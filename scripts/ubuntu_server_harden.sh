#!/usr/bin/env bash
# Ubuntu 生产机安全加固（Platform）
# 用法：sudo bash /data/Platform/scripts/ubuntu_server_harden.sh
set -euo pipefail

PLATFORM_ROOT="${PLATFORM_ROOT:-/data/Platform}"
MYSQL_CNF="${MYSQL_CNF:-/etc/mysql/mysql.conf.d/mysqld.cnf}"
SSH_DROPIN="/etc/ssh/sshd_config.d/99-platform-hardening.conf"
LOG_TAG="[platform-harden]"

log() { echo "${LOG_TAG} $*"; }
die() { echo "${LOG_TAG} ERROR: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "请使用 sudo 运行"

log "平台目录: ${PLATFORM_ROOT}"

# ---------- 1. 收紧敏感文件权限 ----------
if [[ -f "${PLATFORM_ROOT}/.env" ]]; then
  chmod 600 "${PLATFORM_ROOT}/.env"
  log "已设置 ${PLATFORM_ROOT}/.env -> 600"
fi

while IFS= read -r -d '' f; do
  chmod 600 "$f"
  log "已设置 $f -> 600"
done < <(find "${PLATFORM_ROOT}" \( -name '*.key' -o -name '*.pem' \) -type f -print0 2>/dev/null || true)

# ---------- 2. MySQL 仅监听本机 ----------
if [[ ! -f "${MYSQL_CNF}" ]]; then
  die "未找到 MySQL 配置: ${MYSQL_CNF}"
fi

cp -a "${MYSQL_CNF}" "${MYSQL_CNF}.bak.$(date +%Y%m%d%H%M%S)"

set_mysql_var() {
  local key="$1"
  local val="$2"
  if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "${MYSQL_CNF}"; then
    sed -i "s/^[[:space:]]*${key}[[:space:]]*=.*/${key} = ${val}/" "${MYSQL_CNF}"
  else
    printf '\n%s = %s\n' "${key}" "${val}" >> "${MYSQL_CNF}"
  fi
}

set_mysql_var "bind-address" "127.0.0.1"
if grep -qE '^[[:space:]]*mysqlx-bind-address' "${MYSQL_CNF}"; then
  set_mysql_var "mysqlx-bind-address" "127.0.0.1"
fi

log "MySQL bind-address 已设为 127.0.0.1"
systemctl restart mysql
sleep 2
systemctl is-active --quiet mysql || die "MySQL 重启失败，请检查 ${MYSQL_CNF}"

if ss -tlnp | grep ':3306' | grep -qv '127.0.0.1:3306'; then
  log "警告: 3306 仍监听非本机地址，请手动检查 mysqld 配置"
else
  log "MySQL 仅监听 127.0.0.1:3306"
fi

# 本机连通性
if command -v mysqladmin >/dev/null 2>&1; then
  mysqladmin ping -h 127.0.0.1 --silent && log "mysqladmin ping 127.0.0.1 成功"
fi

# ---------- 3. UFW 关闭公网 3306 ----------
if command -v ufw >/dev/null 2>&1; then
  while ufw status numbered 2>/dev/null | grep -qE '3306'; do
    num=$(ufw status numbered | grep -E '3306' | head -1 | sed -n 's/^\[\([0-9]*\)\].*/\1/p')
    [[ -n "${num}" ]] || break
    ufw --force delete "${num}" >/dev/null
    log "已删除 UFW 规则 #${num} (3306)"
  done
  ufw delete allow 3306/tcp 2>/dev/null || true
  ufw reload
  log "UFW 已重载（3306 不再对公网放行）"
fi

# ---------- 4. SSH 基础加固（保留密码登录，避免锁死） ----------
mkdir -p /etc/ssh/sshd_config.d
cat > "${SSH_DROPIN}" <<'EOF'
# Platform 安全加固 - 保留 PasswordAuthentication 供现有运维使用
PermitRootLogin no
MaxAuthTries 5
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
EOF

if sshd -t 2>/dev/null; then
  systemctl reload ssh || systemctl reload sshd || true
  log "SSH 配置已重载 (PermitRootLogin no)"
else
  log "警告: sshd -t 校验失败，已跳过 SSH 重载，请检查 ${SSH_DROPIN}"
fi

# ---------- 5. fail2ban（SSH 防暴力破解） ----------
if ! command -v fail2ban-client >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq fail2ban
fi

mkdir -p /etc/fail2ban/jail.d
cat > /etc/fail2ban/jail.d/platform-sshd.local <<'EOF'
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 5
findtime = 600
bantime = 3600
EOF

systemctl enable fail2ban >/dev/null 2>&1 || true
systemctl restart fail2ban
fail2ban-client status sshd >/dev/null 2>&1 && log "fail2ban sshd 已启用" || log "fail2ban 已安装，请执行 fail2ban-client status 确认"

# ---------- 6. 汇总 ----------
log "========== 加固完成 =========="
log "Navicat: 请继续使用 SSH 隧道，常规主机填 127.0.0.1:3306"
log "公网直连 3306 将不可用（符合预期）"
ss -tlnp | grep -E ':22|:3306|:6379|:8960' || true
ufw status 2>/dev/null | head -20 || true
