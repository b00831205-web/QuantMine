# webapi 镜像：FastAPI + uvicorn。构建上下文 = 仓库根（需要 quantmine 作为路径依赖）。
FROM python:3.13-slim

# WeasyPrint 需要的原生库（Pango/cairo/gdk-pixbuf/ffi）+ psql 客户端（entrypoint 探活用）
#
# fonts-noto-cjk 不是可选项：python:3.13-slim 只带 DejaVu，没有任何汉字字形
# （容器里 `fc-list :lang=zh` 数量为 0）。报告模板要的是 "Noto Sans CJK SC"，
# 字体缺失时 WeasyPrint 会静默回退到 DejaVu，中文报告整页渲染成豆腐块——
# 接口照样 200、PDF 照样生成，只有打开看才发现。约 55 MB，是中文报告能用的
# 最低代价。
#
# 分两步（先 -d 只下载、循环补齐，再从本地缓存装）是因为镜像站会对随机的少数
# 请求返 502。这一层要拉 60 多个包，单包按 5% 失败算，一次全中的概率不到 5%，
# 而 BuildKit 一失败整层缓存就丢——重试整个 build 是在重新掷骰子，可能永远不过。
# apt 自己的 Acquire::Retries 救不了：它只重试连接层失败，不重试 HTTP 错误码。
# /var/cache/apt/archives 在同一个 RUN 内是累积的，所以每轮只补上回没下到的，
# 几轮必然收敛。
ARG APT_DOWNLOAD_PASSES=8
RUN PKGS="libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 \
          libffi8 shared-mime-info postgresql-client fonts-noto-cjk" \
    && apt-get update \
    && n=0 \
    && until apt-get install -y --no-install-recommends -d $PKGS; do \
           n=$((n+1)); \
           if [ "$n" -ge "$APT_DOWNLOAD_PASSES" ]; then \
               echo "apt: still incomplete after $n download passes" >&2; exit 1; \
           fi; \
           echo "apt: download pass $n incomplete, retrying"; \
       done \
    && apt-get install -y --no-install-recommends $PKGS \
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
