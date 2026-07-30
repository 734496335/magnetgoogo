# App 国内更新下载链路优化记录

日期：2026-07-30（UTC+8）

## 结论

本轮同时完成“现有用户立即生效的远程配置优化”和“下一版 App 生效的客户端容错改造”。

现有已安装的旧版本 App 无需重新安装即可从远程配置获得：

1. “立即更新”主地址切换为 Cloudflare R2 加速直链：
   `https://api.naoshiquan.com/download/v0.2.2/magnetgoogo-v0.2.2.apk`
2. 备用链接固定为：
   - 第一项：蓝奏云 `https://wwbdy.lanzn.com/imCPX3zgpbkb`，密码 `8888`
   - 最后一项：GitHub Release
3. Cloudflare Pages 的 `config.json` 和 `site-config.json` 增加 `no-store, no-cache, must-revalidate`，避免更新配置继续命中旧缓存。

## R2 正式 APK

已将正式签名的 `releases/magnetgoogo-v0.2.2.apk` 上传到现有 R2 发布桶：

- Bucket：`maggoogo-releases`
- Key：`v0.2.2/magnetgoogo-v0.2.2.apk`
- 公网地址：`https://api.naoshiquan.com/download/v0.2.2/magnetgoogo-v0.2.2.apk`
- 字节数：`33,562,462`
- SHA-256：`2ceb675b6d85cb5341e41fa219b0629f7e2a104bee89960359c508fabd9248eb`
- Content-Type：`application/vnd.android.package-archive`

完整公网回下载后的字节数和 SHA-256 均与正式 0.2.2 APK 一致。

## 远程配置发布

`mg-data` 最终提交：

`f7b945ee8365c0f2932909ca4ad7ec56ebeb437b`

最终下载契约：

```json
{
  "primary": "https://api.naoshiquan.com/download/v0.2.2/magnetgoogo-v0.2.2.apk",
  "mirrors": [
    "https://wwbdy.lanzn.com/imCPX3zgpbkb",
    "https://github.com/734496335/magnetgoogo/releases/download/v0.2.2/magnetgoogo-v0.2.2.apk"
  ]
}
```

已收敛并验证：

- `https://cn.magnetgoogo.com/config.json`
- `https://magnetgoogo.com/config.json`
- GitHub Raw `mg-data/main/config.json`
- `https://api.naoshiquan.com/config.json`
- `https://maggoogo-gateway.734496335lp.workers.dev/config.json`
- jsDelivr 固定提交 `f7b945ee.../config.json`

Cloudflare Pages 最终部署：

`https://c556a9e3.magnetgoogo-site.pages.dev`

阿里云配置回滚备份：

`/var/www/magnetgoogo-site/config.json.pre-cn-download-20260730`

## App 客户端容错改造

新增：

- `src/core/updateDownloadPolicy.ts`
- `src/core/updateDownload.ts`
- `scripts/update-download-policy-tests.mjs`

修改：

- `ForceUpdateModal.tsx`
- `OptionalUpdateModal.tsx`
- `configChecker.ts`
- `updateCopy.ts`

下一版 APK 将具备：

1. 无论远程配置原始顺序如何，蓝奏云都显示在第一位，GitHub 显示在最后。
2. “立即更新”按可直接下载 APK 的地址顺序自动重试。
3. 蓝奏云网页不会被误当作 APK 字节源。
4. 下载完成后检查文件至少 5 MiB，并验证 APK/ZIP 文件头；HTML 错误页不会进入安装流程。
5. 所有直链均失败后，弹窗直接提供“蓝奏云（推荐）”和“GitHub”两个浏览器入口。
6. 下载及安装错误使用带 `rule_id`、`stage`、`error_code` 的结构化日志。

边界：这些客户端代码尚未进入已发布的 0.2.2 APK，需要在下一版正式 APK 中生效；远程配置与 R2 主地址已经对当前旧版本用户即时生效。

## 阿里云 HTTPS 风险

审计发现 `cn.magnetgoogo.com` 当前证书有效期至 `2026-08-02 00:06:13 UTC`。本轮恢复了：

- `certbot-renew.timer`：enabled + active
- 下一次计划执行：2026-07-31

但人工续期测试仍失败：Let’s Encrypt HTTP-01 请求在公网验证链路返回 403/连接重置。该问题尚未关闭，因此阿里云地址已从 App 更新备用列表移除，不再影响当前更新主链路。现有 Nginx 服务已恢复且配置检查通过。

## VERIFICATION

- `cd magnetgoogo-app && npx tsc --noEmit`：PASS
- `npm run test:update-download`：PASS
- `npm run test:release-build`：PASS
- `node scripts/app-adversarial-tests.mjs`：52/52 PASS
- 四个本机可访问配置端点：最终下载契约全部 PASS
- 阿里云服务器外部视角验证 `cn` 与 GitHub Raw：PASS
- R2 APK 完整回下载：33,562,462 字节，SHA-256 一致，PASS
- K30S：本轮设备未连接，未执行真机弹窗点击验证
