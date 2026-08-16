# MagGoogo Android App 正式发版权威手册

> **唯一 App 发版操作 authority。** 后续构建、签名、归档、蓝奏云/R2/GitHub/阿里云、config、官网、K30S 更新 E2E 均按本文执行。
>
> 真机安装细节见 `K30S-INSTALL-PLAYBOOK.md`；真机测试矩阵见 `K30S-TEST-PLAYBOOK.md`；源发布独立见 `SOURCE-RELEASE-PLAYBOOK.md`。

---

## 0. 四条铁律

1. **最终 APK 先完成 exact-SHA K30S 验收，再发布。** 同版本旧候选装过不算当前 final artifact 验收。
2. **新版本的所有下载渠道准备齐后，才切 `config.json latest_version`。** 不允许用户先看到更新、APK 后到。
3. **config 是 mutable authority，更新顺序以信任层而不是响应速度为准。** 不能重新引入 stale-fast-mirror race。
4. **签名绝不变。** 正式 keystore 固定在 `releases/magnetgoogo-release-new.keystore`；不要把唯一 keystore 放进会被 `expo prebuild --clean` 删除的 `android/` 目录。

---

## 1. 当前项目物理路径

### 0.2.x Release 候选工作区

```text
D:\lpproduct\m023
```

App：

```text
D:\lpproduct\m023\magnetgoogo-app
```

正式归档：

```text
D:\lpproduct\m023\releases
```

### 官网/Cloudflare Pages 主目录

```text
D:\lpproduct\magnet\magnetgoogo-site
```

m023 中没有官网目录，不要在 m023 下凭空找 `magnetgoogo-site`。

---

## 2. 版本号与发布身份

当前没有可靠存在的 `sync-version.js`，因此发版前必须**显式检查**至少：

```text
magnetgoogo-app/package.json          version
magnetgoogo-app/app.json              expo.version
magnetgoogo-app/app.json              android.versionCode
生成后的 android/app/build.gradle     versionName/versionCode
```

版本规则：

- versionName：语义版本，例如 `0.2.6`
- versionCode：Android 单调递增整数，例如 `10`
- 正式 package：`com.magnetgoogo.app`
- Debug package：`com.magnetgoogo.app.debug`

发版前运行：

```bat
cd magnetgoogo-app
npm run test:release-build
```

该门禁会检查 package/version/code、release signing plugin、arm64/source bootstrap 等发布契约。

---

## 3. 正式签名 authority

### 3.1 keystore

```text
releases/magnetgoogo-release-new.keystore
```

这是备案正式签名文件，必须 Git 保留。

`with-release-signing.js` 生成的 Gradle 配置通过相对路径引用：

```text
../../../releases/magnetgoogo-release-new.keystore
```

### 3.2 签名变量

构建期变量：

```text
RELEASE_STORE_PASSWORD
RELEASE_KEY_ALIAS
RELEASE_KEY_PASSWORD
```

正常来源是 Git 忽略的本地 `magnet/.env` / 受保护恢复链，不在新文档或构建日志中输出值。

缺失时优先按项目安全规范恢复 `releases/secrets.enc`，不要重新生成 keystore。

### 3.3 必须和上一正式版 signer 比较

```bat
python scripts/verify_release_apk.py <new.apk> --previous releases/magnetgoogo-v0.2.5.apk ...
```

`matches_previous_certificate` 必须为 `true`。

**任何 signer mismatch 都是发版硬阻断。**

---

## 4. 发版前代码门禁

在 `magnetgoogo-app`：

```bat
npx tsc --noEmit
node scripts/app-adversarial-tests.mjs
npm run test:resource-feed
npm run test:media-network
npm run test:media-security
npm run test:media-cache
npm run test:update-download
npm run test:release-build
npm run test:analytics-v2
npm run test:resource-auto-sync
node scripts/fluency-extreme-tests.mjs
```

变更影响 source/crawler 时还必须：

```bat
cd ..
python -m pytest magnet/tests/crawler_v3 -m "not integration" -q
python scripts/audit_source_delivery.py sources.json
python magnet/validate_enum.py
```

