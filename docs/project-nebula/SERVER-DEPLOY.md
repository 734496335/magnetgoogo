# 阿里云服务器部署信息

## 服务器

| 项目 | 值 |
|------|------|
| **公网 IP** | `47.103.155.154` |
| **地域** | 华东2（上海） |
| **配置** | 2核2G, 40GB ESSD, 200Mbps |
| **系统** | Alibaba Cloud Linux 3 |
| **SSH 用户** | `admin` |
| **SSH 端口** | 22 |

## 部署的服务

| 服务 | 地址 | 端口 | 说明 |
|------|------|------|------|
| **官网镜像** | https://cn.magnetgoogo.com | 80/443 | 百度 SEO 加速，Nginx 静态 |
| **APK 下载** | https://cn.magnetgoogo.com/download/magnetgoogo.apk | 同上 | 国内直连下载 |
| **Admin Dashboard** | http://47.103.155.154:3000 | 3000 | Basic Auth: admin / MagGoogo2026! |

## DNS 配置

| 类型 | 名称 | 内容 | 代理 |
|------|------|------|------|
| A | cn | 47.103.155.154 | 仅 DNS（灰色） |

## SSL 证书

- Let's Encrypt 自动签发
- 到期时间：2026-08-02
- 自动续期：certbot systemd timer

## 文件路径

| 路径 | 内容 |
|------|------|
| `/var/www/magnetgoogo-site/` | 官网静态文件 |
| `/var/www/apk/magnetgoogo.apk` | APK 文件 |
| `/opt/admin-server/` | Admin Dashboard 服务 |
| `/etc/nginx/conf.d/magnetgoogo.conf` | Nginx 官网配置 |
| `/etc/nginx/conf.d/admin-auth.conf` | Nginx Admin 代理+认证 |
| `/etc/systemd/system/admin-server.service` | Admin systemd 服务 |

## Cloudflare Pages 部署（magnetgoogo.com）

| 项目 | 值 |
|------|------|
| **项目名** | `magnetgoogo-site` |
| **Production 分支** | `main`（⚠️ 不是 master） |
| **域名** | `magnetgoogo.com`, `naoshiquan.com`, `magnetgoogo-site.pages.dev` |
| **本地目录** | `D:\lpproduct\magnet\magnetgoogo-site` |

### 部署命令

```bash
# ⚠️ 必须加 --branch=main，否则部署到 Preview 环境，magnetgoogo.com 不会更新！
npx wrangler pages deploy . --project-name=magnetgoogo-site --branch=main
```

> **踩坑记录**：wrangler 检测到 git 仓库时默认用当前分支名（master），
> 而 Cloudflare Pages Production 绑定的是 `main`，导致部署到 Preview 而非 Production。
> magnetgoogo.com 只绑定 Production，所以页面不更新。

## 更新操作

### 更新官网（国内镜像 cn.magnetgoogo.com）
```bash
cd /var/www/magnetgoogo-site
for f in index.html style.css; do wget -q "https://magnetgoogo.com/$f" -O "$f"; done
```

### 更新 APK
```bash
scp app-release.apk admin@47.103.155.154:/var/www/apk/magnetgoogo.apk
```

### 更新 Admin Dashboard
```bash
scp server.js admin@47.103.155.154:/opt/admin-server/
ssh admin@47.103.155.154 "sudo systemctl restart admin-server"
```

## 防火墙规则

| 端口 | 协议 | 用途 |
|------|------|------|
| 22 | TCP | SSH |
| 80 | TCP | HTTP |
| 443 | TCP | HTTPS |
| 3000 | TCP | Admin Dashboard |
