# webapi 镜像：FastAPI + uvicorn。构建上下文 = 仓库根（需要 quantmine 作为路径依赖）。
FROM python:3.13-slim

# WeasyPrint 需要的原生库（Pango/cairo/gdk-pixbuf/ffi）+ psql 客户端（entrypoint 探活用）
#
# fonts-noto-cjk 不是可选项：python:3.13-slim 只带 DejaVu，没有任何汉字字形
# （容器里 `fc-list :lang=zh` 数量为 0）。报告模板要的是 "Noto Sans CJK SC"，
# 字体缺失时 WeasyPrint 会静默回退到 DejaVu，中文报告整页渲染成豆腐块——
# 接口照样 200、PDF 照样生成，只有打开看才发现。约 55 MB，是中文报告能用的
# 最低代价。
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
        libffi8 shared-mime-info postgresql-client fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
# 先拷贝依赖清单以利用构建缓存；quantmine 是 webapi 的路径依赖（../）
COPY pyproject.toml uv.lock README.md ./
COPY quantmine ./quantmine
COPY webapi ./webapi
COPY scripts ./scripts
COPY pipelines ./pipelines

# Keep Airflow in the root venv, matching the native WSL layout and the CLI
# paths used by the workflow API. Versions come from the committed root lock.
RUN uv sync --frozen --extra db --group pipeline --no-default-groups

WORKDIR /app/webapi
# 安装锁定的 webapi 运行时；quantmine 以 editable 路径依赖装入。
RUN uv sync --frozen
ENV PATH="/app/webapi/.venv/bin:$PATH"

COPY docker/webapi/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