发布标准：

- deterministic tests 全绿；
- adversarial hard failure = 0；
- source contract hard finding = 0；
- `ALL VALID`；
- live media authority 正常；
- 已知 P0/P1 = 0。

---

## 5. 正式 Release 构建

### 5.1 当前 native 生成方式

正式 build 前确认 release signing plugin 已处于 current/idempotent 状态：

```bat
cd magnetgoogo-app
npm run test:release-build
```

### 5.2 强制 final build

最终候选应避免复用可能陈旧的 JS/native task，推荐 forced rerun：

```bat
cd magnetgoogo-app\android
gradlew.bat assembleRelease --rerun-tasks ^
  -PreactNativeArchitectures=arm64-v8a ^
  -Pandroid.enableMinifyInReleaseBuilds=true ^
  -Pandroid.enableShrinkResourcesInReleaseBuilds=true ^
  -x lintVitalRelease -x lintVitalAnalyzeRelease -x lintVitalReportRelease
```

签名变量只注入该 Gradle child process，不打印变量值。

产物：

```text
magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk
```

### 5.3 关于 HBC

历史旧流程要求手工：

```text
expo export → .hbc → assets/index.android.bundle
```

当前构建必须以**最终 APK 内 Hermes bundle 实际存在**和 release tests 为准，不再机械地复制旧流程步骤。若 native 构建链发生变化，再检查 bundle task 是否真实执行。

最终 APK 可验证 Hermes magic；若没有内嵌 JS/Hermes，Release 是硬失败。

---

## 6. 正式 APK 验证

示例：

```bat
python scripts/verify_release_apk.py ^
  magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk ^
  --previous releases/magnetgoogo-v0.2.5.apk ^
  --expect-version 0.2.6 ^
  --expect-code 10 ^
  --expect-package com.magnetgoogo.app ^
  --max-bytes 52428800
```

必须：

```text
status=PASS
package=com.magnetgoogo.app
versionName=<NEW>
versionCode=<NEW CODE>
abis=[arm64-v8a]
certificate == previous certificate
```

另外记录：

- bytes
- SHA256
- Hermes magic
- bundle forbidden strings scan

**后续所有渠道都必须绑定这一 SHA。**

---

## 7. Final APK K30S Gate

按 `K30S-INSTALL-PLAYBOOK.md`：

```bat
adb -s a1ea223a install -r "magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk"
```

必须输出：

```text
Performing Streamed Install
Success
```

然后：

- installed base.apk SHA = final APK SHA；
- version/code 正确；
- firstInstallTime 保持不变；
- 冷启动/热恢复/force-stop recovery；
- 重复搜索 freshness；
- resources/detail/favorites/settings 主流程；
- Fatal/ANR=0。

**这一 gate 没过，不归档、不上传、不切 config。**

---

## 8. 归档到 `releases/`

最终 K30S exact-SHA PASS 后：

```text
releases/magnetgoogo-v<NEW>.apk
```

例：

```text
releases/magnetgoogo-v0.2.6.apk
```

归档后再次：

```bat
python scripts/verify_release_apk.py releases/magnetgoogo-v0.2.6.apk --previous releases/magnetgoogo-v0.2.5.apk --expect-version 0.2.6 --expect-code 10
```

并确认：

```text
archive SHA == build output SHA == K30S installed SHA
```

`releases/*.apk` 通常不需要提交 Git；它是本地/发布制品归档。

---

## 9. 发布渠道顺序

**先准备文件，再切用户可见 config。**

推荐顺序：

```text
1. R2 primary
2. 阿里云 stable + versioned archive
3. GitHub Release
4. 蓝奏云（人工上传，拿链接）
5. 写好 config / 官网下载信息
6. 发布 config / Pages / Aliyun site
7. 端点收敛
8. 旧版本公网更新 E2E
```

蓝奏云必须在 config 切换前拿到真实新链接，禁止 `REPLACE_WITH_NEW_LINK`、旧版本链接或占位符上线。

---

## 10. R2 主下载发布

Gateway R2 bucket：

```text
bucket: maggoogo-releases
binding: RELEASES
```

