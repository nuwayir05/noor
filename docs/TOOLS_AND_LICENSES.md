# Tools, models, data and licenses — Noor

Required by the submission rules (component licenses and owners' rights).

## AI models and services
| Component | Used for | License / terms |
|---|---|---|
| Claude Haiku 4.5 (Anthropic API) | scope check, relevance check, story checker | Anthropic commercial terms (paid API; key kept in a private `.env` / Space secret, never in the repo) |
| Claude Sonnet 5.5 (Anthropic API) | building lessons and stories from approved passages only | Anthropic commercial terms |
| BAAI/bge-m3 (Hugging Face) | meaning search over the 64 approved passages | MIT |
| Microsoft Edge neural voice `ar-SA-ZariyahNeural` via `edge-tts` | the «استمع» button (natural Arabic voice) | `edge-tts` library: LGPL-3.0. Uses Microsoft's online read-aloud service; if unavailable, the website falls back to the browser's own voice |

## Content
| Source | License / rights |
|---|---|
| HadeethEnc.com — Encyclopedia of Translated Prophetic Hadiths (v1.7.0) | Text, grade and explanation used with source attribution and a link to the original page for every hadith |
| King Fahd Glorious Qur'an Printing Complex — Hafs text, Tafsir Muyassar | Qur'an text shown unchanged with its source |
| Sharia review | Dana Al-Qubaisi (team member) approved all 64 passages, the 16 pre-made answers and the 4 stories |
| Story illustrations (16 panels) | Made for this project by the team (Dana Al-Shehri) |
| Noor logo and owl | Made for this project by the team |

## Python (ai/)
| Package | License |
|---|---|
| fastapi | MIT |
| uvicorn | BSD-3-Clause |
| pydantic | MIT |
| anthropic (SDK) | MIT |
| sentence-transformers | Apache-2.0 |
| scikit-learn | BSD-3-Clause |
| numpy | BSD-3-Clause |
| json-repair | MIT |
| edge-tts | LGPL-3.0 |
| torch (CPU) | BSD-3-Clause |

## Website (src/)
| Package | License |
|---|---|
| React, React DOM | MIT |
| TanStack Router / Start | MIT |
| Vite | MIT |
| Tailwind CSS | MIT |
| Radix UI, shadcn/ui components | MIT |
| dnd-kit (drag and drop) | MIT |
| lucide-react (icons) | ISC |
| class-variance-authority | Apache-2.0 |
| IBM Plex Sans Arabic (Google Fonts) | SIL Open Font License 1.1 |

## Hosting
| Service | Used for |
|---|---|
| Hugging Face Spaces (Docker, CPU) | live demo: AI server + website on one link |
| GitHub | public source code |
