
clear
cd /data/Platform

find /data/Platform -type d -name "__pycache__" -exec rm -rf {} +

git pull

# 设置脚本执行权限（更安全的权限设置）
chmod +x /data/Platform/update_frontend.sh

cd /data/Platform/frontend

sudo systemctl stop Platform-backend.service
sudo systemctl stop mysql

sudo rm -rf /data/Platform/logs/*
sudo rm -rf dist
sudo rm -rf node_modules
sudo rm -rf package-lock.json

npm install
npm run build

sudo systemctl start mysql
sudo systemctl restart Platform-backend.service