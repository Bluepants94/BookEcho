# 最小可运行占位 Dockerfile。
# 若 backend 业务侧后续提供更完整的 Dockerfile，请以其为准，避免覆盖复杂实现。
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/bookecho.db

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /data

# 优先使用 requirements.txt；若尚不存在则安装最小运行依赖
COPY requirements.txt* ./
RUN if [ -f requirements.txt ]; then \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.27" "python-jose[cryptography]" "passlib[bcrypt]" "sqlalchemy>=2.0" "pydantic-settings>=2.0"; \
    fi

COPY . .

EXPOSE 8000

# 兼容常见入口：main:app 或 app.main:app
CMD ["sh", "-c", "if [ -f app/main.py ]; then uvicorn app.main:app --host 0.0.0.0 --port 8000; else uvicorn main:app --host 0.0.0.0 --port 8000; fi"]
