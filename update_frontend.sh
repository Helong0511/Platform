
clear
cd /data/Platform

find /data/Platform -type d -name "__pycache__" -exec rm -rf {} +

git pull

# 设置脚本执行权限（更安全的权限设置）
chmod +x /data/Platform/update_frontend.sh

cd /data/Platform/frontend

sudo systemctl stop Platform-backend.service
sudo systemctl stop Platform-scheduler.service
sudo systemctl stop mysql

sudo rm -rf /data/Platform/logs/*
sudo rm -rf dist
sudo rm -rf node_modules
# 保留 package-lock.json，确保 npm install 版本可重复、避免 workspace:* 解析失败

npm ci || npm install
npm run build

sudo systemctl start mysql
sudo systemctl restart Platform-backend.service
sudo systemctl restart Platform-scheduler.service