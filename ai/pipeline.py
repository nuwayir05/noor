"""
Noor pipeline: one question in, one /ask response out (the exact shape in the website spec, section 9).

  question
   -> 0. pre-made pack for this exact question?            (instant)
   -> 1. scope check (Haiku)                                 out_of_scope -> referral
   -> 2. search (BGE-M3 + spelling) + relevance check (Haiku) nothing answers -> referral (no_match)
   -> 3. same passages answered before?                      reuse that pack (instant)
   -> 4. answer builder (Sonnet) with ONLY those passages
   -> 5. code checks: every lesson sentence's evidence must be in the passages, quiz answers valid, lengths
   -> saved to the cache, returned

Nothing religious is ever written by code here: all text comes from approved passages or from Sonnet,
and every Sonnet lesson sentence must point to words that exist in the approved passages.
"""
import json, os, re, threading, time
from datetime import datetime, timezone

from prompts import HAIKU, SONNET, SCOPE_PROMPT, ANSWER_PROMPT, TOPICS
from retrieval import norm, format_passage, TASHKEEL
from relevance import retrieve_verified

MAX_WORDS = 16          # prompt asks for 12; allow a little slack before dropping a sentence
STOPWORDS = set('''من الي علي في عن ان انه انها لا لم لن ما ثم او ام هذا هذه ذلك تلك الذي التي الذين كان كانت قال قالت
يكون هو هي هم كل بعض قد لقد اذا اذ حتي مع عند لكن بل غير بين لولا وهو وهي وان فان كما مثل اي ايضا الله
النبي رسول الرسول نبي'''.split())
HONORIFICS = re.compile(r'ﷺ|ﷻ|صلى الله عليه وسلم|رضي الله عنهما|رضي الله عنهم|رضي الله عنها|رضي الله عنه|عليه السلام|عز وجل|سبحانه وتعالى|تعالى')


# ---------------------------------------------------------------- helpers
def parse_json(text):
    """Read the model's JSON even if it is wrapped in ``` or has unescaped quotes inside Arabic text."""
    raw = (text or '').strip()
    if not raw:
        raise ValueError('empty reply')
    body = re.sub(r'^```(?:json)?|```$', '', raw, flags=re.M).strip()
    m = re.search(r'\{.*\}', body, flags=re.S)
    body = m.group(0) if m else body
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        import json_repair                      # fixes e.g. "قل "بسم الله"" inside a string
        out = json_repair.loads(body)
        if not isinstance(out, dict) or not out:
            raise
        return out


def call(client, model, system, user, max_tokens):
    """One model call that returns the reply text. Noor's tasks need no long 'thinking': it is switched off,
    so the whole token budget goes to the JSON answer (newer models think by default and could use it all up)."""
    kw = dict(model=model, system=system, messages=[{'role': 'user', 'content': user}])
    try:
        resp = client.messages.create(max_tokens=max_tokens, thinking={'type': 'disabled'}, **kw)
    except Exception as e:                       # a model that can't switch thinking off: low effort + more room
        if 'thinking' not in str(e).lower() and 'disabled' not in str(e).lower():
            raise
        resp = client.messages.create(max_tokens=max_tokens * 3, output_config={'effort': 'low'}, **kw)
    if getattr(resp, 'stop_reason', '') == 'max_tokens' and not any(getattr(b, 'type', '') == 'text' for b in resp.content):
        resp = client.messages.create(max_tokens=max_tokens * 3, output_config={'effort': 'low'}, **kw)
    text = ''.join(getattr(b, 'text', '') or '' for b in resp.content)
    if not text.strip():
        kinds = [getattr(b, 'type', '?') for b in resp.content]
        raise RuntimeError(f'empty reply from {model} (stop_reason={getattr(resp, "stop_reason", "?")}, blocks={kinds})')
    return text


def save_debug(name, text):
    """Keep unreadable model replies so they can be inspected (packs/debug/)."""
    path = f'packs/debug/{datetime.now().strftime("%H%M%S")}-{re.sub(r"[^a-z0-9]+", "-", name.lower())[:30]}.txt'
    try:
        os.makedirs('packs/debug', exist_ok=True)
        open(path, 'w', encoding='utf-8').write(text or '')
    except OSError:
        return '(not saved)'
    return path


