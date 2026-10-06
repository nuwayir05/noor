"""
Noor retrieval — the "R" in RAG.

Finds the approved passages that best match a child's (or parent's) question, inside the topic the
scope check (Haiku) returned. Sonnet then builds the lesson ONLY from what this returns.

Three things make it robust to how children actually write:
  1. Arabic normalisation   — no tashkeel, unified hamza/alef/ya/ta marbuta, punctuation removed.
  2. Dialect expansion      — "وش/ليش/أبي/أسوي…" also searched as "ماذا/لماذا/أريد/أفعل…".
  3. Hybrid scoring         — meaning (embedding model) + spelling (character n-grams).
     Meaning catches paraphrases; spelling catches typos and rare words. Score = a*meaning + (1-a)*spelling.

Each passage is indexed as several "units": its text+explanation, and each dialect example question.
A passage's score = its best unit. Below THRESHOLD -> status "no_match" -> the app shows the referral.

Usage
  from retrieval import NoorRetriever
  r = NoorRetriever('noor_passages.json', model='bge-m3')       # approved passages only
  ctx = r.retrieve('ليش ناكل باليمين', topic='آداب الطعام')
  ctx['status'] -> 'ok' | 'no_match';  ctx['passages_block'] -> goes into {PASSAGES}

Models (run on your laptop; downloaded once from Hugging Face, then cached):
  bge-m3     BAAI/bge-m3                      ~2.3 GB  (recommended)
  e5-large   intfloat/multilingual-e5-large   ~2.2 GB
  e5-small   intfloat/multilingual-e5-small   ~0.5 GB
  lexical    character n-grams only, no download (baseline / emergency fallback)
"""
import hashlib, json, os, re
import numpy as np

MODELS = {
    'bge-m3':   dict(hf='BAAI/bge-m3', q_prefix='', p_prefix=''),
    'e5-large': dict(hf='intfloat/multilingual-e5-large', q_prefix='query: ', p_prefix='passage: '),
    'e5-small': dict(hf='intfloat/multilingual-e5-small', q_prefix='query: ', p_prefix='passage: '),
    'lexical':  dict(hf=None, q_prefix='', p_prefix=''),
}

# ---- Tuned on Nuwayir's laptop, 4 Oct 2026 (eval_retrieval.py, 66 questions): bge-m3 a=0.4 th=0.45 ----
ALPHA = {'bge-m3': 0.4, 'e5-large': 0.7, 'e5-small': 0.4, 'lexical': 0.0}       # weight of meaning vs spelling
THRESHOLDS = {'bge-m3': 0.45, 'e5-large': 0.65, 'e5-small': 0.47, 'lexical': 0.17}

TASHKEEL = re.compile(r'[ؗ-ًؚ-ْٰۖ-ۭـ]')
INVISIBLE = re.compile(r'[​-‏⁦-⁩﻿]')


def norm(s):
    """Same normalisation for passages and questions."""
    s = TASHKEEL.sub('', INVISIBLE.sub('', str(s or '')))
    s = re.sub('[أإآٱ]', 'ا', s).replace('ى', 'ي').replace('ة', 'ه').replace('ؤ', 'و').replace('ئ', 'ي')
    s = re.sub(r'[٠-٩]', lambda m: str('٠١٢٣٤٥٦٧٨٩'.index(m.group())), s)   # Arabic digits -> 0-9
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


