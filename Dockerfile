# syntax=docker/dockerfile:1
# PR-Robot — Production Dockerfile (Phase 8)
#
# Multi-stage build:
#   1) builder — ติดตั้ง Python Dependencies ลง Virtual Environment แยก
#   2) runtime — Image ที่ใช้จริง มีแค่ Runtime Libraries ที่จำเป็น (WeasyPrint ต้องใช้
#      Pango/GDK-Pixbuf) + fonts-noto-core (ฟอนต์ไทย จำเป็นสำหรับ PDF — ดู Open Item
#      ที่บันทึกไว้ตั้งแต่ Phase 5/7 ใน docs/00_KICKOFF_AND_DESIGN.md) + รันด้วย User
#      ที่ไม่ใช่ Root
#
# Build:   docker build -t pr-robot:latest .
# Run:     ดู docker-compose.prod.yml (ต้องมี .env จริงแยกต่างหาก ไม่ Commit ขึ้น Git)

ARG PYTHON_VERSION=3.11

# ---------- Stage 1: builder ----------
FROM python:${PYTHON_VERSION}-slim AS builder

# ไลบรารีที่จำเป็นตอน Build เท่านั้น (Compile บาง Python Package เช่น psycopg2-binary
# ปกติมี Wheel สำเร็จรูปอยู่แล้ว แต่กัน Fallback มา Build จาก Source ไว้)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:${PYTHON_VERSION}-slim AS runtime

# Runtime Libraries ที่ WeasyPrint ต้องใช้จริง (Pango สำหรับ Layout ข้อความ,
# GDK-Pixbuf สำหรับรูปภาพในเอกสาร, shared-mime-info สำหรับตรวจ Mime Type) +
# fonts-noto-core (ฟอนต์ไทย Noto Sans Thai — ยืนยันแล้วว่าจำเป็นตั้งแต่ Phase 5:
# ถ้าไม่มี PDF จะ Fallback ไป Font ที่ไม่รองรับภาษาไทยดีพอ) + curl (ใช้ใน HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-noto-core \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

# User ที่ไม่ใช่ Root สำหรับรัน Application (Security Review Item)
RUN groupadd --gid 1000 prrobot && useradd --uid 1000 --gid prrobot --shell /bin/bash --create-home prrobot

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# โฟลเดอร์เก็บไฟล์ที่ Upload/Generate จริง (Mount เป็น Volume แยกใน Compose)
RUN mkdir -p /app/storage/uploads /app/storage/generated \
    && chown -R prrobot:prrobot /app

USER prrobot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
