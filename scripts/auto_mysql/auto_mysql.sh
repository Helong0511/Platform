#!/usr/bin/env bash
#
# auto_mysql.sh
# 完整生产级 MySQL 自动优化脚本（NO TLS/SSL）
# 用法：
#   sudo ./auto_mysql.sh              # dry-run（默认，仅显示变更）
#   sudo ./auto_mysql.sh --apply --yes  # 直接应用（自动备份 + 写入 + 重启 + 创建备份任务）
#
set -euo pipefail

# -----------------------
# 参数解析
# -----------------------
APPLY=false
AUTO_YES=false
BIND_ALL=false
BACKUP_DAYS=7
OUT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=true; shift;;
    --yes) AUTO_YES=true; shift;;
    --bind-all) BIND_ALL=true; shift;;
    --backup-days) BACKUP_DAYS="$2"; shift 2;;
    --out) OUT_PATH="$2"; shift 2;;
    -h|--help)
      cat <<USAGE
用法:
  sudo $0 [--apply] [--yes] [--bind-all] [--backup-days N] [--out PATH]

选项:
  --apply        : 写入并重启 MySQL（默认 dry-run，仅预览）
  --yes          : 非交互自动确认所有步骤（慎用）
  --bind-all     : 在生成配置中设置 bind-address = 0.0.0.0（请确保防火墙）
  --backup-days N: 备份保留天数（默认 7）
  --out PATH     : 自定义输出生产配置片段路径
USAGE
      exit 0;;
    *) echo "未知参数: $1"; exit 2;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "[ERROR] 请用 root 或 sudo 运行此脚本"
  exit 1
fi

TS=$(date +%F_%H%M%S)
LOG="/var/log/auto_mysql_${TS}.log"
exec 3>&1
exec 1>>"${LOG}" 2>&1

log(){ printf "[%s] %s\n" "$(date '+%F %T')" "$*" >&3; }
die(){ printf "[%s] ERROR: %s\n" "$(date '+%F %T')" "$*" >&3; exit 1; }

log "开始 auto_mysql.sh（NO TLS）"
log "选项: APPLY=${APPLY}, AUTO_YES=${AUTO_YES}, BIND_ALL=${BIND_ALL}, BACKUP_DAYS=${BACKUP_DAYS}, OUT_PATH=${OUT_PATH:-(auto)}"

# -----------------------
# 1. 检测系统类型与 MySQL 服务名
# -----------------------
OS_ID=""
OS_PRETTY=""
if [ -f /etc/os-release ]; then
  . /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_PRETTY="${PRETTY_NAME:-$OS_ID}"
else
  OS_ID=$(uname -s)
  OS_PRETTY="$OS_ID"
fi

case "$OS_ID" in
  ubuntu|debian) MYSQL_SVC="mysql"; DEFAULT_OUT="/etc/mysql/mysql.conf.d/99-production.cnf"; CONF_CAND=(/etc/mysql /etc/mysql/mysql.conf.d /etc/mysql/conf.d) ;;
  centos|rhel|rocky|almalinux|amzn) MYSQL_SVC="mysqld"; DEFAULT_OUT="/etc/my.cnf.d/99-production.cnf"; CONF_CAND=(/etc /etc/my.cnf.d /etc/mysql) ;;
  *) MYSQL_SVC="mysql"; DEFAULT_OUT="/etc/mysql/99-production.cnf"; CONF_CAND=(/etc/mysql /etc);;
esac

log "系统: ${OS_PRETTY} (id=${OS_ID}), 假定 MySQL service 名称: ${MYSQL_SVC}"

# -----------------------
# 2. 检查 MySQL 是否已安装并获取版本
# -----------------------
if ! command -v mysql >/dev/null 2>&1; then
  die "未检测到 mysql 客户端，请先安装 MySQL"
fi
MYSQL_VERSION=$(mysql -V 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i~/^[0-9]+\.[0-9]+\.[0-9]+/) {print $i; exit}}' || true)
log "检测到 MySQL 版本: ${MYSQL_VERSION:-unknown}"

