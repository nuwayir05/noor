# نور (Noor): رحلة تعلم قصيرة لكل سؤال

**Live demo:** https://nuwayir05-noor.hf.space  
**Track:** 03, interactive experiences and learning journeys (التجارب التفاعلية والرحلة المعرفية)  
**Team Mishkat (فريق مشكاة)** · AI Challenge for Serving Islamic Content 2026 · Bathel Foundation

> Noor turns a child's religious question into a short, interactive learning journey designed for children with
> attention difficulties (ADHD), ages 6–10. Answers come **only** from 64 passages approved by our Sharia reviewer;
> anything outside them is gently referred to the parent.

## The problem
A parent is asked «ليش نتوضأ؟» or «ليش نقول بسم الله؟». A long text answer or an open chatbot does not suit a child who
loses focus after a minute, and a general AI may invent religious content. Parents need short, trustworthy, engaging
answers, and to know where each answer came from.

## What Noor does
1. **The parent types the child's question** (any wording, Saudi dialect welcome).
2. **The AI checks it is safe and in scope**, finds the approved passage(s), and builds a learning pack.
3. **The child learns in small steps:** 3 short sentences at a time, then an active item (ordering game or question),
   a "try it now" activity, an illustrated mini-story as a reward, and stars.
4. **The parent sees** the exact sources (grade, reviewer, link), progress, and how the journey adapted.

## How the AI works (`ai/`)
| Step | What | Tool |
|---|---|---|
| 1 | Ready answers for 16 common questions (instant, reviewed) | cache |
| 2 | Scope check: is it one of the 5 approved topics? If not → referral | Claude Haiku 4.5 |
| 3 | Hybrid search over the **64 approved passages only** (meaning + Arabic spelling, dialect map) | BGE-M3 + char n-grams |
| 4 | Relevance check: do the passages really answer it? If not → referral | Claude Haiku 4.5 |
| 5 | Lesson builder: lesson, ordering game, two quiz levels, try-it, from those passages only | Claude Sonnet 5.5 |
| 6 | Code checks: every sentence must match words in the approved text; every quiz answer must be in what was taught | Python |
| 7 | Stories: written offline, checked by a second model, then approved by a person | Sonnet + Haiku + reviewer |

The AI never writes religious content from its own knowledge. Details: [`docs/CONTENT_SOURCES.md`](docs/CONTENT_SOURCES.md).

## How it adapts to the child (`src/engine/adaptive.ts`, `src/routes/session.$id.tsx`)
| Signal | What Noor does |
|---|---|
| Focus mode | At most 3 sentences in a row, then a game or question; never the same format 3 times in a row |
| "Next" pressed in under 2 s twice, or skipped twice | Shortens the explanation and switches to the game/questions |
| No touch for 15 s | Movement break (10-second countdown), then an active item instead of more reading |
| 3 answers slower than 10 s | Movement break |
| 2 correct in a row / 2 mistakes | Level 2 (harder questions, full game) / back to level 1 |
| Session time reached, very slow answers, or 2 breaks | Gentle ending: «بقي نشاط أخير», one easy question, then the reward |
| Engaged (no break, mostly correct) | Illustrated story as a reward |

Every decision is shown to the parent in Arabic («كيف تكيّفت الرحلة؟»). The engine is rule-based and runs in the browser.

## Privacy
No login, no accounts, no database. The child's name, age and progress stay in the browser (`localStorage`) and can be
deleted from Settings. Noor asks for **no diagnosis** and does not infer or classify religious or sensitive traits;
"focus mode" only changes the presentation. Questions are sent to the AI server only to build the answer.

## Run it locally
**AI server** (Python 3.11+):
```bash
cd ai
pip install -r requirements.txt
cp env.example .env          # then put your Anthropic API key in .env (never commit it)
python -m uvicorn server:app --port 8000
```
**Website** (Node 20+), in a second terminal:
```bash
npm install
npm run dev                  # http://localhost:8080 (talks to the AI on http://localhost:8000)
```
If the AI server is offline, the website still works for the suggested questions using `src/data/fallback-packs.json`.

**Online:** `npm run build`, copy `dist/client` to `ai/web`, and deploy `ai/` with `ai/Dockerfile`
(Hugging Face Space, port 7860; the API key is a Space secret). One link serves the website and the AI.

**Content tools:** `python ai/pregenerate.py` (rebuild the 16 ready answers + stories and the review page),
`python ai/fix_pack.py "<question>"` (rebuild one answer, keeping its story), `python ai/eval_retrieval.py` (search test).

## Project structure
```
ai/            AI server: prompts, retrieval, checks, pre-made packs, stories, voice
  noor_passages.json   the 64 approved passages
  packs/store.json     16 approved ready answers + 4 stories
src/           website (React + TanStack)
  routes/      pages: ask, processing, session (child), referral, parent dashboard, sources, settings
  engine/      adaptive engine
  data/        offline fallback answers
public/images/ the 16 story illustrations
docs/          content sources, tools and licenses
```

## Limits (honest)
- Covers 5 topics and 64 passages; everything else is referred to the parent by design.
- New questions take about 15–25 seconds; the 16 ready answers are instant.
- Usage limits protect the public demo: 15 questions per visitor per 10 minutes, 150 new lessons per day.
- The natural voice uses an online service; if it is unavailable, the browser's own Arabic voice is used.

## Credits
Sharia review: Dana Al-Qubaisi · Illustrations: Dana Al-Shehri · Tools and licenses: [`docs/TOOLS_AND_LICENSES.md`](docs/TOOLS_AND_LICENSES.md)
