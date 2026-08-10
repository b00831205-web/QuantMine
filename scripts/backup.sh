#!/usr/bin/env bash
# quantmine 数据库每日备份（在 WSL Ubuntu 内运行，由 Windows 计划任务调起）。
#
#   wsl -d Ubuntu -e bash /mnt/e/.../scripts/backup.sh
#
# 以 .env 里的应用角色连接，不需要 sudo，所以可无人值守运行。该角色对所有表有
# SELECT，数据/结构/序列都能导全；ownership 与 ACL 不完整（要完整需超级用户导），
# 对"防丢数据"这个目的足够。
#
# 环境变量：
#   QUANTMINE_BACKUP_DIR    备份目录，默认 /mnt/e/pgbackup（放 Windows 盘，刻意不与
#                           数据同处一块 WSL 虚拟磁盘）
#   QUANTMINE_BACKUP_KEEP   保留份数，默认 14
#
# 关键约束：**先验证新备份，验证通过才轮转旧备份**。否则一次失败的 dump 会把仅有的
# 好备份挤掉——备份系统最经典的自杀方式。
#
# ---------------------------------------------------------------------------
# 注册为 Windows 每日计划任务（PowerShell，不需要管理员）：
#
#   $cmd = 'wsl.exe -d Ubuntu -e bash <REPO>/scripts/backup.sh > E:\pgbackup\task-stdout.log 2>&1'
#   $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c $cmd"
#   $trigger = New-ScheduledTaskTrigger -Daily -At '12:30'
#   $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
#       -DontStopIfGoingOnBatteries -StartWhenAvailable `
#       -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
#   Register-ScheduledTask -TaskName 'quantmine-db-backup' -Action $action `
#       -Trigger $trigger -Settings $settings
#
# ⚠️ -AllowStartIfOnBatteries / -DontStopIfGoingOnBatteries 不能省。
# New-ScheduledTaskSettingsSet 默认 DisallowStartIfOnBatteries=True，笔记本不插电时
# 任务会永远卡在 State=Queued 从不执行，而 LastTaskResult 仍是 0——看起来一切正常，
# 实际一次都没跑过。2026-08-10 实测踩到。
#
# 套一层 cmd.exe 重定向是为了捕获 wsl.exe 本身的失败（那类错误进不了 backup.log）。
# 排查顺序：Get-ScheduledTaskInfo → E:\pgbackup\task-stdout.log → $DEST/backup.log。
# ---------------------------------------------------------------------------
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEST=${QUANTMINE_BACKUP_DIR:-/mnt/e/pgbackup}
KEEP=${QUANTMINE_BACKUP_KEEP:-14}
MIN_BYTES=${QUANTMINE_BACKUP_MIN_BYTES:-1048576}
MIN_TABLES=${QUANTMINE_BACKUP_MIN_TABLES:-19}

mkdir -p "$DEST" || { echo "cannot create backup dir: $DEST" >&2; exit 1; }
LOG=$DEST/backup.log

log() { printf '%s  %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG"; }
die() { log "FAIL: $*"; exit 1; }

log "--- backup start (root=$ROOT dest=$DEST keep=$KEEP)"

# 1) 连接串（.env 存的是 SQLAlchemy 形式，psql/pg_dump 不认 +psycopg2）
[ -f "$ROOT/.env" ] || die ".env not found at $ROOT/.env"
URL=$(grep '^QUANTMINE_DATABASE_URL=' "$ROOT/.env" | cut -d= -f2- | sed 's/+psycopg2//')
[ -n "$URL" ] || die "QUANTMINE_DATABASE_URL missing from $ROOT/.env"

# 2) 等 Postgres 就绪：计划任务可能在 WSL 冷启动瞬间触发，systemd 拉起 postgresql
#    需要几秒
ready=no
for _ in $(seq 1 30); do
    if pg_isready -q -d "$URL"; then ready=yes; break; fi
    sleep 2
done
[ "$ready" = yes ] || die "postgres not accepting connections after 60s"

# 3) 导到 .partial，验证通过再改名转正
STAMP=$(date +%F_%H%M)
TMP=$DEST/.quantmine_$STAMP.dump.partial
OUT=$DEST/quantmine_$STAMP.dump

pg_dump "$URL" -Fc -f "$TMP" || { rm -f "$TMP"; die "pg_dump exited nonzero"; }

SIZE=$(stat -c %s "$TMP" 2>/dev/null || echo 0)
[ "$SIZE" -ge "$MIN_BYTES" ] || { rm -f "$TMP"; die "dump only $SIZE bytes (< $MIN_BYTES)"; }

pg_restore -l "$TMP" >/dev/null 2>&1 || { rm -f "$TMP"; die "dump unreadable by pg_restore"; }

TABLES=$(pg_restore -l "$TMP" | grep -c 'TABLE DATA')
[ "$TABLES" -ge "$MIN_TABLES" ] \
    || { rm -f "$TMP"; die "dump has $TABLES tables, expected >= $MIN_TABLES"; }

mv "$TMP" "$OUT" || { rm -f "$TMP"; die "could not finalize $OUT"; }
log "OK   $(basename "$OUT")  $(du -h "$OUT" | cut -f1)  tables=$TABLES"

# 4) 轮转（只有走到这里才会删旧备份）
ls -1t "$DEST"/quantmine_*.dump 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f "$old" && log "prune $(basename "$old")"
done

# 清掉历史遗留的 .partial（上次中断留下的）
find "$DEST" -maxdepth 1 -name '.quantmine_*.dump.partial' -mmin +120 -delete 2>/dev/null

log "--- backup done, $(ls -1 "$DEST"/quantmine_*.dump 2>/dev/null | wc -l) dumps retained"