# -----------------------
# 3. 查找主配置 my.cnf 与 include 文件
# -----------------------
MYCNF=""
cands=( /etc/mysql/my.cnf /etc/my.cnf /etc/mysql/mysql.conf.d/mysqld.cnf /etc/my.cnf.d/server.cnf )
for p in "${cands[@]}"; do
  if [ -f "$p" ]; then MYCNF="$p"; break; fi
done

if [ -z "$MYCNF" ]; then
  # 尝试从 mysql --help 获取默认文件列表
  if mysql --help 2>/dev/null | grep -q "Default options are read from"; then
    # best-effort parsing
    default_list=$(mysql --help 2>/dev/null | sed -n '1,120p' | tr -d '\r' | awk '/my.cnf/ {print $0}' || true)
    for f in $default_list; do
      if [ -f "$f" ]; then MYCNF="$f"; break; fi
    done
  fi
fi

if [ -z "$MYCNF" ]; then
  found=$(find /etc -maxdepth 3 -type f \( -name 'my.cnf' -o -name 'mysqld.cnf' \) 2>/dev/null | head -n1 || true)
  [ -n "$found" ] && MYCNF="$found"
fi

if [ -z "$MYCNF" ]; then
  log "未找到主 my.cnf，脚本将继续生成片段到 ${DEFAULT_OUT}（某些原路径可能无法读取）"
else
  log "主配置文件: ${MYCNF}"
fi

# 目标输出文件
OUT_FILE="${OUT_PATH:-$DEFAULT_OUT}"
log "生成目标片段: ${OUT_FILE}"

# -----------------------
# 4. 收集配置文件列表（主配置 + include）并提取路径
# -----------------------
cfg_files=()
if [ -n "$MYCNF" ]; then
  cfg_files+=( "$MYCNF" )
  includes=$(awk 'tolower($0) ~ /!includedir/ {print $2} tolower($0) ~ /!include/ {print $2}' "$MYCNF" 2>/dev/null || true)
  for inc in $includes; do
    if [ -d "$inc" ]; then
      while IFS= read -r f; do [ -f "$f" ] && cfg_files+=( "$f" ); done < <(find "$inc" -maxdepth 1 -type f -name '*.cnf' 2>/dev/null | sort)
    elif [ -f "$inc" ]; then
      cfg_files+=( "$inc" )
    fi
  done
fi

for d in /etc/mysql/mysql.conf.d /etc/my.cnf.d /etc/mysql/conf.d; do
  if [ -d "$d" ]; then
    while IFS= read -r f; do cfg_files+=( "$f" ); done < <(find "$d" -maxdepth 1 -type f -name '*.cnf' 2>/dev/null | sort)
  fi
done