def qkey(question):
    """Key for 'same question': normalised, no punctuation, no question mark."""
    return norm(question).replace('؟', '').strip()


def canonical_topic(t):
    t = t or ''
    for label in TOPICS:
        if label in t or t in label and t:
            return label
    if 'صلا' in t:
        return 'الصلاة'
    return None


def _clean(s):
    s = HONORIFICS.sub(' ', TASHKEEL.sub('', str(s or '')).replace('ـ', ''))   # strip diacritics first, then honorifics
    return re.sub(r'\s+', ' ', norm(s)).strip()


def passage_corpus(passages):
    """Two searchable versions of the passages: plain (normalised) and with honorifics removed
    (Sonnet often writes ﷺ or drops «رضي الله عنه»)."""
    parts = []
    for p in passages:
        parts += [p.get('text_simple') or '', p['text'], p['explanation'], ' '.join(p.get('benefits', [])),
                  ' '.join(p.get('word_meanings', [])), p.get('source', '')]
    joined = ' '.join(parts)
    return (re.sub(r'\s+', ' ', norm(joined)).strip(), _clean(joined))


def evidence_ok(evidence, corpus):
    """True if the evidence words really occur in the approved passages (tashkeel/punctuation/honorific-insensitive).
    Evidence may be quoted with gaps ('...', '…'): every piece must be found."""
    raw_pieces = [x for x in re.split(r'\.\.\.|…', evidence or '') if norm(x)]
    if not raw_pieces:
        return False
    # evidence must carry real words, not just «أن من» left over after honorifics are removed
    content = [w for w in _clean(' '.join(raw_pieces)).split() if len(w) >= 3 and w not in STOPWORDS]
    if len(content) < 1:
        return False
    for raw in raw_pieces:
        if not any(_piece_found(v, c) for v, c in ((re.sub(r'\s+', ' ', norm(raw)).strip(), corpus[0]),
                                                   (_clean(raw), corpus[1]))):
            return False
    return True


def _piece_found(piece, corpus):
    if not piece:
        return True                      # the piece was only an honorific
    if piece in corpus:
        return True
    words = piece.split()
    if len(words) < 3:
        return all(w in corpus.split() for w in words)
    tri = [' '.join(words[i:i + 3]) for i in range(len(words) - 2)]
    return sum(t in corpus for t in tri) / len(tri) >= 0.6


def taught(answer, taught_text):
    """A quiz answer must come from what the child was taught (lesson sentences + ordering steps),
    not from other parts of the hadith. At least half of its content words must appear in that text."""
    a, t = _clean(answer), _clean(taught_text)
    if not a:
        return False
    words = [w for w in a.split() if len(w) >= 3 and w not in STOPWORDS]
    if not words:
        return a in t
    return sum(w in t for w in words) / len(words) >= 0.5


QUIZ_RULE = ('\n\n(تعليمات إضافية: كل سؤال في quiz_l1 و quiz_l2 يجب أن تكون إجابته الصحيحة مذكورة صراحة '
             'في جمل lesson أو في خطوات order_game، لأن الطفل لم يتعلّم غيرها.)')


