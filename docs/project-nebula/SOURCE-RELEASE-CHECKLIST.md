# sources.enc.json 发布清单（易漏点）

> App 用 `Promise.any` 抢最快端点；**任一旧端点更快就会继续用旧源**。必须六路对齐 + 清缓存。

## 端点矩阵

| # | Base | 文件来源 | 更新方式 | 缓存风险 |
|---|---|---|---|---|
| ① | `cn.magnetgoogo.com` | 阿里云 `/var/www/magnetgoogo-site/sources.enc.json` | **scp** | Nginx 缓存少，漏 scp 最常见 |
| ② | `magnetgoogo.com` | CF Pages 站点根目录 `sources.enc.json` | **wrangler pages deploy --branch=main** | 必须 `main` 非 Preview |
| ③ | `cdn.jsdelivr.net/gh/734496335/mg-data@main` | GitHub mg-data | git push 后 CDN | **可缓存数小时** → 必须 purge |
| ④ | `raw.githubusercontent.com/.../mg-data/main` | GitHub mg-data | git push | 一般较快 |
| ⑤ | `api.naoshiquan.com` | CF Worker → 上游 raw | 上游更新后 | Worker `CACHE_TTL` 默认约 300 秒；App 带 `Cache-Control: no-cache` 会跳过读缓存 |
| ⑥ | `maggoogo-gateway...workers.dev` | 同 ⑤ | 同 ⑤ | 同 ⑤ |

App 竞速顺序（`secureSourceStore.ts`）：

`magnetgoogo.com` → gateway → jsDelivr → raw → workers.dev → **cn.magnetgoogo.com**

## 标准步骤

1. `python validate_enum.py` → ALL VALID
2. `python encrypt_sources.py` → 写入 **`mg-data/sources.enc.json`**（勿手滑再 `--verify` 后无意义重生成 diff）
3. **复制**同一文件到 `magnetgoogo-site/sources.enc.json`（漏了则 ② 旧）
4. **不要**把 `sources-debug.enc.json` 提交进 mg-data（`git add -A` 易误带）
5. `cd mg-data && git add sources.enc.json && commit && push`
6. `cd magnetgoogo-site && npx wrangler pages deploy . --project-name=magnetgoogo-site --branch=main --commit-dirty=true`
7. `scp mg-data/sources.enc.json admin@47.103.155.154:/var/www/magnetgoogo-site/sources.enc.json`
8. **清缓存**
   - jsDelivr：`https://purge.jsdelivr.net/gh/734496335/mg-data@main/sources.enc.json`
   - 可选再 purge `config.json`
   - Worker：等待不超过 5 分钟，或依赖 App `no-cache`
9. **验收**：六个 URL 的 `Content-Length` / SHA-256 一致（③ 可延迟）
10. **客户端磁盘缓存**：App 本地 `source-cache/sources.cache.json` 最长约 72 小时；要立刻看到新源需清应用数据或覆盖安装，或等待过期后重拉

## 不做

- 不改 `config.json` 版本号（纯源发布）
- 不自动 demote
- 不部署无关 APK
