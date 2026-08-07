#!/usr/bin/env bash
# 若用 sh update_frontend.sh 调用，自动切换到 bash（dash 不支持 pipefail）
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

set -euo pipefail

clear

PLATFORM_ROOT="/data/Platform"
FRONTEND_DIR="${PLATFORM_ROOT}/frontend"
LOG_DIR="${PLATFORM_ROOT}/logs"
MYSQL_WAIT_MAX="${MYSQL_WAIT_MAX:-60}"
SERVICE_WAIT_MAX="${SERVICE_WAIT_MAX:-45}"

wait_for_service_inactive() {
    local unit="$1"
    local max_wait="${2:-$SERVICE_WAIT_MAX}"
    local waited=0
    while systemctl is-active --quiet "$unit" 2>/dev/null; do
        if [ "$waited" -ge "$max_wait" ]; then
            echo "警告: ${unit} 在 ${max_wait}s 内未完全停止，继续后续步骤..."
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    echo "${unit} 已停止"
}

wait_for_mysql_ready() {
    local max_wait="${1:-$MYSQL_WAIT_MAX}"
    local waited=0
    while ! mysqladmin ping -h127.0.0.1 --silent 2>/dev/null; do
        if [ "$waited" -ge "$max_wait" ]; then
            echo "错误: MySQL 在 ${max_wait}s 内未就绪，中止部署"
            exit 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    echo "MySQL 已就绪"
}

# 判断是否为错误类日志文件名（含轮转备份）
is_error_log_file() {
    local base
    base="$(basename "$1")"
    case "$base" in
        error.log|error.log.[0-9]*|error.log.[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9])
            return 0
            ;;
        gunicorn_error.log|gunicorn_error.log.*|gunicorn_scheduler_error.log|gunicorn_scheduler_error.log.*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# 文件是否含非空白内容
file_has_content() {
    local f="$1"
    [ -f "$f" ] && [ -s "$f" ] && grep -q '[^[:space:]]' "$f" 2>/dev/null
}

# 更新前清理日志：清全部，但「有内容的错误日志」保留不删
cleanup_logs_before_update() {
    echo "=== 更新前清理日志 ==="
    if [ ! -d "$LOG_DIR" ]; then
        echo "日志目录不存在，跳过: ${LOG_DIR}"
        return 0
    fi

    local f base deleted=0 kept=0
    shopt -s nullglob
    # 仅处理 logs/ 顶层活跃日志与轮转备份；保留 archive/ 交由定时任务策略
    for f in \
        "${LOG_DIR}"/*.log \
        "${LOG_DIR}"/*.log.[0-9]* \
        "${LOG_DIR}"/*.log.[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]
    do
        [ -f "$f" ] || continue
        base="$(basename "$f")"
        if is_error_log_file "$f" && file_has_content "$f"; then
            echo "保留错误日志: ${base}"
            kept=$((kept + 1))
            continue
        fi
        echo "删除: ${base}"
        rm -f -- "$f" || true
        deleted=$((deleted + 1))
    done
    shopt -u nullglob

    echo "日志清理完成：删除 ${deleted} 个，保留错误日志 ${kept} 个"
}

# 清理 Python / 前端构建相关缓存
cleanup_caches() {
    echo "=== 清理缓存 ==="
    # Python 字节码缓存
    find "$PLATFORM_ROOT" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
    find "$PLATFORM_ROOT" -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete 2>/dev/null || true
    # 测试/工具缓存
    find "$PLATFORM_ROOT" -type d \( -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" \) \
        -prune -exec rm -rf {} + 2>/dev/null || true
    # 项目级缓存目录
    if [ -d "${PLATFORM_ROOT}/.cache" ]; then
        rm -rf "${PLATFORM_ROOT}/.cache"
        echo "已删除 ${PLATFORM_ROOT}/.cache"
    fi
    # 前端 Vite 缓存（保留 node_modules，构建前仍会重装/复用）
    if [ -d "${FRONTEND_DIR}/node_modules/.vite" ]; then
        rm -rf "${FRONTEND_DIR}/node_modules/.vite"
        echo "已删除 frontend/node_modules/.vite"
    fi
    if [ -d "${FRONTEND_DIR}/.vite" ]; then
        rm -rf "${FRONTEND_DIR}/.vite"
        echo "已删除 frontend/.vite"
    fi
    echo "缓存清理完成"
}

cd "$PLATFORM_ROOT"

cleanup_logs_before_update
cleanup_caches

git pull

chmod +x "$PLATFORM_ROOT/update_frontend.sh"

cd "$FRONTEND_DIR"

echo "=== 停止服务（先调度器，再 API，最后 MySQL）==="
# 调度器依赖 MySQL 跑定时任务，须先于 MySQL 停服并等待进程退出
sudo systemctl stop Platform-scheduler.service
wait_for_service_inactive Platform-scheduler.service || true

sudo systemctl stop Platform-backend.service
wait_for_service_inactive Platform-backend.service || true

sudo systemctl stop mysql

# 仅清理前端构建产物
sudo rm -rf dist
sudo rm -rf node_modules
# 保留 package-lock.json，确保 npm install 版本可重复、避免 workspace:* 解析失败

echo "=== 构建前端 ==="
npm ci || npm install
npm run build

echo "=== 启动服务（MySQL 就绪后再启应用）==="
sudo systemctl start mysql
wait_for_mysql_ready

cp /data/Platform/frontend/privacy.html  /data/Platform/frontend/dist/

sudo systemctl start Platform-backend.service
sudo systemctl start Platform-scheduler.service

echo "=== 部署完成 ==="
systemctl is-active mysql Platform-backend.service Platform-scheduler.service