# Saudi/Gulf dialect -> MSA / passage vocabulary. Keys and values are in norm() form.
# Added to the question (never replacing it), so nothing the child wrote is lost.
DIALECT = {
    'وش': 'ماذا ما', 'ايش': 'ماذا ما', 'شنو': 'ماذا', 'ليش': 'لماذا لم', 'ليه': 'لماذا', 'عشان': 'لكي لان',
    'ابي': 'اريد', 'ابغي': 'اريد', 'ابغا': 'اريد', 'يبي': 'يريد', 'تبي': 'تريد',
    'اسوي': 'افعل', 'يسوي': 'يفعل', 'نسوي': 'نفعل', 'سويت': 'فعلت', 'تسوي': 'تفعل',
    'وين': 'اين', 'الحين': 'الان', 'كذا': 'هكذا', 'زين': 'حسن جيد', 'مو': 'ليس', 'ماهو': 'ليس',
    'صحيت': 'استيقظت', 'اصحي': 'استيقظ', 'نصحي': 'نستيقظ', 'قمت': 'استيقظت',
    'ماما': 'ام', 'امي': 'ام', 'بابا': 'اب', 'ابوي': 'اب', 'ولدي': 'ابن الولد', 'بنتي': 'البنت الولد',
    'جدي': 'الكبير', 'جدتي': 'الكبير', 'اخوي': 'اخ اخي', 'اختي': 'اخت اخي',
    'الحمام': 'الخلاء الغائط', 'حمام': 'الخلاء', 'دوره': 'الخلاء', 'المياه': 'الخلاء',
    'اطلع': 'اخرج', 'طلعت': 'خرجت', 'ادخل': 'دخل', 'دخلت': 'دخل',
    'شمال': 'الشمال اليسار', 'يسار': 'الشمال', 'يمين': 'اليمين اليمني', 'يميني': 'اليمين الايمن',
    'معصب': 'غضب الغضب', 'عصبت': 'غضب الغضب', 'معصبه': 'غضب', 'زعلان': 'غضب', 'زعلت': 'غضب',
    'كابوس': 'حلم الرؤيا يكره', 'حلمت': 'حلم الرؤيا', 'خفت': 'يخافه يكره',
    'قطه': 'البهيمه الحيوان', 'قطتنا': 'البهيمه الحيوان', 'قطوه': 'البهيمه الحيوان', 'قطوتي': 'البهيمه',
    'كلب': 'الحيوان', 'حيوان': 'البهيمه', 'جوعانه': 'تجيعه جوع', 'جوعان': 'تجيعه جوع',
    'يع': 'عاب عيب الطعام', 'مو حلو': 'عاب', 'الغدا': 'الطعام', 'العشا': 'الطعام العشاء', 'الفطور': 'الطعام',
    'ساندويتش': 'طعام', 'ساندويتشي': 'طعامي', 'عزيمه': 'الضيافه طعام', 'عزمونا': 'الضيافه',
    'شبعت': 'الحمد بعد الاكل', 'الحس': 'يلعق', 'الحسها': 'يلعقها', 'الحس اصابعي': 'لعق الاصابع',
    'سريري': 'فراش فراشه', 'فراشي': 'فراشه', 'مخدتي': 'فراش', 'انام': 'النوم ينام', 'بنام': 'النوم ينام',
    'وضو': 'الوضوء', 'اتوضا': 'الوضوء توضا', 'توضيت': 'توضا الوضوء',
    'مسواك': 'السواك', 'فرشه': 'السواك', 'اسناني': 'السواك فم',
    'يأذن': 'المؤذن النداء', 'يذن': 'المؤذن النداء', 'الاذان': 'النداء المؤذن', 'اذان': 'النداء المؤذن',
    'التحيات': 'التشهد', 'جبهتي': 'السجود',
    'كذبه': 'الكذب', 'كذبت': 'الكذب', 'اكذب': 'الكذب', 'نكذب': 'الكذب',
    'اضرب': 'يده الاذي', 'اضربها': 'يده الاذي', 'اضربه': 'يده الاذي', 'تزعجني': 'الاذي', 'يضايقني': 'الاذي',
    'شكرا': 'يشكر الشكر', 'اشكر': 'يشكر', 'عطست': 'عطس', 'يعطس': 'عطس',
    'ركعه': 'ركعات', 'الشارع': 'الطريق', 'احسد': 'الحسد',
}
_DIALECT_PHRASES = sorted((k for k in DIALECT if ' ' in k), key=len, reverse=True)


def expand(q):
    """Normalise + add MSA equivalents of dialect words (prefixes و/ف/ب/ال handled)."""
    q = norm(q)
    extra = []
    for ph in _DIALECT_PHRASES:
        if ph in q:
            extra.append(DIALECT[ph])
    for tok in q.split():
        for cand in (tok, re.sub(r'^(و|ف|ب)', '', tok), re.sub(r'^(وال|بال|فال|ال)', '', tok)):
            if cand in DIALECT:
                extra.append(DIALECT[cand]); break
    return q + (' ' + ' '.join(extra) if extra else '')


def format_passage(p):
    """One passage in the exact shape the answer-builder prompt expects."""
    quran = p['type'] == 'quran'
    out = [f"{'الآية' if quran else 'الحديث'}: {p.get('text_simple') if quran else p['text']}",
           f"المصدر: {p['source']}", f"الدرجة: {p['grade']}", f"الشرح: {p['explanation']}"]
    if p.get('benefits'):
        out.append('الفوائد: ' + ' / '.join(p['benefits']))
    if p.get('word_meanings'):
        out.append('معاني الكلمات: ' + ' / '.join(p['word_meanings']))
    return '\n'.join(out)


