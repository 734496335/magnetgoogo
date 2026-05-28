# 源数据安全策略

文档版本：V1.0  
更新时间：2026-05-09

## 核心原则

> **磁力源规则是核心资产，对用户绝对保密。**
>
> 源数据在任何环节都必须以加密形态存在，禁止以明文形式传输或暴露。

## 1. 传输安全

### 绝对禁止

- ❌ 任何端点以明文提供 `sources.json`
- ❌ App 代码中包含明文 fallback（如 `DEV_BASE`、`/sources.json`）
- ❌ HTTP（非 HTTPS）传输源数据
- ❌ 将解密后的源数据写入可被用户访问的存储

### 必须遵守

- ✅ 所有端点仅提供 `sources.enc.json`（AES-256-CBC 加密）
- ✅ 传输使用 HTTPS
- ✅ 加密负载附带 HMAC-SHA256 签名，App 解密前必须验签
- ✅ 解密密钥以 XOR 分片存储在代码中，不以单一字符串存在

## 2. 存储安全（App 端 3 层防护）

| 层 | 位置 | 形态 | 保护 |
|---|---|---|---|
| Layer 1 | 传输中 | AES-256-CBC 密文 | 抓包看不到明文 |
| Layer 2 | 磁盘缓存 | 仍为加密密文 | Root 提取也只是密文 |
| Layer 3 | 内存运行时 | XOR 混淆 (session key) | Frida dump 看到乱码 |

## 3. 端点分发策略

```
┌─── 加密源分发端点（仅 sources.enc.json）───┐
│                                              │
│  magnetgoogo.com      Cloudflare Pages       │ ← 国内首选
│  cdn.jsdelivr.net     jsDelivr CDN           │ ← 国内备选
│  raw.githubusercontent GitHub Raw             │ ← 海外
│  api.naoshiquan.com   CF Worker Gateway      │ ← 海外
│                                              │
└──────────────────────────────────────────────┘
```

**访问策略**：5 端点并行 race → 最快响应胜出 → 失败则逐个重试（15s 超时）

## 4. 强制更新机制

| 机制 | 控制点 | 效果 |
|---|---|---|
| **本地缓存过期** | `DEFAULT_EXPIRY_HOURS = 72` | 72h 不联网同步 → 源不可用 |
| **版本门禁** | `config.json` → `min_version` | 低于门槛的 App 版本拒绝解包源数据 |

**操作流程**：
1. 需要强制更新时：修改 `config.json` 中的 `min_version`
2. 重新加密：`python encrypt_sources.py`
3. 部署：推送到 mg-data repo + Cloudflare Pages

## 5. 加密流水线

```
sources.json (明文，仅存在于开发机)
    ↓ python encrypt_sources.py
sources.enc.json (AES-256-CBC + HMAC + gzip)
    ↓ 部署到各端点
用户 App → 拉取 enc → 验签 → 解密 → 仅在内存中使用
```

### 禁止事项

- ❌ 将 sources.json 推送到任何公开仓库
- ❌ 在 CI 日志中输出源内容
- ❌ 在 App 中提供「导出源」功能
- ❌ 明文 API 端点（历史遗留的 DEV_BASE 已删除）

## 6. 历史教训

| 日期 | 事件 | 修复 |
|---|---|---|
| 2026-05-09 | DEV_BASE 明文 fallback 暴露风险 | 彻底移除，禁止明文传输 |
| 2026-05-09 | expires_at 服务端过期导致全用户锁死 | 改为本地缓存过期 + 版本门禁 |
| 2026-05-09 | cn.magnetgoogo.com TLS 不通 | 改用 Cloudflare Pages 分发 |
