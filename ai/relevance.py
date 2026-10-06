"""
Noor relevance check: Haiku confirms which retrieved passages ACTUALLY answer the question.

Why: the search score says "this passage is about the same thing", not "this passage answers it".
"كم ركعة الظهر؟" scores high against prayer passages even though none states 4 rak'ahs.
Haiku reads the 3–5 candidates and keeps only those that answer, or none -> referral.

Pipeline (in /ask):
  scope check (Haiku) -> retrieval top 5 (fast, generous) -> relevance check (Haiku) -> Sonnet
Cost ~0.1 cent and ~1–2 s per new question. Cached/pre-generated packs skip all of this.

  from relevance import retrieve_verified
  ctx = retrieve_verified(retriever, client, question, topic)
  ctx['status'] -> 'ok' | 'no_match';  ctx['passages_block'] -> {PASSAGES}
"""
import json, re
from retrieval import format_passage

HAIKU = 'claude-haiku-4-5-20251001'

RELEVANCE_PROMPT = """أنت مدقق صلة لمنصة "نور" التعليمية الإسلامية للأطفال. لا تُجب عن السؤال أبدًا.
ستصلك رسالة فيها سؤال من طفل أو من والده، ونصوص معتمدة لكل منها رقم تعريف بين قوسين مربعين.

مهمتك: اختر النصوص التي تجيب عن السؤال نفسه مباشرة.
- النص يجيب إذا ذكر صراحةً الشيء المسؤول عنه بعينه: الفعل، أو الذكر، أو السبب، أو العدد، أو الوقت، أو الخطوة.
- لا تختر نصًا لأنه من نفس الموضوع فقط. مثال: "كم ركعة صلاة الظهر؟" لا يجيب عنه نص عن فضل الصلاة أو عن عدد الصلوات.
- إذا سأل عن عدد أو وقت أو حكم أو تفصيل لا يذكره أي نص صراحةً، فأعد قائمة فارغة.
- أسئلة "ليش/لماذا" يجيب عنها النص إذا ذكر سببًا أو فضلًا، أو ذكر أن النبي ﷺ فعل ذلك أو أمر به.
- الطفل قد يكتب بالعامية أو بأخطاء إملائية؛ افهم المقصود.
- رتّب النصوص المختارة من الأقوى إلى الأضعف، بحد أقصى ٣.

أعد JSON فقط دون أي نص آخر:
{"relevant_ids": ["رقم التعريف", "..."], "reason": "سبب قصير"}"""


def _candidate_block(p, max_expl=350):
    text = p.get('text_simple') if p['type'] == 'quran' else p['text']
    expl = p['explanation'] if len(p['explanation']) <= max_expl else p['explanation'][:max_expl] + '…'
    return f"[{p['passage_id']}]\nالنص: {text[:400]}\nالشرح: {expl}"


def _parse(text):
    text = re.sub(r'^```(?:json)?|```$', '', text.strip(), flags=re.M).strip()
    m = re.search(r'\{.*\}', text, flags=re.S)
    return json.loads(m.group(0) if m else text)


def check_relevance(client, question, passages, model=HAIKU):
    """Returns dict(ids=[...], reason=str, ok=bool). On any API/JSON error: ok=False and ids = all candidates
    (so the app still works; Sonnet's enough_info and the evidence check remain as safety nets)."""
    if not passages:
        return dict(ids=[], reason='no candidates', ok=True)
    msg = f"السؤال: {question}\n\nالنصوص:\n\n" + '\n\n'.join(_candidate_block(p) for p in passages)
    try:
        resp = client.messages.create(model=model, max_tokens=300,
                                      system=RELEVANCE_PROMPT,
                                      messages=[{'role': 'user', 'content': msg}])
        out = _parse(resp.content[0].text)
        allowed = [p['passage_id'] for p in passages]
        ids = [i for i in out.get('relevant_ids', []) if i in allowed][:3]   # never trust unknown IDs
        return dict(ids=ids, reason=out.get('reason', ''), ok=True)
    except Exception as e:
        return dict(ids=[p['passage_id'] for p in passages][:3], reason=f'relevance check failed: {e}', ok=False)


def retrieve_verified(retriever, client, question, topic=None, k=5, recall_factor=0.6):
    """Generous search (top k, lower threshold) -> Haiku keeps only passages that answer the question."""
    hits = retriever.search(question, topic, k=k)
    floor = retriever.threshold * recall_factor
    cands = [h['passage'] for h in hits if h['score'] >= floor]
    top = hits[0]['score'] if hits else 0.0
    if not cands:
        return dict(status='no_match', stage='search', top_score=top, passages=[], passage_ids=[],
                    passages_block='', relevance=None)
    rel = check_relevance(client, question, cands)
    keep = [p for pid in rel['ids'] for p in cands if p['passage_id'] == pid]
    if not keep:
        return dict(status='no_match', stage='relevance', top_score=top, passages=[], passage_ids=[],
                    passages_block='', relevance=rel)
    return dict(status='ok', stage='relevance', top_score=top, passages=keep,
                passage_ids=[p['passage_id'] for p in keep],
                passages_block='\n\n---\n\n'.join(format_passage(p) for p in keep), relevance=rel)
