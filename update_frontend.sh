
clear
cd /data/Platform
git pull

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

sudo chmod -R 777 /data/Platform/update_frontend.sh

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