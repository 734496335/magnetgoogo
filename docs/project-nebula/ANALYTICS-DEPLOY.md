# Analytics Dashboard 部署指南

## 架构

```
App 埋点 → CF Gateway → R2（不变）
阿里云 Dashboard → CF Gateway /api/events?raw=1 → 聚合处理 → 展示
                    ↑ 3分钟缓存，极低CF额度消耗
```

**零改动**：App 端不需要任何修改，纯后台 Dashboard 部署。

## 文件清单

```
analytics-server/
  server.js         → 178行，从CF拉数据+处理+密码保护
  public/
    login.html      → 密码登录页
    index.html      → 手机端数据面板（7个Tab，Chart.js图表）
  package.json      → 只依赖 express
```

## 部署步骤

### 1. 上传文件

```powershell
scp analytics-server/package.json admin@47.103.155.154:~/
scp analytics-server/server.js admin@47.103.155.154:~/
scp -r analytics-server/public admin@47.103.155.154:~/
```

### 2. SSH 到服务器

```bash
ssh admin@47.103.155.154
```

```bash
# 创建目录 + 移动文件
sudo mkdir -p /opt/analytics-server/public
sudo cp ~/package.json ~/server.js /opt/analytics-server/
sudo cp ~/public/* /opt/analytics-server/public/

# 安装依赖
cd /opt/analytics-server && sudo npm install --production

# 创建 systemd 服务
sudo tee /etc/systemd/system/analytics-server.service > /dev/null << 'EOF'
[Unit]
Description=MagGoogo Analytics Dashboard
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

[Install]
WantedBy=multi-user.target
EOF

# 启动
sudo systemctl daemon-reload
sudo systemctl enable analytics-server
sudo systemctl restart analytics-server
sudo systemctl status analytics-server
```

### 3. Nginx 反向代理

```bash
sudo vi /etc/nginx/conf.d/magnetgoogo.conf
```

在 `server { ... }` 块中加入：

```nginx
    # Analytics Dashboard (全部路径转发)
    location /analytics/ {
        proxy_pass http://127.0.0.1:3001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 4. 验证

```
浏览器: https://cn.magnetgoogo.com/analytics/
密码: MagGoogo2026
```

## 面板功能（7个Tab）

| Tab | 内容 |
|-----|------|
| 概览 | 今日/累计 KPI + DAU曲线 + 版本饼图 |
| 趋势 | 搜索量 + 复制/打开 + 新增vs回访 |
| 搜索 | 热词TOP 20 |
| 源性能 | 成功率/延迟排行 |
| 地区 | 国家/城市分布 |
| 设备 | 活跃设备列表 |
| 实时 | 最近事件流 |

## CF 额度消耗

每次打开面板 = 1 次 CF Worker 请求（如果3分钟内再刷新用缓存 = 0 次）。
一天刷100次面板 ≈ 最多 100 次请求，远低于 CF 免费额度 100,000/天。
