# 仓库迁移方案：maggoogo-sources → mg-data

> **历史迁移文档，非当前运行时 SOP。** 文中的 `Promise.any`/并行最快者胜出属于旧实现；v0.2.6 当前 source/config mutable authority 已改为按信任层顺序验证。实际发布/续期请读 `SOURCE-RELEASE-PLAYBOOK.md`，App 发版请读 `RELEASE-CHECKLIST.md`。

## 背景
旧仓库 `734496335/maggoogo-sources` 切换到新仓库 `734496335/mg-data`。
好处：
- 拉取速度优化（并行竞争 Promise.any 替代串行 fallback）
- 为后续会员鉴权预留架构
- 旧仓库失效可强制用户升级

## 新架构

### 端点列表
| 端点 | URL | 用途 |
|------|-----|------|
| jsDelivr CDN | `cdn.jsdelivr.net/gh/734496335/mg-data@main` | 主力，国内有 CDN 节点 |
| GitHub Raw | `raw.githubusercontent.com/734496335/mg-data/main` | 备用 |
| CF Worker | `maggoogo-gateway.734496335lp.workers.dev` | 备用 + 未来会员鉴权网关 |
| Dev | `192.168.5.207:9090` | 本地开发 |

### 拉取策略
```
旧：CDN → Gateway → Raw → Dev  (串行，最慢 4×15s = 60s)
新：CDN | Raw | Gateway | Dev   (并行竞争，最慢 8s)
```

### 安全层
- Layer 1: AES-256-CBC 加密传输
- Layer 2: 磁盘缓存（仍是加密态，72h 过期）
- Layer 3: 内存 XOR 混淆

### 会员鉴权（预留）
```
Free 用户:  无 token → GitHub CDN 直接拉取
Member 用户: Authorization: Bearer <token> → CF Worker 验证后返回数据
```

## 迁移步骤

### 1. 创建新 GitHub 仓库
```bash
# 在 GitHub 上创建 734496335/mg-data 仓库（公开）
cd d:\lpproduct\magnet\mg-data
git remote add origin https://github.com/734496335/mg-data.git
git push -u origin main
```

### 2. 验证 CDN 可用
等待 5-10 分钟让 jsDelivr 缓存生效：
```
https://cdn.jsdelivr.net/gh/734496335/mg-data@main/config.json
https://cdn.jsdelivr.net/gh/734496335/mg-data@main/sources.enc.json
```

### 3. 发布新版 App
- App 代码已指向 mg-data
- 打包 APK 发布

### 4. 废弃旧仓库（强制旧用户升级）
编辑 `maggoogo-sources/config.json`：
```json
{
  "min_version": "X.Y.Z",   ← 设为新版版本号
  "announcement": "请更新到最新版本以继续使用",
  ...
}
```
Push 到旧仓库 → 旧版本用户打开 App 会看到强制升级提示。

### 5. 后续更新源
```bash
cd d:\lpproduct\magnet
python encrypt_sources.py --deploy
# 自动加密 sources.json → mg-data/sources.enc.json → git push
```

## 后续会员方案
当需要支持会员时：
1. CF Worker 添加 token 验证逻辑
2. App 中添加登录/注册 UI
3. 登录成功后调用 `setAuthToken(token)` 存储
4. 后续请求自动带 `Authorization: Bearer <token>`
5. CF Worker 验证 token → 返回 premium 源 / 403
6. 可以再新建 `mg-data-v2` 仓库，旧仓库设 min_version 强制升级
