# Docker 一键部署

面向个人自托管：`docker compose up` 即得可登录、可用的完整应用。无需手动装
Postgres / 建角色 / 跑迁移 / 配 Airflow。

## 快速开始

```bash
cp .env.docker.example .env      # 改掉里面的密码和密钥（至少改一遍）
docker compose up -d
```

打开 <http://localhost:8080>，用 `.env` 里的 `QUANTMINE_ADMIN_USER` / `QUANTMINE_ADMIN_PASSWORD` 登录。

生成随机密钥：

```bash
python -c "import secrets;print(secrets.token_hex(32))"                       # QUANT_AUTH_SECRET
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"  # AIRFLOW_FERNET_KEY
```

## 服务与端口

| 服务 | 说明 | 端口 |
|---|---|---|
| `frontend` | Nginx 托管前端 + 反代 `/api` → webapi（同源，Cookie 可用） | 8080 |
| `webapi` | FastAPI 后端 | 内部 8000 |
| `postgres` | Postgres 16 + pgvector；首次启动自动建角色/库/扩展、应用 schema 与迁移、授权 | 5432 |
| `airflow` | Airflow 3.x standalone（调度 + 执行数据管线） | 8081（自带 UI，可选） |

首次 `up` 会构建镜像并初始化数据库，需要几分钟；之后启动很快。

## 只跑核心（不含 Airflow）

不需要数据管线时，省掉最重的 Airflow：

```bash
docker compose up -d postgres webapi frontend
```

登录、研究、报告、AI、数据速查页均正常；仅 Workflows 页无数据。

## 已知限制

- **Workflows 页的浏览**（DAG 列表/详情/图/时长）开箱可用（webapi 直接读 Airflow 元数据库）。
- **触发/暂停等写操作**依赖 Airflow CLI，当前 webapi 容器内未装 Airflow 二进制，这些按钮可能不生效。首次跑起来后如需要可再联系调整（改走 Airflow REST API 或在 webapi 镜像内装 CLI）。
- 新库是**空的**：研究/报告页需要先通过数据管线灌入行情与因子数据后才有内容。

## 常用命令

```bash
docker compose logs -f webapi        # 看后端日志
docker compose down                  # 停止（保留数据卷）
docker compose down -v               # 停止并删除数据（含数据库！慎用）
docker compose build --no-cache webapi   # 改了后端依赖后重建
```
