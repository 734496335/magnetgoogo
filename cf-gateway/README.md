# MagGoogo API Gateway (Cloudflare Worker)

## 部署步骤

### 1. 注册 Cloudflare 账号
https://dash.cloudflare.com/sign-up (免费)

### 2. 安装 wrangler CLI
```bash
cd cf-gateway
npm install
```

### 3. 登录 Cloudflare
```bash
npx wrangler login
```
浏览器会弹出授权页面，点击允许。

### 4. 部署
```bash
npx wrangler deploy
```

部署成功后会输出 Worker URL，格式：
```
https://maggoogo-gateway.<your-subdomain>.workers.dev
```

### 5. 本地测试
```bash
npx wrangler dev
```
本地服务默认在 http://localhost:8787

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /` | 健康检查 |
| `GET /config.json` | 远程配置 |
| `GET /sources.enc.json` | 加密源（版本门控） |
| `GET /api/check` | 综合状态检查 |

## 请求头

| Header | 说明 |
|--------|------|
| `X-App-Version` | App 版本号 (如 `1.0.0`) |
| `X-Device-Id` | 设备唯一ID（预留） |
| `X-Member-Token` | 会员令牌（预留） |

## 自动注入的 CF 头

| Header | 说明 |
|--------|------|
| `CF-IPCountry` | 用户国家代码 |
| `CF-Connecting-IP` | 用户真实 IP |
