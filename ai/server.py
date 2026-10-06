"""
Noor backend.

On the laptop (VS Code terminal):
    py -m uvicorn server:app --port 8000

Online (Hugging Face Space): the Dockerfile runs it on port 7860 and also serves the website from the web/ folder,
so the judges open ONE link. The API key comes from the Space's secret ANTHROPIC_API_KEY (never in the files).

  GET  /health  -> {"ok": true, "passages": 64, "premade": 16}
  POST /ask     {"question": "ليش نتوضأ؟", "age": 7}  -> the response shape in the website spec, section 9

Protection for a public link (anyone can open it, and new lessons cost API credit):
  - each visitor: at most PER_IP_LIMIT questions per 10 minutes
  - whole site: at most DAILY_NEW_LIMIT new (not pre-made) lessons per day; after that only ready answers are given
"""
import os, re, time, threading, hashlib
from collections import defaultdict, deque
from pathlib import Path

# optional .env file next to this script: ANTHROPIC_API_KEY=sk-ant-...   (never commit it)
_env = Path(__file__).with_name('.env')
if _env.exists():
    for line in _env.read_text(encoding='utf-8').splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import anthropic
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from retrieval import NoorRetriever
from pipeline import Noor, PackStore, response

MODEL = os.environ.get('NOOR_EMBED_MODEL', 'bge-m3')
PER_IP_LIMIT = int(os.environ.get('NOOR_PER_IP_LIMIT', '15'))        # questions per visitor per 10 minutes
DAILY_NEW_LIMIT = int(os.environ.get('NOOR_DAILY_NEW_LIMIT', '150'))  # new lessons (Sonnet) per day, whole site

app = FastAPI(title='Noor API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

print('Loading approved passages and the search model (first start takes ~1–2 min)…')
retriever = NoorRetriever('noor_passages.json', model=MODEL, approved_only=True)
store = PackStore('packs/store.json')
noor = Noor(anthropic.Anthropic(max_retries=4), retriever, store)
print(f'Ready: {len(retriever.passages)} approved passages, '
      f'{sum(1 for p in store.data["packs"].values() if p.get("premade"))} pre-made packs.')

_lock = threading.Lock()
_recent = defaultdict(deque)          # ip -> times of recent questions
_new_today = {'day': time.strftime('%Y-%m-%d'), 'count': 0}


def _visitor(request: Request):
    fwd = request.headers.get('x-forwarded-for', '')
    return fwd.split(',')[0].strip() or (request.client.host if request.client else '?')


def _too_many(ip):
    now = time.time()
    with _lock:
        q = _recent[ip]
        while q and now - q[0] > 600:
            q.popleft()
        if len(q) >= PER_IP_LIMIT:
            return True
        q.append(now)
        return False


def _new_allowed():
    with _lock:
        today = time.strftime('%Y-%m-%d')
        if _new_today['day'] != today:
            _new_today.update(day=today, count=0)
        return _new_today['count'] < DAILY_NEW_LIMIT


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)
    age: int = Field(default=7, ge=4, le=14)


@app.get('/health')
def health():
    return dict(ok=True, passages=len(retriever.passages),
                premade=sum(1 for p in store.data['packs'].values() if p.get('premade')))


@app.post('/ask')
def ask(body: AskIn, request: Request):
    t0 = time.time()
    if _too_many(_visitor(request)):
        return response('no_match', body.question, reason='أسئلة كثيرة في وقت قصير، جرّب بعد قليل')
    try:
        out = noor.ask(body.question, body.age, allow_new=_new_allowed())
        if out.get('status') == 'ok' and not out.get('cached'):
            with _lock:
                _new_today['count'] += 1
        return out
    except Exception as e:                         # never send a crash to the child's screen
        print(f'[error] {body.question}: {e}')
        return response('no_match', body.question, reason='حدث خلل مؤقت')
    finally:
        print(f'  ({time.time() - t0:.1f}s)')


# ---------------------------------------------------------------- natural Arabic voice for the "استمع" button
# Uses Microsoft's neural voices through the free edge-tts library. If it fails, the website falls back to the
# browser's own voice, so the button always works.
VOICE = os.environ.get('NOOR_VOICE', 'ar-SA-ZariyahNeural')     # warm female Saudi voice (male: ar-SA-HamedNeural)
_tts_cache, _tts_order = {}, deque()
_tts_recent = defaultdict(deque)


def _speakable(text):
    t = text.replace('ﷺ', ' صلى الله عليه وسلم ').replace('ﷻ', ' جل جلاله ')
    t = re.sub(r'[«»"()\[\]{}]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()[:500]


@app.get('/tts')
async def tts(text: str, request: Request):
    text = _speakable(text)
    if not text:
        return Response(status_code=204)
    key = hashlib.md5(text.encode()).hexdigest()
    if key not in _tts_cache:
        now, q = time.time(), _tts_recent[_visitor(request)]
        while q and now - q[0] > 600:
            q.popleft()
        if len(q) >= 80:
            return Response(status_code=429)
        q.append(now)
        try:
            import edge_tts
            audio = bytearray()
            async for chunk in edge_tts.Communicate(text, VOICE, rate='-8%').stream():
                if chunk['type'] == 'audio':
                    audio += chunk['data']
            if not audio:
                raise RuntimeError('no audio')
        except Exception as e:
            print(f'[tts error] {e}')
            return Response(status_code=503)
        _tts_cache[key] = bytes(audio); _tts_order.append(key)
        while len(_tts_order) > 400:
            _tts_cache.pop(_tts_order.popleft(), None)
    return Response(_tts_cache[key], media_type='audio/mpeg', headers={'Cache-Control': 'public, max-age=86400'})


# ---------------------------------------------------------------- the website (only if the web/ folder exists)
WEB = Path(__file__).with_name('web').resolve()
if (WEB / '_shell.html').exists():
    @app.get('/{path:path}', include_in_schema=False)
    def website(path: str):
        f = (WEB / path).resolve()
        if path and f.is_file() and WEB in f.parents:
            return FileResponse(f)
        if path.startswith('assets/') or path.startswith('images/'):
            return JSONResponse({'detail': 'not found'}, status_code=404)
        return FileResponse(WEB / '_shell.html')       # every page of the app (/ask, /session/…) loads the same shell
