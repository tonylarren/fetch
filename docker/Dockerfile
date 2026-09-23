FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=2 \
    FLAGS_use_mkldnn=1

# PaddleOCR needs these system libs even in headless mode
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 ccache curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir paddlepaddle -i https://www.paddlepaddle.org.cn/packages/stable/cpu/

# Bake the detection/recognition models into the image so the first request
# after a deploy isn't downloading ~100MB.
ARG OCR_LANG=fr
ENV OCR_LANG=${OCR_LANG}
COPY scripts/bake_models.py /tmp/bake_models.py
RUN python /tmp/bake_models.py && rm /tmp/bake_models.py

COPY app ./app
COPY scripts ./scripts

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
