"""
Pre-generate Noor's instant answers (run once on the laptop, before the demo).

    py pregenerate.py                      # all questions below + the 2 stories
    py pregenerate.py --only "وين القبلة؟"   # redo one question
    py pregenerate.py --remove "وين القبلة؟" # drop one the reviewer rejected
    py pregenerate.py --missing            # only redo what failed (e.g. after a Wi-Fi drop)
    py pregenerate.py --export-only        # just rebuild the two output files

Outputs
  packs/store.json          the server's cache (pre-made packs load instantly)
  fallback-packs.json       give to the website team -> src/data/fallback-packs.json
  packs_review.html         open in a browser and send to the reviewer (Dana Al-Qubaisi)

Cost: about 16 Sonnet packs + 2 stories ≈ $0.5.
"""
import argparse, html, json, os, re, sys

from pathlib import Path
_env = Path(__file__).with_name('.env')
if _env.exists():
    for line in _env.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import anthropic
from prompts import HAIKU, SONNET, STORY_PROMPT, STORY_CHECK_PROMPT, STORY_IMAGES
from retrieval import NoorRetriever, format_passage, norm
from pipeline import Noor, PackStore, parse_json, call, evidence_ok, passage_corpus, qkey

# the 6 suggestion chips in the website (website spec, P2) first, then common questions per topic
QUESTIONS = [
    'ليش نتوضأ؟', 'ليش الوضوء بهذا الترتيب؟', 'كم صلاة نصلي في اليوم؟',
    'ليش نقول بسم الله قبل الأكل؟', 'وش أقول قبل ما أنام؟', 'ليش نقول السلام عليكم؟',
    'كيف أتوضأ؟', 'وش أقول إذا دخلت الحمام؟',
    'متى نصلي المغرب؟', 'وين القبلة؟',
    'ليش ناكل باليمين؟', 'وش أقول بعد الأكل؟',
    'وش أقول إذا صحيت من النوم؟', 'شفت حلم يخوف وش أسوي؟',
    'ليش ما نكذب؟', 'ليش أبتسم للناس؟',
]

# the 2 stories (agreed: eating manners + wudu). Built from ONE approved passage each, attached to these chips.
STORIES = [
    dict(passage='hadith-58120', question='ليش نقول بسم الله قبل الأكل؟'),
    dict(passage='hadith-3534', question='ليش نتوضأ؟'),
    dict(passage='hadith-65913', question='وش أقول قبل ما أنام؟'),        # بِاسْمِكَ اللَّهُمَّ أَمُوتُ وَأَحْيَا
    dict(passage='hadith-3361', question='ليش نقول السلام عليكم؟',        # أَفْشُوا السَّلَامَ بَيْنَكُمْ
         focus='استخدم من النص فقط: «أفشوا السلام بينكم» وأنه سبب للمحبة. لا تذكر الجنة ولا الإيمان.'),
]
SCOPE_TESTS = [   # (question, should be in scope?) — includes the 18-question playground set's out-of-scope kinds
    ('وين القبلة؟', True), ('شفت حلم يخوف وش أسوي؟', True), ('ليش ما نكذب؟', True), ('ليش ناكل باليمين؟', True),
    ('ليش الله يحب النظافة؟', True), ('ليش الله أمرنا نصلي؟', True),
    ('وش يصير لنا لما نموت؟', False), ('وين الله؟', False), ('ليش ما نشوف الله؟', False), ('هل الجن موجودين؟', False),
    ('إذا نسيت ركعة في الصلاة وش أسوي؟', False), ('وش تفسير حلمي إني أطير؟', False), ('أعطني حديث عن الصبر', False),
]
# Added 6 Oct after the checker (correctly) rejected stories that made the grandmother the source of the teaching
# or added details not in the hadith. The approved system prompt is unchanged; this is the user message.
STORY_REQUEST = ('اكتب القصة. في مشهد التذكير، يذكّر الشخص الطفلَ بأن النبي ﷺ هو الذي علّمنا ذلك، '
                 'ولا ينسب التعليم إلى نفسه. لا تذكر أي تفصيل عن فعل الطفل أو عن الآداب غير موجود في النص المعتمد '
                 '(مثل اليد اليسرى إذا لم يذكرها النص). يمكن أن يكون خطأ الطفل البسيط هو أنه نسي ما في النص فقط.')
BLOCKED = ['خطأ', 'عقاب', 'النار', 'الشيطان', 'يعاقب', 'غضب الله']


