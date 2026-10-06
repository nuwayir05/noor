# Noor — AI server + website in one Hugging Face Space (free CPU: 2 vCPU, 16 GB RAM).
FROM python:3.11-slim

RUN useradd -m -u 1000 user && mkdir -p /home/user/app && chown -R user:user /home/user/app
ENV HOME=/home/user HF_HOME=/home/user/.cache/huggingface PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# CPU-only PyTorch first (much smaller than the default GPU build), then the rest.
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

USER user
# Download the search model (BAAI/bge-m3, ~2.3 GB) once, while building, so the app starts faster.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

COPY --chown=user . .
EXPOSE 7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
