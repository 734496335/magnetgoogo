---
name: release-checklist
description: 涉及版本号、APK、ipa、下载链接、config.json 改动时加载。压缩版的 RELEASE-CHECKLIST.md。
---

# 发版关键路径

完整版见 `docs/project-nebula/RELEASE-CHECKLIST.md`。本 skill 只列**必须改的 10 个文件**与**严禁改的 800+ 文件**。

## 稳定链接（永不变，800+ SEO 页都依赖）
- `cn.magnetgoogo.com/download/magnetgoogo.apk`
- `github.com/734496335/magnetgoogo/releases/latest`

**绝对禁止在 SEO 页面里写蓝奏云具体链接或具体版本号。** 只允许指向上述两个稳定链接。

## 易变链接（每次发版必改的 ~10 个文件）
1. `magnetgoogo-app/app.json` — `expo.version`
2. `magnetgoogo-app/package.json` — `version`
3. `magnetgoogo-app/android/app/build.gradle` — `versionCode` / `versionName`
4. `magnetgoogo-site/index.html` — 蓝奏云 ID + JSON-LD `softwareVersion`
5–13. `magnetgoogo-site/{lang}/index.html` × 9 — JSON-LD `softwareVersion`
14. `maggoogo-sources/config.json` — `latest_version` / `min_version` / `mirrors`
15. `magnetgoogo/README_CN.md` — 蓝奏云链接

## 发版后必跑
- `python encrypt_sources.py`
- push maggoogo-sources / mg-data 仓库
- 部署 magnetgoogo-site: `cd magnetgoogo-site && npx wrangler pages deploy . --project-name=magnetgoogo-site --branch=main --commit-dirty=true`

## 禁忌
- `--branch=main` 缺失会创建 Preview deployment，自定义域不生效
- 不得在 800+ alt/blog/guide 页改任何东西做发版
- APK 上传前必须用 zipalign + 与上一版相同的签名 keystore
