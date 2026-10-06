"""
Rebuild ONE pre-made answer (lesson, game, quizzes, try-it) from the same approved passages,
keeping its approved story exactly as it is (the story pictures are drawn for that text).

    py fix_pack.py "وش أقول قبل ما أنام؟"

Then re-export: fallback-packs.json + packs_review.html (send the review page to the Sharia reviewer).
"""
import json, os, sys
from pathlib import Path

_env = Path(__file__).with_name('.env')
if _env.exists():
    for line in _env.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import anthropic
from pipeline import Noor, PackStore, response
from pregenerate import export


class _NoRetriever:          # rebuilding needs no search: the passages are already chosen
    passages = []


def main(question):
    store = PackStore('packs/store.json')
    old = store.by_question(question)
    if not old:
        sys.exit(f'No pre-made answer for: {question}')
    by_id = {p['passage_id']: p for p in json.load(open('noor_passages.json', encoding='utf-8'))}
    passages = []


def main(question):
    store = PackStore('packs/store.json')
    old = store.by_question(question)
    if not old:
        sys.exit(f'No pre-made answer for: {question}')
    by_id = {p['passage_id']: p for p in json.load(open('noor_passages.json', encoding='utf-8'))
             if isinstance(p, dict)} if isinstance(json.load(open('noor_passages.json', encoding='utf-8')), list) \
        else {p['passage_id']: p for p in json.load(open('noor_passages.json', encoding='utf-8'))['passages']}
    passages = [by_id[p['passage_id']] for p in old['passages']]
    noor = Noor(anthropic.Anthropic(max_retries=4), _NoRetriever(), store)
    pack, report = noor.build(question, 7, passages, attempts=3)
    if not pack:
        sys.exit(f'Could not rebuild: {report}')
    pack['story'] = (old.get('pack') or {}).get('story')          # keep the approved story + its pictures
    out = response('ok', question, old.get('topic'), pack, passages, cached=False)
    store.save(question, out, premade=True)
    n = export(store)
    print(f'Rebuilt "{question}": {len(pack["lesson"])} lesson sentences, '
          f'{len(pack["quiz_l1"])}+{len(pack["quiz_l2"])} quiz questions, '
          f'order game: {"yes" if pack["order_game"] else "no"}, story kept: {"yes" if pack["story"] else "no"}. '
          f'Exported {n} answers.')


if __name__ == '__main__':
    main(' '.join(sys.argv[1:]).strip() or 'وش أقول قبل ما أنام؟')