# 去重
if [ ${#cfg_files[@]} -gt 0 ]; then
  mapfile -t cfg_files < <(printf "%s\n" "${cfg_files[@]}" | awk '!x[$0]++')
fi

log "将扫描的配置文件: ${cfg_files[*]:-(none)}"

get_param_from_files(){
  local param="$1"
  for f in "${cfg_files[@]}"; do
    val=$(awk -F= -v p="$param" 'BEGIN{IGNORECASE=1} {gsub(/^[ \t]+|[ \t]+$/,"",$0); if ($0 ~ "^#") next; split($0,a,"="); if (tolower(a[1])==tolower(p)) {gsub(/^[ \t]+|[ \t]+$/,"",a[2]); print a[2]; exit}}' "$f" 2>/dev/null || true)
    if [ -n "$val" ]; then echo "$val"; return 0; fi
  done
  echo ""
  return 1
}

orig_datadir=$(get_param_from_files datadir)
orig_socket=$(get_param_from_files socket)
orig_pidfile=$(get_param_from_files "pid-file")
orig_logerror=$(get_param_from_files "log-error")
orig_bind=$(get_param_from_files "bind-address")

[ -z "$orig_datadir" ] && orig_datadir="/var/lib/mysql"
[ -z "$orig_socket" ] && orig_socket="/var/run/mysqld/mysqld.sock"
[ -z "$orig_pidfile" ] && orig_pidfile="/var/run/mysqld/mysqld.pid"
[ -z "$orig_logerror" ] && orig_logerror="/var/log/mysql/error.log"

log "提取到的路径: datadir=${orig_datadir}, socket=${orig_socket}, pid-file=${orig_pidfile}, log-error=${orig_logerror}, bind-address=${orig_bind:-(none)}"

# -----------------------
# 5. 硬件检测 (内存/CPU/根分区类型)
# -----------------------
MEM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo || echo 0)
MEM_BYTES=$(( MEM_KB * 1024 ))
MEM_GB=$(awk "BEGIN{printf \"%.2f\", $MEM_BYTES/1024/1024/1024}")
CPU_CORES=$(nproc || echo 1)

ROOT_SRC=$(df / | tail -1 | awk '{print $1}' || true)
DEVNAME=$(basename "$ROOT_SRC" | sed -E 's/[0-9]+$//')
DISK_TYPE="unknown"
if [ -r "/sys/block/${DEVNAME}/queue/rotational" ]; then
  if [ "$(cat /sys/block/${DEVNAME}/queue/rotational)" -eq 0 ]; then
    if [[ "$DEVNAME" =~ ^nvme ]]; then DISK_TYPE="NVMe"; else DISK_TYPE="SSD"; fi
  else
    DISK_TYPE="HDD"
  fi
else
  if command -v lsblk >/dev/null 2>&1; then
    maybe=$(lsblk -ndo NAME,ROTA | awk '$2==0{print $1; exit}' || true)
    if [[ "$maybe" == nvme* ]]; then DISK_TYPE="NVMe"; else DISK_TYPE="SSD"; fi
  fi
fi

log "硬件检测: 内存=${MEM_GB}GB, CPU=${CPU_CORES} 核, 根分区磁盘类型=${DISK_TYPE} (device=${DEVNAME})"

# -----------------------
# 6. 尝试读取运行时变量（若 MySQL 正在运行）
# -----------------------
MYSQL_RUNNING=false
if systemctl is-active --quiet "${MYSQL_SVC}" 2>/dev/null; then
  MYSQL_RUNNING=true
  log "MySQL 服务 ${MYSQL_SVC} 正在运行"
else
  log "MySQL 服务 ${MYSQL_SVC} 未运行（或 systemd 无法检测），将基于文件与硬件生成建议"
fi

MYSQL_CLI="mysql -N -s -e"
if [ -f /etc/mysql/debian.cnf ]; then
  MYSQL_CLI="mysql --defaults-file=/etc/mysql/debian.cnf -N -s -e"
elif [ -S "$orig_socket" ]; then
  MYSQL_CLI="mysql -S $orig_socket -uroot -N -s -e"
fi

get_mysql_var(){
  local v="$1"
  if $MYSQL_CLI "SHOW GLOBAL VARIABLES LIKE '${v}'" >/dev/null 2>&1; then
    $MYSQL_CLI "SHOW GLOBAL VARIABLES LIKE '${v}'" | awk '{print $2}'
  else
    echo ""
  fi
}

OLD_BP=""
OLD_LOGFILE=""
OLD_MAX_CONN=""
OLD_IO_CAP=""
if [ "$MYSQL_RUNNING" = true ]; then
  OLD_BP=$(get_mysql_var innodb_buffer_pool_size || true)
  OLD_LOGFILE=$(get_mysql_var innodb_log_file_size || true)
  OLD_MAX_CONN=$(get_mysql_var max_connections || true)
  OLD_IO_CAP=$(get_mysql_var innodb_io_capacity || true)
fi
log "运行时样本: innodb_buffer_pool_size=${OLD_BP:-(无)}, innodb_log_file_size=${OLD_LOGFILE:-(无)}, max_connections=${OLD_MAX_CONN:-(无)}, innodb_io_capacity=${OLD_IO_CAP:-(无)}"

# -----------------------
# 7. 计算推荐值（生产优先）
# -----------------------
if awk "BEGIN{exit !($MEM_BYTES >= 32*1024*1024*1024)}"; then BPCT=0.75
elif awk "BEGIN{exit !($MEM_BYTES >= 8*1024*1024*1024)}"; then BPCT=0.70
elif awk "BEGIN{exit !($MEM_BYTES >= 2*1024*1024*1024)}"; then BPCT=0.65
else BPCT=0.60
fi

INNODB_BUFFER_BYTES=$(awk "BEGIN{printf \"%d\", $MEM_BYTES * $BPCT}")
[ "$INNODB_BUFFER_BYTES" -lt $((128*1024*1024)) ] && INNODB_BUFFER_BYTES=$((128*1024*1024))
if command -v numfmt >/dev/null 2>&1; then
  INNODB_BUFFER_H=$(numfmt --to=iec --suffix=B $INNODB_BUFFER_BYTES)
else
  INNODB_BUFFER_H="${INNODB_BUFFER_BYTES}"
fi

INNODB_LOG_BYTES=$(awk "BEGIN{printf \"%d\", $INNODB_BUFFER_BYTES/4}")
[ "$INNODB_LOG_BYTES" -gt $((2*1024*1024*1024)) ] && INNODB_LOG_BYTES=$((2*1024*1024*1024))
if command -v numfmt >/dev/null 2>&1; then
  INNODB_LOG_H=$(numfmt --to=iec --suffix=B $INNODB_LOG_BYTES)
else
  INNODB_LOG_H="${INNODB_LOG_BYTES}"
fi

MAX_CONNECTIONS=$((150 + CPU_CORES * 50))
[ "$MAX_CONNECTIONS" -gt 5000 ] && MAX_CONNECTIONS=5000
THREAD_CACHE=$(( CPU_CORES * 4 ))
[ "$THREAD_CACHE" -lt 8 ] && THREAD_CACHE=8

if awk "BEGIN{exit !($MEM_BYTES >= 32*1024*1024*1024)}"; then TABLE_OPEN_CACHE=4000
elif awk "BEGIN{exit !($MEM_BYTES >= 8*1024*1024*1024)}"; then TABLE_OPEN_CACHE=2000
else TABLE_OPEN_CACHE=1024
fi

case "$DISK_TYPE" in
  NVMe) IO_CAP=8000; IO_CAP_MAX=20000;;
  SSD)  IO_CAP=2000; IO_CAP_MAX=6000;;
  HDD)  IO_CAP=200;  IO_CAP_MAX=400;;
  *)    IO_CAP=200;  IO_CAP_MAX=400;;