key 契约：

```text
v<version>/magnetgoogo-v<version>.apk
```

公网：

```text
https://api.naoshiquan.com/download/v<version>/magnetgoogo-v<version>.apk
```

例如：

```text
https://api.naoshiquan.com/download/v0.2.6/magnetgoogo-v0.2.6.apk
```

当前 Wrangler CLI 已核对，上传命令格式为：

```bat
cd D:\lpproduct\magnet\cf-gateway
npx wrangler r2 object put maggoogo-releases/v0.2.6/magnetgoogo-v0.2.6.apk ^
  --file D:\lpproduct\m023\releases\magnetgoogo-v0.2.6.apk ^
  --content-type application/vnd.android.package-archive
```

换版本时只替换版本号和文件名。上传后必须**完整回下载**并比较：

```text
bytes
SHA256
Content-Type=application/vnd.android.package-archive
```

### 关键风险

`cf-gateway/src/index.js` 的 R2 missing fallback 仍应被视为备用，不可依赖它代替 R2 object。**R2 primary object 存在是正式发布 Gate。**

---

## 11. 阿里云 APK 发布

当前稳定下载仍需要维护：

```text
/var/www/apk/magnetgoogo.apk
/var/www/apk/magnetgoogo-v<version>.apk
```

典型：

```bat
scp releases/magnetgoogo-v0.2.6.apk admin@47.103.155.154:/var/www/apk/magnetgoogo-v0.2.6.apk
ssh admin@47.103.155.154 "cp /var/www/apk/magnetgoogo-v0.2.6.apk /var/www/apk/magnetgoogo.apk"
```

上线后从公网完整回下载，比较 SHA；不要只在服务器本机 `ls -l`。

---

## 12. GitHub Release

仓库当前公开 Release authority：

```text
734496335/magnetgoogo
```

创建：

```text
tag: v<version>
asset: magnetgoogo-v<version>.apk
```

Release notes 与 App update announcement 保持语义一致，但可以中英文分别写。

上传后验证 asset bytes/SHA；不能只看网页显示“上传成功”。

---

## 13. 蓝奏云

蓝奏云为人工上传渠道，用户本次将自行上传 v0.2.6。

操作要求：

1. 上传 `releases/magnetgoogo-v0.2.6.apk`；
2. 设置/确认密码（当前项目历史约定通常为 `8888`，发版前以实际链接为准）；
3. 拿到**真实新 URL**；
4. 浏览器打开落地页确认文件名/版本；
5. 再把 URL 写进 config / 官网；
6. 不伪造“蓝奏云文件体 SHA 已自动验证”的结论，除非确实拿到文件 bytes。

---

## 14. App 更新 config 当前真实 trust order

`configChecker.ts` v0.2.6：

### Authorities

```text
1. GitHub Raw mg-data/main/config.json
2. https://magnetgoogo.com/config.json
3. https://api.naoshiquan.com/config.json
```

每个 endpoint HTTP 200 后还必须过 schema validation。

### Fallbacks

```text
1. https://cn.magnetgoogo.com/config.json
2. old workers.dev config
3. immutable jsDelivr commit config
```

**不是“谁响应快谁赢”。**

历史 `Promise.any` mutable config race 已废弃，因为 stale CDN 可能抢赢新配置。

---

## 15. config 发布内容

当前 config 至少包括：

```jsonc
{
  "latest_version": "<NEW>",
  "min_version": "<MIN>",
  "download": {
    "primary": "https://api.naoshiquan.com/download/v<NEW>/magnetgoogo-v<NEW>.apk",
    "mirrors": [
      "<new-lanzou-url>",
      "https://github.com/734496335/magnetgoogo/releases/download/v<NEW>/magnetgoogo-v<NEW>.apk"
    ]
  },
  "announcement": "...",
  "source_expiry_hours": 72,
  "source_schema_version": 1,
  "updated_at": "<ISO8601>"
}
```

### optional vs forced

- `latest_version` 提高：可选更新；
- `min_version` 提高：低于门槛强制更新。

除非有明确兼容/安全原因，不要顺手提高 `min_version`。

