"""
End-to-end retrieval test WITH the Haiku relevance check (needs your API key; ~65 Haiku calls ≈ $0.05–0.10).

  set ANTHROPIC_API_KEY first   (Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."   Mac: export ANTHROPIC_API_KEY=sk-ant-...)
  py test_relevance.py --model bge-m3
  py test_relevance.py --model bge-m3 --tests real_questions.csv

Reports:
  answered correctly  - a correct passage is among those Haiku kept
  wrongly refused     - answerable question but Haiku kept nothing
  no-answer refused   - 'expected: []' questions that correctly end as no_match  (the main goal)
  extra passages      - kept passages that were not in 'expected' (Sonnet may still use them sensibly)
"""
import argparse, csv, json, time
import anthropic
from retrieval import NoorRetriever
from relevance import retrieve_verified
from eval_retrieval import load_tests

ap = argparse.ArgumentParser()
ap.add_argument('--model', default='bge-m3'); ap.add_argument('--tests', default='test_questions.json')
a = ap.parse_args()

client = anthropic.Anthropic()
# fail loudly if Haiku can't be reached (otherwise relevance.py silently falls back to search results)
try:
    client.messages.create(model='claude-haiku-4-5-20251001', max_tokens=5,
                           messages=[{'role': 'user', 'content': 'قل: نعم'}])
    print('Haiku reachable: OK')
except Exception as e:
    raise SystemExit(f'\nHAIKU CALL FAILED, so the relevance check cannot run.\nReason: {e}\n'
                     'Check: is ANTHROPIC_API_KEY set in THIS terminal? Is the key complete? Does the account have credit?')
r = NoorRetriever(model=a.model, approved_only=False)
tests = load_tests(a.tests)
rows, t_total = [], 0.0
for t in tests:
    t0 = time.time()
    ctx = retrieve_verified(r, client, t['q'], t['topic'])
    dt = time.time() - t0; t_total += dt
    exp = set(t['expected'])
    kept = ctx['passage_ids']
    rows.append(dict(q=t['q'], topic=t['topic'], expected='|'.join(exp) or '(none)', kept='|'.join(kept),
                     status=ctx['status'], stage=ctx['stage'],
                     correct=(bool(exp) and bool(exp & set(kept))) or (not exp and ctx['status'] == 'no_match'),
                     reason=(ctx['relevance'] or {}).get('reason', ''), seconds=round(dt, 2)))
    if ctx['relevance'] and not ctx['relevance']['ok']:
        print('  !! relevance check failed for this question:', ctx['relevance']['reason'][:150])
    mark = 'OK ' if rows[-1]['correct'] else 'XX '
    print(f"{mark} {t['q'][:40]:<40} -> {ctx['status']:<8} {kept}")

ans = [x for x in rows if x['expected'] != '(none)']; none = [x for x in rows if x['expected'] == '(none)']
print(f"\nanswered correctly : {sum(x['correct'] for x in ans)}/{len(ans)}")
print(f"wrongly refused    : {sum(x['status'] == 'no_match' for x in ans)}/{len(ans)}")
print(f"no-answer refused  : {sum(x['correct'] for x in none)}/{len(none)}")
print(f"avg time           : {t_total/len(rows):.2f} s/question (search + Haiku)")
with open('relevance_results.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print('details: relevance_results.csv')