esac

TMP_TABLE_SIZE="64M"
MAX_HEAP_TABLE_SIZE="64M"

log "计算结果: innodb_buffer_pool_size=${INNODB_BUFFER_H}, innodb_log_file_size=${INNODB_LOG_H}, max_connections=${MAX_CONNECTIONS}, innodb_io_capacity=${IO_CAP}"

# -----------------------
# 8. 生成配置片段
# -----------------------
GEN_CONTENT=$(cat <<EOF
# 99-production.cnf - generated by auto_mysql.sh (NO TLS)
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ") UTC
# System: ${OS_PRETTY}, Memory=${MEM_GB}GB, CPU=${CPU_CORES}, Disk=${DISK_TYPE}
#
[mysqld]

# preserve paths
datadir = ${orig_datadir}
socket = ${orig_socket}
pid-file = ${orig_pidfile}
log-error = ${orig_logerror}

character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
skip-character-set-client-handshake = 1

# networking
max_connections = ${MAX_CONNECTIONS}    # original: ${OLD_MAX_CONN:-(none)}
thread_cache_size = ${THREAD_CACHE}
open_files_limit = 65535
back_log = 512

# InnoDB
innodb_buffer_pool_size = ${INNODB_BUFFER_H}   # original(runtime/config): ${OLD_BP:-(none)}
innodb_buffer_pool_instances =  $(awk "BEGIN{if(${INNODB_BUFFER_BYTES}/1024/1024/1024>=8) print 8; else if(${INNODB_BUFFER_BYTES}/1024/1024/1024>=2) print int(${INNODB_BUFFER_BYTES}/1024/1024/1024); else print 1}")
innodb_log_file_size = ${INNODB_LOG_H}        # original(runtime/config): ${OLD_LOGFILE:-(none)}
innodb_log_files_in_group = 2
innodb_file_per_table = 1
innodb_flush_method = O_DIRECT
innodb_flush_log_at_trx_commit = 1
innodb_io_capacity = ${IO_CAP}
innodb_io_capacity_max = ${IO_CAP_MAX}

# tmp tables & caches
tmp_table_size = ${TMP_TABLE_SIZE}
max_heap_table_size = ${MAX_HEAP_TABLE_SIZE}
table_open_cache = ${TABLE_OPEN_CACHE}
table_definition_cache = 2000

# logging
slow_query_log = 1
slow_query_log_file = /var/log/mysql/mysql-slow.log
long_query_time = 1
log_error = ${orig_logerror}

# binlog
server-id = 1
log_bin = /var/log/mysql/mysql-bin
binlog_format = ROW
expire_logs_days = ${BACKUP_DAYS}
binlog_expire_logs_seconds = $(( BACKUP_DAYS * 24 * 3600 ))
sync_binlog = 1

# security
local_infile = 0
secure_file_priv = NULL

EOF
)

