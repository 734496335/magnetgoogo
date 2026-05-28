#!/bin/bash
# 部署 Analytics Server 到阿里云
# 用法: bash scripts/deploy-analytics.sh

SERVER="admin@47.103.155.154"
REMOTE_DIR="/opt/analytics-server"
LOCAL_DIR="analytics-server"

echo "📦 Uploading analytics server..."
ssh $SERVER "mkdir -p $REMOTE_DIR/public $REMOTE_DIR/data"

# Upload files (excluding node_modules and data)
scp $LOCAL_DIR/package.json $SERVER:$REMOTE_DIR/
scp $LOCAL_DIR/server.js $SERVER:$REMOTE_DIR/
scp $LOCAL_DIR/public/index.html $SERVER:$REMOTE_DIR/public/
scp $LOCAL_DIR/public/login.html $SERVER:$REMOTE_DIR/public/

echo "📥 Installing dependencies on server..."
ssh $SERVER "cd $REMOTE_DIR && npm install --production"

echo "🔧 Creating systemd service..."
ssh $SERVER "cat > /etc/systemd/system/analytics-server.service << 'EOF'
[Unit]
Description=MagGoogo Analytics Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/analytics-server
ExecStart=/usr/bin/node /opt/analytics-server/server.js
Restart=always
RestartSec=5
Environment=PORT=3001
Environment=DASH_PASS=MagGoogo2026
Environment=DATA_DIR=/opt/analytics-server/data

[Install]
WantedBy=multi-user.target
EOF"

echo "🔄 Restarting service..."
ssh $SERVER "systemctl daemon-reload && systemctl enable analytics-server && systemctl restart analytics-server"

echo "🔧 Configuring Nginx reverse proxy..."
ssh $SERVER "cat > /etc/nginx/conf.d/analytics.conf << 'NGINX'
# Analytics dashboard + event ingestion
location /analytics/ {
    proxy_pass http://127.0.0.1:3001/;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
}

# Event ingestion API (app sends here)
location /api/events {
    proxy_pass http://127.0.0.1:3001/api/events;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header Content-Type application/json;
}
NGINX"

ssh $SERVER "nginx -t && systemctl reload nginx"

echo ""
echo "✅ Deploy complete!"
echo "   📊 Dashboard: https://cn.magnetgoogo.com/analytics/"
echo "   📡 Event API: https://cn.magnetgoogo.com/api/events"
echo "   🔑 Password: MagGoogo2026"