def validate_pack(raw, passages):
    """Keep only what passes the checks. Returns (pack or None, report)."""
    report = dict(dropped_sentences=[], dropped_quiz=0)
    if not isinstance(raw, dict) or raw.get('enough_info') is False:
        return None, dict(report, reason='enough_info_false')
    corpus = passage_corpus(passages)

    lesson = []
    for item in raw.get('lesson') or []:
        text, ev = (item or {}).get('text', '').strip(), (item or {}).get('evidence', '')
        if text and len(text.split()) <= MAX_WORDS and evidence_ok(ev, corpus):
            lesson.append(dict(text=text, evidence=ev.strip()))
        else:
            report['dropped_sentences'].append(text)
    if not lesson:
        return None, dict(report, reason='no_grounded_sentence')

    def quizzes(items, n_min):
        out = []
        for q in items or []:
            opts = [o.strip() for o in (q or {}).get('options', []) if isinstance(o, str) and o.strip()]
            opts = list(dict.fromkeys(opts))
            ans = (q or {}).get('answer', '').strip()
            if q.get('question') and ans in opts and len(opts) >= n_min:
                out.append(dict(question=q['question'].strip(), options=opts, answer=ans))
            else:
                report['dropped_quiz'] += 1
        return out

    og = raw.get('order_game')
    if isinstance(og, dict):
        steps = [s.strip() for s in og.get('steps', []) if isinstance(s, str) and s.strip()]
        og = dict(instruction=(og.get('instruction') or 'رتّب الخطوات').strip(), steps=steps) if 2 <= len(steps) <= 8 else None
    else:
        og = None

    taught_text = ' '.join([l['text'] for l in lesson] + (og['steps'] if og else []))
    def only_taught(items):
        keep = [q for q in items if taught(q['answer'], taught_text)]
        report['dropped_quiz'] += len(items) - len(keep)
        return keep
    q1, q2 = only_taught(quizzes(raw.get('quiz_l1'), 2)), only_taught(quizzes(raw.get('quiz_l2'), 2))
    if not q1 and not q2:
        return None, dict(report, reason='quiz_not_from_lesson')

    pack = dict(lesson=lesson, order_game=og,
                quiz_l1=q1, quiz_l2=q2,
                try_it=(raw.get('try_it') or '').strip(), takeaway=(raw.get('takeaway') or '').strip(),
                source=(raw.get('source') or '').strip() or ' / '.join(dict.fromkeys(p['source'] for p in passages)),
                story=None)
    return pack, report


def public_passage(p):
    """Passage as the website receives it (website spec, section 9)."""
    return dict(passage_id=p['passage_id'], type=p['type'], topic=p['topic'],
                text=p['text'], source=p['source'], grade=p['grade'],
                dorar_grade=None if (p.get('dorar_grade') or '').startswith('غير مطلوب') else p.get('dorar_grade'),
                partial_ayah=bool(p.get('partial_ayah')), link=p['link'], reviewer=p.get('reviewer'))


def response(status, question, topic=None, pack=None, passages=(), cached=False, reason=None):
    return dict(status=status, question=question, topic=topic, cached=cached, pack=pack,
                passages=[public_passage(p) for p in passages],
                referral=None if status == 'ok' else dict(reason=reason or ''))