if [ "$BIND_ALL" = true ]; then
  GEN_CONTENT="${GEN_CONTENT}\nbind-address = 0.0.0.0\n"
else
  if [ -n "$orig_bind" ]; then
    GEN_CONTENT="${GEN_CONTENT}\n# bind-address preserved in main config: ${orig_bind}\n"
  else
    GEN_CONTENT="${GEN_CONTENT}\n# Recommended bind-address = 127.0.0.1 for local-only setups\n"
  fi
fi

WORKDIR="/tmp/auto_mysql_${TS}"
mkdir -p "$WORKDIR"
TEMP_OUT="${WORKDIR}/99-production.cnf"
printf "%s\n" "$GEN_CONTENT" > "$TEMP_OUT"
chmod 644 "$TEMP_OUT"

log "生成的配置片段在: ${TEMP_OUT}"
sed -n '1,200p' "$TEMP_OUT" >&3

# -----------------------
# 9. 显示差异（如目标已存在）
# -----------------------
if [ -f "$OUT_FILE" ]; then
  log "目标 ${OUT_FILE} 已存在，显示差异 (old <- new):"
  if command -v diff >/dev/null 2>&1; then
    diff -u "$OUT_FILE" "$TEMP_OUT" | sed 's/^/    /' >&3 || true
  fi
else
  log "目标 ${OUT_FILE} 不存在，将创建"
fi

confirm_or_exit(){
  local prompt="$1"
  if [ "$AUTO_YES" = true ]; then
    log "AUTO_YES 已启用，自动确认"
    return 0
  fi
  read -p "$prompt [y/N]: " yn
  case "$yn" in [Yy]*) return 0;; *) return 1;; esac
}

if [ "$APPLY" = false ]; then
  log "当前为 dry-run 模式（未写入）。使用 --apply 来写入并重启 MySQL"
  cat <<SUMMARY >&3

SUMMARY (dry-run):
 - 生成片段: ${TEMP_OUT}
 - 目标路径: ${OUT_FILE}
 - 建议: innodb_buffer_pool_size=${INNODB_BUFFER_H}, innodb_log_file_size=${INNODB_LOG_H}, max_connections=${MAX_CONNECTIONS}
 - 若满意请执行: sudo $0 --apply --yes
SUMMARY
  exit 0
fi

