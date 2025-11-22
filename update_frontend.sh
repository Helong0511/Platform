clear
cd /data/Platform
git pull
cd /data/Platform/frontend
sudo rm -rf /data/Platform/logs/*
sudo systemctl stop Platform-backend.service
sudo systemctl stop mysql
rm -rf dist
rm -rf node_modules
rm -rf package-lock.json 
npm install
npm run build
sudo systemctl start mysql
sudo systemctl restart Platform-backend.service