### 更新 announcement

要求：

- 用户能看懂；
- 不写内部实现细节；
- 链接/密码与真实发布渠道一致；
- 不能乱码/BOM 破坏 JSON。

---

## 16. config 文件写入位置

至少维护：

```text
m023/mg-data/config.json
D:\lpproduct\magnet\magnetgoogo-site/config.json
```

若主项目另有发布副本，则以当前部署脚本/站点目录为准同步。

修改后：

```bat
node -e "JSON.parse(require('fs').readFileSync('mg-data/config.json','utf8')); console.log('PASS')"
```

确保 UTF-8、无 BOM、schema 通过 App `configValidation` tests。

---

## 17. 官网页面生成

禁止手工逐个改多语言 HTML。

主项目已有生成/同步脚本，按当前仓库真实脚本执行，例如：

```text
scripts/generate-i18n-pages.js
scripts/generate-guide-pages.js
scripts/generate-i18n-guide-pages.js
scripts/generate-seo-pages.js
scripts/sync-download-mirrors.js
```

发版前 grep：

- 旧版本号；
- 旧 R2 URL；
- 旧 GitHub asset；
- 旧蓝奏云 ID；
- placeholder。

必须确认旧链接数量为 0（历史页面确需保留的版本文章除外，需明确白名单）。

---

## 18. Cloudflare Pages 部署

主项目：

```bat
cd D:\lpproduct\magnet
npx wrangler pages deploy magnetgoogo-site --project-name=magnetgoogo-site --branch=main
```

部署后验证：

```text
https://magnetgoogo.com/config.json
官网首页/英文页/至少一页其它语言
下载按钮
announcement
```

config 应采用 no-cache/no-store 策略，避免旧 mutable config 长时间缓存。

---

## 19. `mg-data` config 发布

```bat
cd D:\lpproduct\m023\mg-data
git status --short
git add config.json
git commit -m "chore: publish v<version> app config"
git push origin main
```

不要 `git add -A` 顺带提交 source pack 或测试缓存，除非它们也是本次明确发布内容。

GitHub Raw 是当前 config 首 authority，因此 **mg-data config 内容必须在用户可见切换前完全正确**。

---

## 20. 阿里云官网/config 发布

发布前先建 rollback 备份，再同步官网/config。

历史使用：

```text
/var/www/magnetgoogo-site
```

建议每次：

```text
/var/www/magnetgoogo-site.pre-v<version>-<timestamp>
```

上传后从**公网**确认：

- config latest/min；
- primary/mirrors；
- HTML 下载按钮；
- TLS 正常。

---

## 21. 公开 config 收敛检查

至少：

```text
GitHub Raw
magnetgoogo.com
api.naoshiquan.com
cn.magnetgoogo.com
workers.dev fallback
jsDelivr fallback/immutable
```

检查字段：

```text
latest_version
min_version
primary
mirrors
announcement
updated_at
```

对 mutable authorities，内容必须一致或符合设计的明确 authority/fallback关系。

不要只比较文件大小。

---

## 22. APK 渠道 exact SHA 检查

正式发布完成后，以下能直接取得 bytes 的渠道必须与本地 archive SHA 一致：

```text
local releases/
R2 primary
GitHub Release asset
Aliyun stable
Aliyun versioned archive
```

蓝奏云如果受网页密码/脚本保护而无法稳定自动回下载，只能标“落地页/文件名人工验证”，不能假报 exact SHA。

---

## 23. 发布后生产 App 更新 E2E

这是最终必做项。

1. K30S 安装一个真实旧正式版；
2. 记录 `firstInstallTime`；
3. 启动旧版；
4. 从**公网 config**看到新版本；
5. announcement/版本号正确；
6. 点击立即更新；
7. App 内从 primary 下载 APK；
8. size + ZIP/APK header guard 通过；
9. App 自己 `content:// + ACTION_VIEW` 拉起 MIUI；
10. MIUI 显示 MagGoogo 更新；
11. 用户确认；
12. 安装后 version/code = 新版；
13. `firstInstallTime` 不变；
14. 历史/收藏等关键数据保留；
15. 搜索/资源/详情正常；
16. Fatal/ANR=0。