# -----------------------
# 10. APPLY: 备份并写入
# -----------------------
log "APPLY 模式: 备份并写入配置片段到 ${OUT_FILE}"
BACKUP_DIR="/etc/mysql/backup_${TS}"
mkdir -p "$BACKUP_DIR"

if [ -d /etc/mysql ]; then
  cp -a /etc/mysql "$BACKUP_DIR/" || true
fi
for f in /etc/my.cnf /etc/my.cnf.d /etc/mysql/mysql.conf.d /etc/mysql/conf.d; do
  if [ -e "$f" ]; then cp -a "$f" "$BACKUP_DIR/" 2>/dev/null || true; fi
done
log "已备份配置到: ${BACKUP_DIR}"

mkdir -p "$(dirname "$OUT_FILE")"
if [ -f "$OUT_FILE" ]; then
  cp -a "$OUT_FILE" "${OUT_FILE}.bak_${TS}"
  log "备份已有目标: ${OUT_FILE}.bak_${TS}"
fi
cp "$TEMP_OUT" "$OUT_FILE"
chmod 644 "$OUT_FILE"
chown root:root "$OUT_FILE"
log "已写入 ${OUT_FILE}"

# -----------------------
# 11. 创建备份脚本与 systemd timer
# -----------------------
BACKUP_SCRIPT="/usr/local/bin/mysql_auto_backup.sh"
BACKUP_DATA_DIR="/var/backups/mysql"
log "创建备份脚本 ${BACKUP_SCRIPT}，备份目录 ${BACKUP_DATA_DIR}，保留 ${BACKUP_DAYS} 天"

cat > "${BACKUP_SCRIPT}" <<'BKS'
#!/usr/bin/env bash
DAYS=${DAYS:-7}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/mysql}
mkdir -p "$BACKUP_DIR"
TS=$(date +%F_%H%M%S)
mysqldump --defaults-file=/root/.my.cnf --single-transaction --quick --routines --events --all-databases > "${BACKUP_DIR}/full_${TS}.sql" || exit 1
gzip -f "${BACKUP_DIR}/full_${TS}.sql"
find "${BACKUP_DIR}" -type f -mtime +${DAYS} -exec rm -f {} \;
BKS

sed -i "s/DAYS=\${DAYS:-7}/DAYS=${BACKUP_DAYS}/" "${BACKUP_SCRIPT}"
sed -i "s|BACKUP_DIR=\${BACKUP_DIR:-/var/backups/mysql}|BACKUP_DIR=${BACKUP_DATA_DIR}|" "${BACKUP_SCRIPT}"
chmod +x "${BACKUP_SCRIPT}"
chown root:root "${BACKUP_SCRIPT}"

cat > /etc/systemd/system/mysql-auto-backup.service <<'SVC'
[Unit]
Description=MySQL daily backup (auto-generated)

[Service]
Type=oneshot
ExecStart=/usr/local/bin/mysql_auto_backup.sh
SVC

cat > /etc/systemd/system/mysql-auto-backup.timer <<'TMR'
[Unit]
Description=Run MySQL auto backup daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
TMR

systemctl daemon-reload
systemctl enable --now mysql-auto-backup.timer || true
log "已启用 timer: mysql-auto-backup.timer"

# -----------------------
# 12. 创建备份用户与凭据 /root/.my.cnf
# -----------------------
log "创建备份用户 backup@localhost，并写入 /root/.my.cnf（权限 600）"
BACKUP_PASS=$(openssl rand -hex 20)
if [ -f /etc/mysql/debian.cnf ]; then
  mysql --defaults-file=/etc/mysql/debian.cnf -e "CREATE USER IF NOT EXISTS 'backup'@'localhost' IDENTIFIED BY '${BACKUP_PASS}'; GRANT SELECT, RELOAD, SHOW DATABASES, LOCK TABLES, REPLICATION CLIENT, EVENT, TRIGGER ON *.* TO 'backup'@'localhost'; FLUSH PRIVILEGES;" || true