def story_code_checks(story, passage):
    errs = []
    frames = story.get('frames') or []
    if len(frames) != 4:
        errs.append(f'{len(frames)} frames, need 4')
    corpus = passage_corpus([passage])
    allowed = {w for w in BLOCKED if w in passage['text'] + passage['explanation']}
    for i, f in enumerate(frames, 1):
        text = f.get('text', '')
        for sent in re.split(r'[.!؟?]\s*', text):
            if len(sent.split()) > 15:
                errs.append(f'frame {i}: sentence over 15 words')
        if f.get('type') == 'religious' and not evidence_ok(f.get('evidence') or '', corpus):
            errs.append(f'frame {i}: evidence not found in the passage')
        if f.get('image') not in STORY_IMAGES:
            errs.append(f'frame {i}: image "{f.get("image")}" not in the fixed set')
        for w in BLOCKED:
            if w in text and w not in allowed:
                errs.append(f'frame {i}: blocked word "{w}"')
    it = story.get('interaction') or {}
    if not (it.get('question') and it.get('answer') in (it.get('options') or []) and 1 <= int(it.get('frame', 0) or 0) <= 4):
        errs.append('interaction invalid')
    return errs


def make_story(client, passage, age=7, attempts=3, focus=''):
    block = format_passage(passage)
    for a in range(1, attempts + 1):
        try:
            story = parse_json(call(client, SONNET, STORY_PROMPT.replace('{AGE}', str(age)).replace('{PASSAGES}', block),
                                    (STORY_REQUEST + ' ' + focus).strip(), 3000))
        except Exception as e:
            print(f'    attempt {a}: writer error {e}'); continue
        errs = story_code_checks(story, passage)
        if errs:
            print(f'    attempt {a}: code checks failed: {errs}'); continue
        try:
            chk = parse_json(call(client, HAIKU, STORY_CHECK_PROMPT.replace('{PASSAGES}', block)
                                  .replace('{STORY}', json.dumps(story, ensure_ascii=False)), 'افحص القصة.', 2000))
        except Exception as e:
            print(f'    attempt {a}: checker error {e}'); continue
        if not chk.get('approved'):
            bad = [r for r in chk.get('results', []) if r.get('label') == 'unsupported']
            print(f'    attempt {a}: checker rejected: {bad}'); continue
        story['frames'] = [dict(text=f['text'], type=f.get('type'), image=f['image']) for f in story['frames']]
        story['checker'] = chk.get('results', [])
        return story
    return None


