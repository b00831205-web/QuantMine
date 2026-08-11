# Airflow 镜像：官方 airflow 3.x + 装入 quantmine（含 data/db 额外依赖），
# 使 DAG 任务脚本能 import quantmine。构建上下文 = 仓库根。
ARG AIRFLOW_VERSION=3.2.0
FROM apache/airflow:${AIRFLOW_VERSION}

COPY --chown=airflow:airflow pyproject.toml README.md /opt/quantmine/
COPY --chown=airflow:airflow quantmine /opt/quantmine/quantmine

# quantmine 的 pandas/numpy 版本与 airflow 3.2 在本项目根 venv 中已验证共存
RUN pip install --no-cache-dir "/opt/quantmine[data,db]"
