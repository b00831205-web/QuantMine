# Airflow 镜像：与 webapi 镜像同源 —— 从仓库根 uv.lock 安装，使 Airflow 与
# quantmine 的依赖版本和开发环境（WSL 根 venv）完全一致。构建上下文 = 仓库根。
#
# 不再继承 apache/airflow 官方镜像。那条路要在官方已锁定的依赖集之上再
# `pip install quantmine`，而 quantmine 要求 fastapi>=0.136.3、pandas>=3.0，都高于
# 官方镜像自带的版本，pip 于是把 fastapi 顶到 0.141.1 —— 该版本下 cadwyn 的路由
# 生成会抛 RouteResponseBySchemaConverterDoesNotApplyToAnythingError，Execution API
# 对 PATCH task-instances/{id}/run 返回 500，worker 重试后被 SIGKILL，
# LocalExecutor 崩溃，任何任务都永远停在 queued。加 --constraint 也救不了：
# quantmine 的版本下限本就高于官方镜像，约束会直接解析失败。
FROM python:3.13-slim

RUN pip install --no-cache-dir uv

ENV AIRFLOW_HOME=/opt/airflow
WORKDIR /app

# 先拷依赖清单以利用构建缓存；quantmine 由 uv 以路径依赖装入根 venv。
COPY pyproject.toml uv.lock README.md ./
COPY quantmine ./quantmine
COPY scripts ./scripts

# data: DAG 任务用 yfinance/pandas-datareader 抓行情；db: sqlalchemy/psycopg2；
# pipeline: apache-airflow + asyncpg（Airflow 3 的异步元数据库引擎硬依赖）。
RUN uv sync --frozen --extra data --extra db --group pipeline --no-default-groups

# 让 `python` 与 `airflow` 都解析到根 venv：DAG 的 BashOperator 走
# "${QUANT_PYTHON_BIN:-.venv/bin/python}"，两种写法在此都成立。
ENV PATH="/app/.venv/bin:$PATH"

RUN mkdir -p "$AIRFLOW_HOME"

EXPOSE 8080
ENTRYPOINT ["airflow"]