else
  mysql -uroot -e "CREATE USER IF NOT EXISTS 'backup'@'localhost' IDENTIFIED BY '${BACKUP_PASS}'; GRANT SELECT, RELOAD, SHOW DATABASES, LOCK TABLES, REPLICATION CLIENT, EVENT, TRIGGER ON *.* TO 'backup'@'localhost'; FLUSH PRIVILEGES;" || true
fi

cat > /root/.my.cnf <<EOF
[client]
user=backup
password=${BACKUP_PASS}
EOF
chmod 600 /root/.my.cnf
chown root:root /root/.my.cnf
log "备份用户创建完成，凭据写入 /root/.my.cnf"

# -----------------------
# 13. 处理 innodb_log_file_size 变更：安全替换 ib_logfile*
# -----------------------
if [ -n "${OLD_LOGFILE}" ] && [ "${OLD_LOGFILE}" != "${INNODB_LOG_H}" ]; then
  log "检测到 innodb_log_file_size 需要变更: ${OLD_LOGFILE} -> ${INNODB_LOG_H}"
  cat <<WARN >&3
注意: 修改 innodb_log_file_size 需要停止 MySQL、备份 ib_logfile*、删除旧 ib_logfile*，然后启动 MySQL。
WARN

  if [ "${AUTO_YES}" = true ]; then
    log "AUTO_YES: 按安全步骤自动替换 ib_logfile*（将短暂停止 MySQL）"
    systemctl stop "${MYSQL_SVC}" || log "停止 MySQL 失败，继续"
    mkdir -p "${BACKUP_DIR}/ib_logfile_backup"
    cp -a /var/lib/mysql/ib_logfile* "${BACKUP_DIR}/ib_logfile_backup/" || true
    rm -f /var/lib/mysql/ib_logfile* || true
    systemctl start "${MYSQL_SVC}" || die "MySQL 启动失败，请检查日志"
    log "已完成 ib_logfile* 替换并重启 MySQL"
  else
    if confirm_or_exit "是否现在按安全步骤替换 ib_logfile*（会短暂停止 MySQL）?"; then
      systemctl stop "${MYSQL_SVC}" || log "停止 MySQL 失败，继续"
      mkdir -p "${BACKUP_DIR}/ib_logfile_backup"
      cp -a /var/lib/mysql/ib_logfile* "${BACKUP_DIR}/ib_logfile_backup/" || true
      rm -f /var/lib/mysql/ib_logfile* || true
      systemctl start "${MYSQL_SVC}" || die "MySQL 启动失败，请检查日志"
      log "已完成 ib_logfile* 替换并重启 MySQL"
    else
      log "用户选择不替换 ib_logfile*。请手动执行替换以使 innodb_log_file_size 生效。"
      systemctl restart "${MYSQL_SVC}" || log "重启 MySQL 失败"
    fi
  fi
else
  log "innodb_log_file_size 未变化或旧值不可用，重启 MySQL 以应用新片段"
  systemctl restart "${MYSQL_SVC}" || die "重启 MySQL 失败，请检查日志"
fi

# -----------------------
# 14. 总结
# -----------------------
log "优化完成，摘要："
cat <<SUMMARY >&3
已完成:
 - 原 /etc/mysql 等配置已备份到: ${BACKUP_DIR}
 - 生产片段已写入: ${OUT_FILE}
 - 建议 innodb_buffer_pool_size: ${INNODB_BUFFER_H}
 - 建议 innodb_log_file_size: ${INNODB_LOG_H}
 - 建议 max_connections: ${MAX_CONNECTIONS}
 - innodb_io_capacity: ${IO_CAP}
 - 备份脚本: ${BACKUP_SCRIPT}
 - systemd timer: mysql-auto-backup.timer
 - 备份账号: backup@localhost (凭据: /root/.my.cnf, mode 600)
 - SSL/TLS: 未配置 (按要求)
 - 请检查 MySQL 日志: sudo journalctl -u ${MYSQL_SVC} -n 200 --no-pager
SUMMARY

log "日志文件: ${LOG}"
log "脚本结束"
exit 0