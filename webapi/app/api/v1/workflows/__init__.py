"""Airflow workflows 业务域。

数据来源：直接只读 Airflow 元数据库（SQLite，`airflow/airflow.db`）。
不经过 Airflow webserver / REST API，因此无需鉴权；代价是耦合 Airflow 内部表结构
（dag / dag_run / task_instance / dag_tag）。仅覆盖本项目实际用到的字段。
"""

from __future__ import annotations