class NoorRetriever:
    def __init__(self, passages_path='noor_passages.json', model='bge-m3', approved_only=True,
                 threshold=None, alpha=None, cache_dir='.noor_index'):
        if model not in MODELS:
            raise ValueError(f'unknown model {model}; choose from {list(MODELS)}')
        self.model_key, self.cfg = model, MODELS[model]
        self.threshold = THRESHOLDS[model] if threshold is None else threshold
        self.alpha = ALPHA[model] if alpha is None else alpha
        all_p = json.load(open(passages_path, encoding='utf-8'))
        self.passages = [p for p in all_p if p.get('approved')] if approved_only else all_p
        if not self.passages:
            raise RuntimeError("No approved passages yet. Mark approved=true after Shahad's review, "
                               "or pass approved_only=False while developing.")
        self._build_units()
        self._build_lexical()
        self.dense = None
        if self.cfg['hf']:
            self._build_dense(cache_dir)

    # ------------------------------------------------------------------ index
    def _build_units(self):
        self.units, owner, self.kind = [], [], []
        for i, p in enumerate(self.passages):
            body = (p.get('text_simple') or p['text']) + ' ' + p['explanation']
            self.units.append(norm(body)); owner.append(i); self.kind.append('body')
            for q in p['example_questions']:
                self.units.append(expand(q)); owner.append(i); self.kind.append('example')
        self.owner = np.array(owner)

    def _build_lexical(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.lex = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 4), sublinear_tf=True)
        self.lex_vecs = self.lex.fit_transform(self.units)            # rows are L2-normalised

    def _build_dense(self, cache_dir):
        from sentence_transformers import SentenceTransformer
        self.dense = SentenceTransformer(self.cfg['hf'])
        self.dense.max_seq_length = 512
        texts = [(self.cfg['q_prefix'] if k == 'example' else self.cfg['p_prefix']) + norm(u)
                 for u, k in zip(self.units, self.kind)]
        key = hashlib.md5((self.model_key + '|' + '\n'.join(texts)).encode()).hexdigest()[:12]
        path = os.path.join(cache_dir, f'{self.model_key}-{key}.npy')
        if os.path.exists(path):
            self.dense_vecs = np.load(path)
        else:
            self.dense_vecs = self.dense.encode(texts, normalize_embeddings=True, batch_size=16,
                                                show_progress_bar=True).astype(np.float32)
            try:
                os.makedirs(cache_dir, exist_ok=True)
                np.save(path, self.dense_vecs)
            except OSError:                         # read-only host: just keep it in memory
                pass

    # ------------------------------------------------------------------ search
    def unit_scores(self, question):
        lex = (self.lex_vecs @ self.lex.transform([expand(question)]).T).toarray().ravel()
        if self.dense is None:
            return lex
        qv = self.dense.encode([self.cfg['q_prefix'] + norm(question)], normalize_embeddings=True)[0]
        return self.alpha * (self.dense_vecs @ qv) + (1 - self.alpha) * lex

    def search(self, question, topic=None, k=3, _scores=None):
        sims = self.unit_scores(question) if _scores is None else _scores
        best = {}
        for u, s in enumerate(sims):
            i = int(self.owner[u])
            if topic and self.passages[i]['topic'] != topic:
                continue
            if i not in best or s > best[i][0]:
                best[i] = (float(s), self.kind[u])
        ranked = sorted(best.items(), key=lambda kv: -kv[1][0])[:k]
        return [dict(passage=self.passages[i], score=round(s, 4), matched_on=kind)
                for i, (s, kind) in ranked]

    def retrieve(self, question, topic=None, k=3):
        """What the /ask endpoint calls after the scope check."""
        hits = self.search(question, topic, k)
        top = hits[0]['score'] if hits else 0.0
        hits = [h for h in hits if h['score'] >= self.threshold]       # never pad with weak matches
        if not hits:
            return dict(status='no_match', top_score=top, passages=[], passage_ids=[], passages_block='')
        return dict(status='ok', top_score=top,
                    passages=[h['passage'] for h in hits],
                    passage_ids=[h['passage']['passage_id'] for h in hits],
                    passages_block='\n\n---\n\n'.join(format_passage(h['passage']) for h in hits))


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Try a question against the Noor index')
    ap.add_argument('question'); ap.add_argument('--topic'); ap.add_argument('--model', default='bge-m3')
    ap.add_argument('--all', action='store_true', help='include passages not yet approved (development)')
    a = ap.parse_args()
    r = NoorRetriever(model=a.model, approved_only=not a.all)
    print('expanded query:', expand(a.question))
    for h in r.search(a.question, a.topic, k=5):
        print(f"{h['score']:.3f}  {h['passage']['passage_id']:<16} ({h['matched_on']})  {h['passage']['title'][:60]}")
    ctx = r.retrieve(a.question, a.topic)
    print('\nstatus:', ctx['status'], '| sent to Sonnet:', ctx['passage_ids'])
