#!/usr/bin/env bash
# GAM 运行时目录权限修复（root 执行 git pull 后运行，避免密钥上传 Permission denied）
#
# 用法（在服务器上，无需改 systemd）：
#   cd /data/Platform && git pull
#   bash /data/Platform/scripts/ensure_gam_runtime_dirs.sh
#
# 手动指定运行用户（若自动识别不对）：
#   APP_USER=ubuntu bash /data/Platform/scripts/ensure_gam_runtime_dirs.sh
set -euo pipefail

PLATFORM_ROOT="${PLATFORM_ROOT:-/data/Platform}"
APP_USER="${APP_USER:-}"
LOG_TAG="[gam-dirs]"

log() { echo "${LOG_TAG} $*"; }
die() { echo "${LOG_TAG} ERROR: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "请使用 root 或 sudo 运行"

_detect_app_user() {
  local user=""

  # 1. 从正在运行的 uvicorn 进程识别（最准确，无需改 systemd）
  user="$(
    ps -eo user=,args= 2>/dev/null \
      | grep -E '[u]vicorn.*app\.main:app' \
      | grep -F "${PLATFORM_ROOT}" \
      | awk '{print $1}' \
      | head -1
  )"
  if [[ -n "${user}" && "${user}" != "root" ]]; then
    echo "${user}"
    return
  fi

  user="$(
    ps -eo user=,args= 2>/dev/null \
      | grep -E '[u]vicorn.*app\.main:app' \
      | awk '{print $1}' \
      | grep -v '^root$' \
      | head -1
  )"
  if [[ -n "${user}" ]]; then
    echo "${user}"
    return
  fi

  # 2. 从已有 systemd 单元读取 User=（只读，不要求你修改）
  local unit
  for unit in /etc/systemd/system/*.service; do
    [[ -f "${unit}" ]] || continue
    if grep -qF "${PLATFORM_ROOT}" "${unit}" 2>/dev/null && grep -qE '^User=' "${unit}"; then
      grep -E '^User=' "${unit}" | head -1 | cut -d= -f2-
      return
    fi
  done

  echo "ubuntu"
}

if [[ -z "${APP_USER}" ]]; then
  APP_USER="$(_detect_app_user)"
fi

id "${APP_USER}" >/dev/null 2>&1 || die "用户不存在: ${APP_USER}（可执行 APP_USER=xxx bash $0）"

SECRETS_DIR="${PLATFORM_ROOT}/secrets"
CONFIG_DIR="${PLATFORM_ROOT}/config"
CACHE_ROOT="${PLATFORM_ROOT}/.cache"
GAM_CACHE_DIR="${CACHE_ROOT}/gam"
GAM_CONFIG="${CONFIG_DIR}/gam_scheduler.json"

log "项目目录: ${PLATFORM_ROOT}"
log "运行用户: ${APP_USER}（自动识别，与 uvicorn 进程一致即可）"

install -d -o "${APP_USER}" -g "${APP_USER}" -m 750 "${SECRETS_DIR}"
install -d -o "${APP_USER}" -g "${APP_USER}" -m 750 "${CONFIG_DIR}"
install -d -o "${APP_USER}" -g "${APP_USER}" -m 750 "${CACHE_ROOT}"
install -d -o "${APP_USER}" -g "${APP_USER}" -m 750 "${GAM_CACHE_DIR}"

if [[ ! -f "${GAM_CONFIG}" ]]; then
  sudo -u "${APP_USER}" tee "${GAM_CONFIG}" >/dev/null <<'EOF'
{
  "version": 1,
  "description": "GAM 定时拉数账号与白名单配置",
  "accounts": []
}
EOF
  chmod 640 "${GAM_CONFIG}"
  log "已创建空配置: ${GAM_CONFIG}"
fi

chown "${APP_USER}:${APP_USER}" "${GAM_CONFIG}"
chmod 640 "${GAM_CONFIG}"

shopt -s nullglob
gam_files=("${SECRETS_DIR}"/gam-*.json)
if ((${#gam_files[@]})); then
  chown "${APP_USER}:${APP_USER}" "${gam_files[@]}"
  chmod 640 "${gam_files[@]}"
  log "已修复密钥文件权限: ${#gam_files[@]} 个"
else
  log "暂无 gam-*.json 密钥（可在管理端页面上传）"
fi

if sudo -u "${APP_USER}" test -w "${SECRETS_DIR}"; then
  log "secrets 目录可写，GAM 密钥上传应可正常使用"
else
  die "secrets 目录对 ${APP_USER} 仍不可写"
fi

if sudo -u "${APP_USER}" test -w "${GAM_CACHE_DIR}"; then
  log "GAM 缓存目录可写: ${GAM_CACHE_DIR}"
else
  die "GAM 缓存目录对 ${APP_USER} 不可写: ${GAM_CACHE_DIR}"
fi

log "完成（默认路径 ${SECRETS_DIR} / ${GAM_CONFIG} / ${GAM_CACHE_DIR}，无需改 systemd）"