# ---------------------------------------------------------------- pack store (cache + pre-made packs)
class PackStore:
    """packs/store.json — {"packs": {pack_id: {...response..., "premade": bool}}, "by_question": {qkey: pack_id}}
    Every question gets its OWN pack (pack_id = its normalised wording), so two pre-made questions that use the
    same hadith never overwrite each other. A new wording that retrieves the same passages can REUSE an existing
    pack (pre-made first) instead of waiting ~15 s for Sonnet."""

    def __init__(self, path='packs/store.json'):
        self.path, self.lock = path, threading.Lock()
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        self.data = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else dict(packs={}, by_question={})

    @staticmethod
    def pset(passage_ids):
        return '|'.join(sorted(passage_ids))

    def by_question(self, question):
        pid = self.data['by_question'].get(qkey(question))
        return self.data['packs'].get(pid) if pid else None

    def by_passages(self, passage_ids):
        want = self.pset(passage_ids)
        hits = [p for p in self.data['packs'].values()
                if self.pset([x['passage_id'] for x in p['passages']]) == want]
        hits.sort(key=lambda p: (not p.get('premade'), p.get('created', '')))   # pre-made first, then oldest
        return hits[0] if hits else None

    def _write(self):
        tmp = self.path + '.tmp'
        try:
            json.dump(self.data, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except OSError as e:                        # read-only host: keep the packs in memory only
            print(f'  (could not save packs: {e})')

    def save(self, question, resp, premade=False):
        """Store resp as this question's own pack (a live pack never replaces a pre-made one)."""
        with self.lock:
            pid = qkey(question)
            old = self.data['packs'].get(pid)
            if not (old and old.get('premade') and not premade):
                self.data['packs'][pid] = dict(resp, question=question, premade=premade,
                                               created=datetime.now(timezone.utc).isoformat(timespec='seconds'))
            self.data['by_question'][pid] = pid
            self._write()

    def alias(self, question, pack):
        """Point a new wording at an existing pack (reuse, no copy)."""
        with self.lock:
            self.data['by_question'][qkey(question)] = qkey(pack['question'])
            self._write()

    def remove_question(self, question):
        with self.lock:
            pid = qkey(question)
            self.data['packs'].pop(pid, None)
            for k in [k for k, v in self.data['by_question'].items() if v == pid or k == pid]:
                self.data['by_question'].pop(k)
            self._write()


# ---------------------------------------------------------------- the pipeline
class Noor:
    def __init__(self, client, retriever, store, log=print):
        self.client, self.retriever, self.store, self.log = client, retriever, store, log
        self.by_id = {p['passage_id']: p for p in retriever.passages}

    def _from_cache(self, hit, question):
        out = {k: v for k, v in hit.items() if k not in ('premade', 'created')}
        return dict(out, question=question, cached=True)

    def scope(self, question):
        try:
            out = parse_json(call(self.client, HAIKU, SCOPE_PROMPT, question, 300))
            return bool(out.get('in_scope')), canonical_topic(out.get('topic')), out.get('reason', '')
        except Exception as e:                   # scope check down: continue; relevance + Sonnet + code still guard
            self.log(f'  scope check failed ({e}); continuing without topic')
            return True, None, 'scope check unavailable'

    def build(self, question, age, passages, attempts=2):
        # Added 6 Oct (user message; the approved system prompt is unchanged): quizzes only about the lesson.
        block = '\n\n---\n\n'.join(format_passage(p) for p in passages)
        system = ANSWER_PROMPT.replace('{AGE}', str(age)).replace('{PASSAGES}', block)
        last = {}
        for i in range(attempts):
            text = ''
            try:
                text = call(self.client, SONNET, system, question + QUIZ_RULE, 4000)
                raw = parse_json(text)
            except Exception as e:
                last = dict(reason=f'sonnet/json error: {e}')
                if text:
                    last['reason'] += f' (reply saved to {save_debug("sonnet", text)})'
                self.log(f'  attempt {i + 1}: {last["reason"]}')
                continue
            pack, report = validate_pack(raw, passages)
            if pack:
                if report['dropped_sentences'] or report['dropped_quiz']:
                    self.log(f'  checks dropped {len(report["dropped_sentences"])} sentence(s), {report["dropped_quiz"]} quiz item(s)')
                return pack, report
            last = report
            if report.get('reason') == 'enough_info_false':
                break
        return None, last

    def ask(self, question, age=7, use_cache=True, allow_new=True):
        t0 = time.time()
        question = (question or '').strip()
        if use_cache:
            hit = self.store.by_question(question)
            if hit:
                self.log(f'[cache] {question}')
                return self._from_cache(hit, question)

        in_scope, topic, reason = self.scope(question)
        if not in_scope:
            self.log(f'[out_of_scope] {question} ({reason})')
            return response('out_of_scope', question, reason=reason)

        ctx = retrieve_verified(self.retriever, self.client, question, topic)
        if ctx['status'] != 'ok':
            self.log(f'[no_match] {question} (stage {ctx["stage"]})')
            return response('no_match', question, topic, reason='لا يوجد نص معتمد يجيب عن هذا السؤال')
        passages = ctx['passages']
        topic = topic or passages[0]['topic']

        if use_cache:
            hit = self.store.by_passages(ctx['passage_ids'])
            if hit:
                self.log(f'[cache by passages] {question} -> reuses pack of "{hit["question"]}"')
                self.store.alias(question, hit)
                return self._from_cache(hit, question)

        if not allow_new:                          # public demo: daily limit for NEW lessons reached
            self.log(f'[limit] {question}')
            return response('no_match', question, topic, reason='تم الوصول إلى الحد اليومي للدروس الجديدة')
        pack, report = self.build(question, age, passages)
        if not pack:
            self.log(f'[no_match] {question} (answer builder: {report.get("reason")})')
            return response('no_match', question, topic, reason='تعذّر بناء درس من النصوص المعتمدة')

        out = response('ok', question, topic, pack, passages, cached=False)
        self.store.save(question, out)
        self.log(f'[ok] {question} -> {ctx["passage_ids"]} in {time.time() - t0:.1f}s')
        return out