**只验证 `adb install -r` 不能替代这条生产更新链。**

---

## 24. 更新失败回退策略

客户端当前：

```text
primary/direct candidates
→ 下载失败删除坏文件
→ 下一 direct candidate
→ 全失败后浏览器 fallback
```

APK guard：

```text
>= 5 MiB
ZIP/APK magic
```

蓝奏云网页不是 direct APK candidate，避免把 HTML 当 APK。

安装 intent 失败时，回退浏览器渠道。

---

## 25. 回滚

### config 回滚

如果 APK 文件本身没问题、只是 config 文案/链接错误：

- 修正 config；
- 推 GitHub Raw authority；
- Pages/Gateway/Aliyun 收敛；
- 不需要重发 APK。

### APK 回滚

Android versionCode 不能对公众“降级覆盖”作为正常回滚策略。

严重 App bug 应：

1. 修复；
2. 新 versionName/versionCode；
3. 同签名重新发版。

### signer 问题

任何 signer mismatch：**停止发布**，不要让用户卸载重装来掩盖错误，除非这是明确的不可恢复签名迁移事故并有用户公告。

---

## 26. 历史事故必须防止复发

详细见 `USER-IMPACT-INCIDENTS.md`。发版尤其关注：

- keystore 放 android 后被 prebuild clean 删除；
- APK 未上传就先切 config；
- 蓝奏云占位/旧链接上线；
- 官网仍硬编码旧版本；
- mutable config 快旧镜像抢赢新 authority；
- 同版本旧 candidate 冒充 final APK 真机验收；
- App 内安装链只测 `adb install`，没有测 `content://`/MIUI；
- 更新中 Android back 隐藏 modal 但下载继续。

---

## 27. 发版最终 Checklist

### Build

```text
[ ] versionName/versionCode/package 正确
[ ] TypeScript PASS
[ ] adversarial PASS
[ ] resource/media/update/release gates PASS
[ ] source gates（如受影响）PASS
[ ] forced final Release build PASS
[ ] verify_release_apk PASS
[ ] signer exact previous match
[ ] arm64-v8a only
[ ] final SHA 固定
```

### K30S final bytes

```text
[ ] adb install -r Success
[ ] installed SHA = final SHA
[ ] retained-data upgrade
[ ] repeated-search freshness
[ ] main/resource/detail/favorites/settings smoke
[ ] HOT/COLD lifecycle
[ ] Fatal/ANR=0
```

### Archive/channel preparation

```text
[ ] releases/magnetgoogo-v<NEW>.apk exact final SHA
[ ] R2 uploaded + full redownload SHA match
[ ] Aliyun stable/versioned SHA match
[ ] GitHub Release asset SHA match
[ ] Lanzou new link manually verified
```

### Config/site

```text
[ ] latest/min correct
[ ] primary=R2 new APK
[ ] Lanzou/GitHub mirrors correct
[ ] announcement correct
[ ] no placeholder
[ ] mg-data authority pushed
[ ] Pages deployed
[ ] Aliyun site/config deployed
[ ] old links audit = 0 unexpected
[ ] public config authorities converge
```

### Production E2E

```text
[ ] real old formal version installed
[ ] public update prompt correct
[ ] in-App primary APK download works
[ ] MIUI installer source is MagGoogo
[ ] user-confirmed retained-data upgrade
[ ] post-upgrade search/resource PASS
[ ] Fatal/ANR=0
```

只有全部完成才标：

```text
PUBLIC_RELEASE=PASS
PRODUCTION_UPDATE_E2E=PASS
```

---

## 28. 相关文档

- `DOC-INDEX.md`
- `K30S-INSTALL-PLAYBOOK.md`
- `K30S-TEST-PLAYBOOK.md`
- `SOURCE-RELEASE-PLAYBOOK.md`
- `APP-SIGNING.md`
- `USER-IMPACT-INCIDENTS.md`
- `TEST-RESULT-20260805-v0.2.5全链路公开发布与0.2.3公网升级验收.md` — 上一次完整生产发布证据
