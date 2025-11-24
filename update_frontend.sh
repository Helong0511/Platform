
clear
cd /data/Platform
git pull

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    # 不调用 deactivate，让shell自然退出时自动退出虚拟环境
else
    echo "虚拟环境不存在，跳过pip安装步骤。"
fi

# 设置脚本执行权限（更安全的权限设置）
chmod +x /data/Platform/update_frontend.sh

cd /data/Platform/frontend
sudo rm -rf /data/Platform/logs/*
sudo systemctl stop Platform-backend.service
sudo systemctl stop mysql

sudo rm -rf dist
sudo rm -rf node_modules
sudo rm -rf package-lock.json

npm install
npm run build

sudo systemctl start mysql
sudo systemctl restart Platform-backend.service