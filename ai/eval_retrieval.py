"""
Compare retrieval set-ups on Noor's labelled children's questions, and tune them.

  python eval_retrieval.py                                   # bge-m3, e5-small, lexical
  python eval_retrieval.py --models bge-m3 e5-large lexical
  python eval_retrieval.py --tests real_questions.csv        # the held-out set your team writes

For each embedding model it tries several meaning/spelling weights (ALPHA) and reports:
  hit@1 / hit@3   correct passage first / in the top 3 (top 3 = what Sonnet receives), with topic filter
  no-filter hit@3 same without the scope-check topic (harder; shows robustness)
  threshold       best cut-off separating answerable questions from 'expected: []' ones
Writes retrieval_report.md (put it on your slide) and retrieval_results.csv (every question).
Uses ALL passages (approved or not) so you can test before Shahad finishes.
"""
import argparse, csv, json, time
import numpy as np
from retrieval import NoorRetriever, ALPHA

ALPHA_GRID = [1.0, 0.85, 0.7, 0.55, 0.4]


def load_tests(path):
    """JSON (test_questions.json format) or CSV with columns: question, topic, expected_passage_ids
    (IDs separated by | ; write none if no passage covers it)."""
    if path.endswith('.csv'):
        out = []
        for row in csv.DictReader(open(path, encoding='utf-8-sig')):
            q = (row.get('question') or '').strip()
            if not q or q.startswith('#'):
                continue
            ids = (row.get('expected_passage_ids') or '').strip()
            exp = [] if ids.lower() in ('', 'none', '-') else [i.strip() for i in ids.split('|') if i.strip()]
            out.append(dict(q=q, topic=row['topic'].strip(), expected=exp))
        return out
    return json.load(open(path, encoding='utf-8'))['questions']


def suggest_threshold(rows):
    good = [r['top_score'] for r in rows if r['answerable'] and r['hit1']]
    none = [r['top_score'] for r in rows if not r['answerable']]
    if not good or not none:
        return None, len(good), 0
    best = (-1, None)
    for th in sorted(set(good + none)):
        score = sum(g >= th for g in good) + sum(n < th for n in none)
        if score > best[0]:
            best = (score, th)
    th = best[1]
    return round(th, 3), sum(g >= th for g in good), sum(n < th for n in none)


def run(r, tests, lex_scores, dense_scores, alpha):
    rows = []
    for t, lx, dn in zip(tests, lex_scores, dense_scores):
        sims = lx if dn is None else alpha * dn + (1 - alpha) * lx
        exp = set(t['expected'])
        for filt in (True, False):
            hits = r.search(t['q'], t['topic'] if filt else None, k=3, _scores=sims)
            ids = [h['passage']['passage_id'] for h in hits]
            rows.append(dict(alpha=alpha, topic_filter=filt, q=t['q'], topic=t['topic'],
                             expected='|'.join(t['expected']) or '(none)', top3='|'.join(ids),
                             top_score=hits[0]['score'] if hits else 0, answerable=bool(exp),
                             hit1=bool(exp) and bool(ids) and ids[0] in exp,
                             hit3=bool(exp) and bool(exp & set(ids))))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', nargs='+', default=['bge-m3', 'e5-small', 'lexical'])
    ap.add_argument('--tests', default='test_questions.json')
    a = ap.parse_args()
    tests = load_tests(a.tests)
    n_ans = sum(1 for t in tests if t['expected']); n_none = len(tests) - n_ans

    summary, all_rows = [], []
    for m in a.models:
        print(f'\n=== {m} ===')
        try:
            t0 = time.time()
            r = NoorRetriever(model=m, approved_only=False, threshold=-1)
            build = time.time() - t0
        except Exception as e:
            print(f'  skipped: {e}'); continue
        t0 = time.time()
        lex = [(r.lex_vecs @ r.lex.transform([__import__('retrieval').expand(t['q'])]).T).toarray().ravel() for t in tests]
        if r.dense is not None:
            qv = r.dense.encode([r.cfg['q_prefix'] + __import__('retrieval').norm(t['q']) for t in tests],
                                normalize_embeddings=True)
            dense = [r.dense_vecs @ v for v in qv]
            grid = ALPHA_GRID
        else:
            dense = [None] * len(tests); grid = [0.0]
        per_q_ms = (time.time() - t0) / len(tests) * 1000

        results = []
        for alpha in grid:
            rows = run(r, tests, lex, dense, alpha)
            f = [x for x in rows if x['topic_filter']]; nf = [x for x in rows if not x['topic_filter']]
            th, kept, blocked = suggest_threshold(f)
            res = dict(model=m, alpha=alpha, h1=sum(x['hit1'] for x in f), h3=sum(x['hit3'] for x in f),
                       h3n=sum(x['hit3'] for x in nf), th=th, kept=kept, blocked=blocked, rows=rows)
            results.append(res)
            label = 'meaning only' if alpha == 1.0 else ('spelling only' if alpha == 0.0 else f'hybrid a={alpha}')
            print(f'  {label:<16} hit@1 {res["h1"]}/{n_ans}  hit@3 {res["h3"]}/{n_ans}  '
                  f'(no filter {res["h3n"]}/{n_ans})  threshold {th}: blocks {blocked}/{n_none} no-answer')
        best = max(results, key=lambda x: (x['h1'] + x['h3'] + x['blocked'], x['h1'], x['blocked']))
        best['ms'] = per_q_ms; best['build'] = build
        summary.append(best)
        all_rows += [dict(model=m, **x) for x in best['rows']]
        print(f'  -> best for {m}: ALPHA={best["alpha"]}, THRESHOLD={best["th"]}   ({per_q_ms:.0f} ms/question)')
        for x in best['rows']:
            if x['topic_filter'] and x['answerable'] and not x['hit3']:
                print(f"     MISS: {x['q']}  -> {x['top3']}  (expected {x['expected']})")

    if not summary:
        print('\nNothing ran. Install:  pip install -r requirements.txt'); return
    with open('retrieval_results.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(all_rows[0])); w.writeheader(); w.writerows(all_rows)

    lines = ['# Noor retrieval test', '',
             f'Test file: `{a.tests}`: {len(tests)} questions, {n_ans} with a correct passage, '
             f'{n_none} with no passage (must be refused).', '',
             '| Set-up | Correct passage 1st | Correct passage in top 3 | Top 3 without topic filter | No-answer refused | Threshold | Search time |',
             '|---|---|---|---|---|---|---|']
    for s in summary:
        name = s['model'] if s['alpha'] in (0.0, 1.0) else f"{s['model']} + spelling (a={s['alpha']})"
        lines.append(f"| {name} | {s['h1']}/{n_ans} | {s['h3']}/{n_ans} | {s['h3n']}/{n_ans} | "
                     f"{s['blocked']}/{n_none} | {s['th']} | {s['ms']:.0f} ms |")
    win = max(summary, key=lambda x: (x['h1'] + x['h3'] + x['blocked'], x['h1'], x['blocked']))
    lines += ['', f"**Use {win['model']}** with ALPHA={win['alpha']} and THRESHOLD={win['th']} "
                  '(copy both into retrieval.py).', '', 'Every question: retrieval_results.csv']
    open('retrieval_report.md', 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n' + '\n'.join(lines))


if __name__ == '__main__':
    main()
