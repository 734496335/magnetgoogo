# 阿里云证书续期修复记录（2026-07-31）

## 结论

`cn.magnetgoogo.com` 证书续期问题已关闭。

```text
CERTIFICATE_RENEWAL=PASS
PUBLIC_TLS=PASS
AUTO_RENEW_TIMER=ACTIVE
MEDIA_REVISION=7_UNCHANGED
```

## 根因

- 域名 A 记录直连阿里云 IP `47.103.155.154`，DNS 托管在 Cloudflare。
- 服务器本机访问 HTTP 80 由 Nginx 返回 301，但外网访问相同路径被上游返回 `Server: Beaver / HTTP 403`。
- Let’s Encrypt HTTP-01 看到的是该 403，因此 Certbot nginx/standalone 方式连续失败；继续修改 Nginx HTTP location 无法解决。

## 修复方案

- 使用官方 acme.sh，固定源提交 `2feb392bd0e3964d9bf68871ae804578d9d5ca80`，运行版本 `v3.1.5`。
- 切换到 Let’s Encrypt TLS-ALPN-01，从 443 端口完成验证，不依赖 HTTP 80 或 DNS API 密钥。
- 证书签发时使用 pre-hook 停止 Nginx，post-hook 无论成功失败均启动 Nginx。
- 将证书安装到：
  - `/etc/nginx/ssl/cn.magnetgoogo.com/fullchain.pem`
  - `/etc/nginx/ssl/cn.magnetgoogo.com/privkey.pem`
- Nginx 已切换到上述路径并通过 `nginx -t`。

## 新证书

```text
Subject: CN=cn.magnetgoogo.com
SAN: DNS:cn.magnetgoogo.com
Issuer: Let’s Encrypt YR1
Serial: 05D9B0741250831D213336AD509B7CB5A0A6
Valid from: 2026-07-31 12:46:28 UTC
Valid to: 2026-10-29 12:46:27 UTC
External TLS: TLSv1.3 / authorized=true
```

证书公钥与私钥公钥 SHA 一致：

```text
de5307d24a30c3d5205d3c24eb0eaf89687069a44a5e3fa792a01e84457aed52
```

权限：私钥 `600 root:root`，完整链 `644 root:root`。

## 自动续期

新增并启用：

- `acme-cn-magnetgoogo-renew.service`
- `acme-cn-magnetgoogo-renew.timer`

计划：每日 04:20（Asia/Shanghai）检查，随机延迟最多 30 分钟，`Persistent=true`。

首次手动执行结果：`status=0/SUCCESS`，正确识别下一次 ARI 续期时间为 `2026-09-28T17:23:55Z`。

持久化配置已确认包含：

- `Le_Webroot=alpn`
- Nginx stop/start pre/post hook
- 实际私钥和 fullchain 安装路径
- `systemctl reload nginx` reload command

旧的 `certbot-renew.timer` 已 disabled 并 inactive，避免继续执行必然失败的 HTTP-01 流程。

## 发布后验证

- 外网 TLS 证书受信任：PASS。
- `https://cn.magnetgoogo.com/media/v1/current.json`：HTTP 200。
- 正式媒体 pointer 仍为 revision 7，release `20260730T000000Z-5c299304`。
- Nginx active，配置测试 PASS。
- 自动续期 Timer enabled + active，下一次触发 `2026-08-01 04:41:30 CST`。

## 回滚

Nginx 配置备份：

`/root/cert-backups/20260731T2145/magnetgoogo.conf.before-acmesh`

旧 Certbot 证书文件保留在 `/etc/letsencrypt`，未删除。
