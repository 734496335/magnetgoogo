#!/bin/bash
# ============================================
# 磁力古哥 - 阿里云服务器一键部署脚本
# 功能：Nginx 官网镜像 + APK 下载 + Admin Dashboard
# ============================================

set -e

echo "========================================="
echo "  磁力古哥 服务器部署脚本"
echo "========================================="

# --- 1. 系统更新 & 基础工具 ---
echo "[1/6] 安装基础工具..."
sudo yum update -y -q 2>/dev/null || sudo apt-get update -y -qq 2>/dev/null
sudo yum install -y -q nginx certbot python3-certbot-nginx git wget curl 2>/dev/null || \
sudo apt-get install -y -qq nginx certbot python3-certbot-nginx git wget curl 2>/dev/null

# --- 2. 安装 Node.js 18 ---
echo "[2/6] 安装 Node.js..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash - 2>/dev/null || \
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - 2>/dev/null
    sudo yum install -y -q nodejs 2>/dev/null || sudo apt-get install -y -qq nodejs 2>/dev/null
fi
echo "Node.js: $(node -v)"

# --- 3. 创建目录结构 ---
echo "[3/6] 创建目录结构..."
sudo mkdir -p /var/www/magnetgoogo-site
sudo mkdir -p /var/www/apk
sudo mkdir -p /opt/admin-server
sudo chown -R $USER:$USER /var/www/magnetgoogo-site /var/www/apk /opt/admin-server

# --- 4. Nginx 配置 ---
echo "[4/6] 配置 Nginx..."
sudo tee /etc/nginx/conf.d/magnetgoogo.conf > /dev/null << 'NGINX'
# 官网镜像 (百度 SEO)
server {
    listen 80;
    server_name cn.magnetgoogo.com;

    root /var/www/magnetgoogo-site;
    index index.html;

    # APK 下载
    location /download/ {
        alias /var/www/apk/;
        add_header Content-Disposition "attachment";
        add_header Content-Type application/vnd.android.package-archive;
    }

    # 静态文件缓存
    location ~* \.(css|js|png|jpg|ico|svg|woff2)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}

# Admin Dashboard
server {
    listen 3000;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_cache_bypass $http_upgrade;
    }
}
NGINX

# 测试 Nginx 配置
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

echo "[5/6] 目录结构已就绪"
echo "  官网文件: /var/www/magnetgoogo-site/"
echo "  APK 文件: /var/www/apk/"
echo "  Admin:    /opt/admin-server/"

echo "[6/6] ✅ 基础环境部署完成！"
echo ""
echo "接下来需要："
echo "  1. 上传官网文件到 /var/www/magnetgoogo-site/"
echo "  2. 上传 APK 到 /var/www/apk/"
echo "  3. 部署 admin-server 到 /opt/admin-server/"
echo "  4. 配置 DNS: cn.magnetgoogo.com → 服务器 IP"
echo "  5. 申请 SSL: sudo certbot --nginx -d cn.magnetgoogo.com"
