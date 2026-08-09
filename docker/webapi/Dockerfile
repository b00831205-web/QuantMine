# webapi 镜像：FastAPI + uvicorn。构建上下文 = 仓库根（需要 quantmine 作为路径依赖）。
FROM python:3.13-slim

# WeasyPrint 需要的原生库（Pango/cairo/gdk-pixbuf/ffi）+ psql 客户端（entrypoint 探活用）
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        libffi8 shared-mime-info postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
# 先拷贝依赖清单以利用构建缓存；quantmine 是 webapi 的路径依赖（../）
COPY pyproject.toml README.md ./
COPY quantmine ./quantmine
COPY webapi ./webapi
COPY scripts ./scripts

WORKDIR /app/webapi
# 装 webapi 运行时 + psycopg2（--extra webapi），quantmine 以 editable 方式装入
RUN uv sync --extra webapi
ENV PATH="/app/webapi/.venv/bin:$PATH"

COPY docker/webapi/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
