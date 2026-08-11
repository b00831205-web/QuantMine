"""Airflow task-level write-operation helper (standalone script).

**必须用 Airflow 所在的 venv 运行**（本项目 = 项目根 `.venv`），不是 webapi 的 venv：
只有 Airflow 环境能正确通过 SQLAlchemy 写入元数据库（webapi venv 直连 sqlite 在
WSL drvfs 上会 "unable to open database file"）。Airflow CLI 没有 mark-success/
mark-failed 子命令，故用 Airflow 公共 API `set_state` / `clear_task_instances`。

用法：
    python _airflow_task_action.py <dag_id> <run_id> <task_id> <action>
    action ∈ {mark-success, mark-failed, clear}

数据库指向由环境变量控制（调用方设置）：
    AIRFLOW_HOME                                    读取 airflow.cfg
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN（可选）      覆盖目标库（demo 场景指向 /tmp 副本）

成功时向 stdout 打印一行 JSON：{"ok": true, "altered": <n>, "state": "<state>"}。
失败时非零退出，错误写 stderr。
"""

from __future__ import annotations

import json
import sys


def main() -> int:
    if len(sys.argv) != 5:
        sys.stderr.write("usage: <dag_id> <run_id> <task_id> <action>\n")
        return 2
    dag_id, run_id, task_id, action = sys.argv[1:5]

    from airflow.models.taskinstance import TaskInstance, clear_task_instances
    from airflow.utils.session import create_session
    from airflow.utils.state import TaskInstanceState

    with create_session() as session:
        tis = (
            session.query(TaskInstance)
            .filter(
                TaskInstance.dag_id == dag_id,
                TaskInstance.run_id == run_id,
                TaskInstance.task_id == task_id,
            )
            .all()
        )
        if not tis:
            sys.stderr.write(f"no task instance: {dag_id}/{run_id}/{task_id}\n")
            return 1

        if action == "clear":
            # 重置为可重跑；同时把该次 dag_run 置回 queued，交给调度器重新拉起。
            clear_task_instances(tis, session)
            session.commit()
            sys.stdout.write(json.dumps({"ok": True, "altered": len(tis), "state": None}) + "\n")
            return 0

        if action in ("mark-success", "mark-failed"):
            # 直接用 TI.set_state（模块级 set_state 在 DeltaTrigger 时间表上有内部 bug）。
            state = (
                TaskInstanceState.SUCCESS
                if action == "mark-success"
                else TaskInstanceState.FAILED
            )
            for ti in tis:
                ti.set_state(state, session)
            session.commit()
            sys.stdout.write(
                json.dumps({"ok": True, "altered": len(tis), "state": state.value}) + "\n"
            )
            return 0

    sys.stderr.write(f"unknown action: {action}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
