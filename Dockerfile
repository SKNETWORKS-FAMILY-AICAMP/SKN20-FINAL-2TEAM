# Python 3.11 버전 사용
FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc g++ default-libmysqlclient-dev pkg-config git libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 의존성 설치 (캐시 활용을 위해 코드보다 먼저)
COPY backend/requirements.txt /tmp/backend-req.txt
COPY rag/requirements.txt /tmp/rag-req.txt
COPY design/requirements.txt /tmp/design-req.txt
RUN pip install --no-cache-dir \
    -r /tmp/backend-req.txt \
    -r /tmp/rag-req.txt \
    -r /tmp/design-req.txt \
    && rm -f /tmp/*-req.txt

# 코드 복사
COPY backend/ /app/backend/
COPY rag/ /app/rag/
COPY design/ /app/design/
COPY FRONTEND/ /app/FRONTEND/

# 업로드 디렉토리 생성
RUN mkdir -p /app/backend/uploads

# backend 내부에서 from app.xxx 으로 import하므로 PYTHONPATH 추가
ENV PYTHONPATH="/app/backend:/app:${PYTHONPATH}"

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--app-dir", "/app/backend"]
