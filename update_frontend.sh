#!/usr/bin/env bash
# 若用 sh update_frontend.sh 调用，自动切换到 bash（dash 不支持 pipefail）
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

set -euo pipefail

clear

PLATFORM_ROOT="/data/Platform"
FRONTEND_DIR="${PLATFORM_ROOT}/frontend"
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

cd "$PLATFORM_ROOT"

find "$PLATFORM_ROOT" -type d -name "__pycache__" -exec rm -rf {} +

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

# 保留 logs/ 便于排查；仅清理前端构建产物
sudo rm -rf dist
sudo rm -rf node_modules
# 保留 package-lock.json，确保 npm install 版本可重复、避免 workspace:* 解析失败

sudo rm -rf /data/Platform/logs/*

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