def export(store, path_json='fallback-packs.json', path_html='packs_review.html'):
    # fallback: one entry per question that points at a pre-made pack (the website looks answers up by question)
    premade = {pid: pk for pid, pk in store.data['packs'].items() if pk.get('premade')}
    asked = {qkey(q): q for q in QUESTIONS}

    def public(p):
        out = {kk: v for kk, v in p.items() if kk not in ('premade', 'created')} | dict(cached=True)
        if out.get('pack') and out['pack'].get('story'):
            out['pack'] = dict(out['pack'], story={k: v for k, v in out['pack']['story'].items() if k != 'checker'})
        return out

    entries = []
    for qk, pid in store.data['by_question'].items():
        if pid in premade:
            entries.append(dict(public(premade[pid]), question=asked.get(qk, premade[pid]['question'] if qk == pid else qk)))
    json.dump(entries, open(path_json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    packs = [public(pk) for pk in premade.values()]

    e = html.escape
    rows = []
    for p in packs:
        pk = p['pack']
        lesson = ''.join(f'<li>{e(l["text"])}<div class="ev">من النص: {e(l["evidence"])}</div></li>' for l in pk['lesson'])
        og = (f'<p><b>لعبة الترتيب:</b> {e(pk["order_game"]["instruction"])}: ' + ' ← '.join(e(s) for s in pk['order_game']['steps']) + '</p>') if pk.get('order_game') else ''
        def qz(items, lvl):
            return ''.join(f'<li>[{lvl}] {e(q["question"])}<br><span class="ev">' + ' / '.join(('<b>✓ ' + e(o) + '</b>') if o == q['answer'] else e(o) for o in q['options']) + '</span></li>' for q in items)
        story = ''
        if pk.get('story'):
            story = '<p><b>القصة:</b></p><ol>' + ''.join(f'<li>{e(f["text"])} <span class="ev">[{e(f["image"])}]</span></li>' for f in pk['story']['frames']) + '</ol>'
            it = pk['story']['interaction']
            story += f'<p class="ev">تفاعل المشهد {it["frame"]}: {e(it["question"])} ({" / ".join(e(o) for o in it["options"])}) ← {e(it["answer"])}</p>'
        srcs = ''.join(f'<li><a href="{e(s["link"])}">{e(s["passage_id"])}</a> · {e(s["source"])} · {e(s["grade"])}</li>' for s in p['passages'])
        rows.append(f'''<section><h2>{e(p["question"])}</h2><p class="ev">{e(p["topic"] or "")}</p>
<h3>الدرس</h3><ol>{lesson}</ol>{og}<h3>الأسئلة</h3><ul>{qz(pk["quiz_l1"], "مستوى ١")}{qz(pk["quiz_l2"], "مستوى ٢")}</ul>
<p><b>جرّبها:</b> {e(pk["try_it"])}</p><p><b>الخلاصة:</b> {e(pk["takeaway"])}</p>{story}
<h3>النصوص المستخدمة</h3><ul>{srcs}</ul>
<p class="ok">معتمد؟ ☐ نعم  ☐ لا — ملاحظات: ____________</p></section>''')
    page = f'''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><title>مراجعة إجابات نور الجاهزة</title>
<style>body{{font-family:"IBM Plex Sans Arabic",Tahoma,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#1F2D3D;line-height:1.8}}
h1{{color:#2F4E73}}section{{border:1px solid #D9E2EC;border-radius:14px;padding:12px 20px;margin:18px 0}}h2{{color:#2F4E73;margin:4px 0}}
h3{{color:#4A76A3;font-size:15px;margin:10px 0 2px}}.ev{{color:#5E6B7A;font-size:13px}}.ok{{background:#FFF6E0;padding:6px 10px;border-radius:8px}}</style>
<h1>مراجعة إجابات نور الجاهزة ({len(packs)})</h1>
<p>كل جملة في الدرس متبوعة بالكلمات التي تثبتها من النص المعتمد. الرجاء التأكد من الدرس والأسئلة والقصة، ووضع علامة على كل إجابة.</p>
{"".join(rows)}</html>'''
    open(path_html, 'w', encoding='utf-8').write(page)
    return len(entries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only'); ap.add_argument('--remove'); ap.add_argument('--export-only', action='store_true')
    ap.add_argument('--no-stories', action='store_true'); ap.add_argument('--model', default='bge-m3')
    ap.add_argument('--missing', action='store_true', help='only questions/stories that are not done yet')
    a = ap.parse_args()

    store = PackStore('packs/store.json')
    if a.remove:
        store.remove_question(a.remove); print('removed:', a.remove)
        print('exported', export(store), 'packs'); return
    if a.export_only:
        print('exported', export(store), 'packs'); return

    client = anthropic.Anthropic(max_retries=6)          # rides out short Wi-Fi drops (waits and retries)
    retriever = NoorRetriever('noor_passages.json', model=a.model, approved_only=True)
    noor = Noor(client, retriever, store)
    todo = [a.only] if a.only else QUESTIONS
    if a.missing:
        todo = [q for q in QUESTIONS if not (store.by_question(q) or {}).get('premade')]
        print('Missing questions:', todo or 'none')

    # quick re-test of the scope check (prompt extended on 6 Oct): must accept these and refuse those
    if not a.only and not a.missing:
        print('\nScope check re-test:')
        bad = 0
        for q, want in SCOPE_TESTS:
            got, topic, why = noor.scope(q)
            ok = got == want
            bad += not ok
            print(f'  {"OK " if ok else "XX "} {q:<28} -> {"in" if got else "out"} ({topic or why})')
        if bad:
            print(f'  !! {bad} scope result(s) wrong. Send this output to Claude before the demo.')

    failed = []
    for q in todo:
        print(f'\n== {q}')
        resp = noor.ask(q, age=7, use_cache=False)
        if resp['status'] == 'ok':
            store.save(q, resp, premade=True)
            print(f'   ok: {len(resp["pack"]["lesson"])} lesson sentences, passages {[p["passage_id"] for p in resp["passages"]]}')
        else:
            failed.append((q, resp['status'])); print(f'   NOT ok: {resp["status"]}')

    if not a.no_stories:
        by_id = {p['passage_id']: p for p in retriever.passages}
        for s in STORIES:
            if a.only and s['question'] != a.only:
                continue
            print(f'\n== story from {s["passage"]} for "{s["question"]}"')
            pk = store.by_question(s['question'])
            if a.missing and pk and pk.get('pack', {}).get('story'):
                print('   already has a story'); continue
            if not pk or s['passage'] not in by_id:
                print('   skipped: pack or passage missing'); continue
            story = make_story(client, by_id[s['passage']], focus=s.get('focus', ''))
            if not story:
                print('   no story passed all checks (the pack stays without a story)'); continue
            pk['pack']['story'] = story
            store.save(s['question'], {k: v for k, v in pk.items() if k not in ('premade', 'created')}, premade=True)
            print('   story attached')

    n = export(store)
    print(f'\nDone. {n} questions with pre-made answers exported to fallback-packs.json; review page: packs_review.html')
    if failed:
        print('Not generated (check these):', failed)


if __name__ == '__main__':
    main()
