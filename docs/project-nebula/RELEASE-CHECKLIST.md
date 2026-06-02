# 版本发布完整指南 (Release Guide)

> **唯一权威发版文档。** 每次发布新版本时逐步执行，勾选完成项。
>
> 签名信息见 `APP-SIGNING.md`。变更日志见 `APP-CHANGELOG.md`。

---

## ⚠️ 铁律（血的教训）

1. **config.json 必须先改完再部署** — 所有字段（版本号、蓝奏云链接、公告文案）确认无误后，才能执行任何部署命令
2. **每个端点部署后必须验证** — `curl` 检查远程文件内容，不能假设部署成功
3. **apk 和 config.json 是两条独立链路** — APK 上传阿里云 ≠ config.json 更新，必须分别操作和验证
4. **`npx expo prebuild --clean` 会删除 keystore** — 执行前必须备份 `android/app/magnetgoogo-release.keystore`
5. **`encrypt_sources.py --verify` 会重新生成加密文件** — 不要在推送后执行，否则产生未提交的 diff
6. **mg-data 仓库是独立 git repo** — 路径是 `d:\lpproduct\magnet\mg-data`，不在 `magnetgoogo-app` 内

---

## 1. 下载链接架构

### 1.1 稳定链接（永不变更）

| 链接 | 部署位置 | 用途 |
|------|----------|------|
| `https://cn.magnetgoogo.com/download/magnetgoogo.apk` | 阿里云 `/var/www/apk/magnetgoogo.apk` | **全站主下载按钮** |
| `https://github.com/734496335/magnetgoogo/releases/latest` | GitHub Releases | **SEO 页备用按钮** |

### 1.2 易变链接（每次发版需更新）

| 链接 | 所在文件 | 更新方式 |
|------|----------|----------|
| 蓝奏云链接 | `magnetgoogo-site/index.html` × 1 处 + `config.json` | 手动替换 |
| JSON-LD `softwareVersion` | `index.html` + 9 个 `{lang}/index.html` | 搜索替换版本号 |

### 1.3 六个数据端点

App 启动时从以下 6 个端点竞速拉取 `config.json` 和 `sources.enc.json`：

| 端点 | URL | 基础设施 | 更新方式 |
|------|-----|----------|----------|
| ① | `cn.magnetgoogo.com` | 阿里云 Nginx | `scp` 到 `47.103.155.154` |
| ② | `magnetgoogo.com` | Cloudflare Pages | `wrangler pages deploy` |
| ③ | `cdn.jsdelivr.net/gh/734496335/mg-data@main` | jsDelivr CDN | 推送 mg-data GitHub |
| ④ | `raw.githubusercontent.com/734496335/mg-data/main` | GitHub Raw | 推送 mg-data GitHub |
| ⑤ | `api.naoshiquan.com` | CF Gateway Worker | 从端点②拉取，5 分钟缓存 |
| ⑥ | `maggoogo-gateway.workers.dev` | CF Workers（旧） | 独立维护 |

> **关键**：端点 ⑤ 的 config.json 来自端点 ②（CF Pages），有 5 分钟缓存。部署 CF Pages 后需等 5 分钟端点 ⑤ 才会更新。

---

## 2. 版本号位置索引

### 2.1 App 源码（3 处）

| 文件 | 字段 |
|------|------|
| `magnetgoogo-app/app.json` | `expo.version` |
| `magnetgoogo-app/package.json` | `version` |
| `magnetgoogo-app/android/app/build.gradle` | `versionCode`（只增不减）/ `versionName` |

### 2.2 远程配置（1 处，但部署到 6 个端点）

| 文件 | 字段 |
|------|------|
| `magnetgoogo-site/config.json` | `latest_version`, `min_version`, `download.mirrors`, `announcement`, `updated_at` |

### 2.3 官网元数据（10 处）

| 文件 | 内容 |
|------|------|
| `magnetgoogo-site/index.html` | JSON-LD `softwareVersion` + 蓝奏云链接 |
| `magnetgoogo-site/{lang}/index.html` × 9 | JSON-LD `softwareVersion` |

---

## 3. 发版完整流程

> ⚠️ **严格按顺序执行，不能跳步。每步完成后勾选。**

### Phase A：准备（本地操作，不影响线上）

#### A1. 修改版本号（3 处源码）

```
magnetgoogo-app/app.json          → expo.version: "{NEW}"
magnetgoogo-app/package.json      → version: "{NEW}"
magnetgoogo-app/android/app/build.gradle → versionCode +1, versionName: "{NEW}"
```

#### A2. 构建 Release APK

```bash
cd magnetgoogo-app

# 1. 导出 JS Bundle
npx expo export --platform android

# 2. 复制 Bundle 到 Android assets（必须！否则 APK 无 JS 代码）
mkdir -p android/app/src/main/assets
cp dist/_expo/static/js/android/*.hbc android/app/src/main/assets/index.android.bundle

# 3. 构建（跳过 lint 检查避免无关报错）
cd android
./gradlew assembleRelease -x lintVitalRelease -x lintVitalAnalyzeRelease -x lintVitalReportRelease
```

> **注意**：`gradle.properties` 必须包含以下配置，否则 APK 会膨胀到 80MB+：
> ```
> reactNativeArchitectures=arm64-v8a
> android.enableMinifyInReleaseBuilds=true
> android.enableShrinkResourcesInReleaseBuilds=true
> ```

产出：`magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk`

#### A3. 验证 APK

```bash
# 签名验证
java -jar "$ANDROID_SDK/build-tools/36.0.0/lib/apksigner.jar" verify --print-certs app-release.apk

# 大小验证（应为 25-35MB，超过 50MB 说明 ABI 或 minify 有问题）
ls -lh app-release.apk
```

- [ ] 签名指纹与 `APP-SIGNING.md` 一致
- [ ] 大小 < 40MB

#### A4. 归档

```bash
cp magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk releases/magnetgoogo-v{VERSION}.apk
```

#### A5. 更新 config.json（**先改完再部署！**）

编辑 `magnetgoogo-site/config.json`，**所有字段一次性改完**：

```json
{
  "latest_version": "{NEW}",
  "min_version": "{MIN_VER}",
  "download": {
    "primary": "https://cn.magnetgoogo.com/download/magnetgoogo.apk",
    "mirrors": ["https://wwbdy.lanzn.com/{LANZOU_ID}"]
  },
  "announcement": "v{NEW} 更新说明\n⚠️ 提示信息\n蓝奏云密码: 8888",
  "source_expiry_hours": 72,
  "source_schema_version": 1,
  "updated_at": "{ISO_TIMESTAMP}"
}
```

- [ ] `latest_version` 正确
- [ ] `min_version` 正确（可选更新 vs 强制更新）
- [ ] 蓝奏云链接正确（不是 `REPLACE_WITH_NEW_LINK`！）
- [ ] `announcement` 文案正确

#### A6. 同步 config.json 到 mg-data

```bash
cp magnetgoogo-site/config.json mg-data/config.json
```

#### A7. 更新官网（10 个文件）

```powershell
$old = "{OLD_VERSION}"
$new = "{NEW_VERSION}"
$oldLanzou = "{OLD_LANZOU_ID}"
$newLanzou = "{NEW_LANZOU_ID}"

@("index.html","en\index.html","ja\index.html","ko\index.html","es\index.html","fr\index.html","de\index.html","ru\index.html","pt\index.html","ar\index.html") | ForEach-Object {
  $f = "d:\lpproduct\magnet\magnetgoogo-site\$_"
  if (Test-Path $f) {
    $c = Get-Content $f -Raw -Encoding UTF8
    $c = $c -replace "`"$old`"", "`"$new`""
    if ($_ -eq "index.html") { $c = $c -replace $oldLanzou, $newLanzou }
    [System.IO.File]::WriteAllText($f, $c, [System.Text.Encoding]::UTF8)
    Write-Host "Updated: $_"
  }
}
```

---

### Phase B：部署（线上操作，按顺序执行）

> ⚠️ **config.json 必须在 Phase A 中全部改完。Phase B 只做部署，不改内容。**

#### B1. 上传 APK 到阿里云稳定链接

```powershell
scp releases/magnetgoogo-v{VERSION}.apk admin@47.103.155.154:/var/www/apk/magnetgoogo.apk
```

- [ ] 验证：`ssh admin@47.103.155.154 "ls -lh /var/www/apk/magnetgoogo.apk"` — 文件大小和时间戳正确

#### B2. 蓝奏云上传（手动）

网页操作，获取新链接 ID（密码: 8888）。

- [ ] 蓝奏云链接已获取

#### B3. GitHub Release

```powershell
$env:GITHUB_PAT = "{YOUR_TOKEN}"
# 执行 Step 4c 的 PowerShell 脚本（见下方）
```

- [ ] GitHub Release 页面能看到新版本和 APK

#### B4. 推送 mg-data 到 GitHub

```powershell
cd D:\lpproduct\magnet\mg-data; git add -A; git commit -m "chore: v{VERSION} config"; git push
```

> 推送后端点 ③④ 立即生效（端点 ④ 秒级，端点 ③ jsDelivr 几分钟）

- [ ] 验证：`curl -s "https://raw.githubusercontent.com/734496335/mg-data/main/config.json"` — 内容正确

#### B5. 部署 Cloudflare Pages

```powershell
cd D:\lpproduct\magnet\magnetgoogo-site; npx wrangler pages deploy . --project-name=magnetgoogo-site --branch=main --commit-dirty=true
```

> 部署后端点 ② 立即生效，端点 ⑤（CF Gateway）5 分钟后生效

- [ ] 验证：`curl -s "https://magnetgoogo.com/config.json"` — 内容正确

#### B6. 同步到阿里云

```powershell
scp magnetgoogo-site/config.json admin@47.103.155.154:/var/www/magnetgoogo-site/config.json
scp magnetgoogo-site/index.html admin@47.103.155.154:/var/www/magnetgoogo-site/index.html
```

- [ ] 验证：`ssh admin@47.103.155.154 "cat /var/www/magnetgoogo-site/config.json"` — 内容正确

---

### Phase C：源更新（如果 sources.json 有变化）

#### C1. 加密源

```bash
cd d:/lpproduct/magnet
python encrypt_sources.py
# ⚠️ 不要用 --verify，它会重新生成文件导致 diff
```

- [ ] 输出显示 green 数量正确

#### C2. 推送到 mg-data

```powershell
cd D:\lpproduct\magnet\mg-data; git add -A; git commit -m "chore: v{VERSION} sources ({N} green)"; git push
```

#### C3. 同步到阿里云

```powershell
scp mg-data/sources.enc.json admin@47.103.155.154:~/sources.enc.json
ssh admin@47.103.155.154 "sudo cp ~/sources.enc.json /var/www/sources.enc.json"
```

#### C4. 验证（6 个端点逐一检查）

```powershell
# 端点①阿里云
ssh admin@47.103.155.154 "wc -c /var/www/sources.enc.json"
# 端点②CF Pages
curl -s "https://magnetgoogo.com/sources.enc.json" | python -c "import sys; print(len(sys.stdin.read()))"
# 端点③④GitHub
curl -s "https://raw.githubusercontent.com/734496335/mg-data/main/sources.enc.json" | python -c "import sys; print(len(sys.stdin.read()))"
```

---

### Phase D：验证（端到端）

- [ ] **下载按钮**：访问 `magnetgoogo.com` → 点下载 → 确认 APK 是新版本（大小正确）
- [ ] **蓝奏云**：访问蓝奏云链接 → 确认文件正确
- [ ] **更新提示**：旧版 App 打开 → 确认弹出更新提示 → 文案正确 → 蓝奏云链接正确
- [ ] **源数量**：新安装 App → 搜索 → 确认源数量正确
- [ ] **SEO 页面**：随机抽查 2 个 → 下载按钮指向稳定链接

---

### Phase E：收尾

- [ ] `docs/project-nebula/APP-CHANGELOG.md`：更新版本记录
- [ ] `docs/project-nebula/DEV-LOG.md`：顶部插入发版记录
- [ ] Git commit 所有本地改动

---

## 4. GitHub Release 命令

```powershell
$ver = "{VERSION}"
$body = @"
## What's New
- 优化搜索源、提升搜索性能

⚠️ 本次更新需卸载旧版后重新安装（签名变更）
官网下载：magnetgoogo.com
蓝奏云密码: 8888
"@
$json = @{ tag_name = "v$ver"; name = "v$ver"; body = $body; draft = $false; prerelease = $false } | ConvertTo-Json -Compress
$headers = @{ Authorization = "token $env:GITHUB_PAT"; Accept = "application/vnd.github+json" }

$release = Invoke-RestMethod -Uri "https://api.github.com/repos/734496335/magnetgoogo/releases" -Method Post -Headers $headers -Body ([System.Text.Encoding]::UTF8.GetBytes($json)) -ContentType "application/json; charset=utf-8"

$uploadUrl = $release.upload_url -replace '\{.*\}', ''
Invoke-RestMethod -Uri "$uploadUrl`?name=magnetgoogo-v$ver.apk" -Method Post -Headers $headers -ContentType "application/vnd.android.package-archive" -InFile "releases/magnetgoogo-v$ver.apk"
```

> 需要 `repo` 权限的 GitHub PAT。Token 创建：https://github.com/settings/tokens

---

## 5. App 内更新机制

`configChecker.ts` 启动时从 6 个端点竞速拉取 `config.json`：

- `appVersion < min_version` → **强制更新**（不可跳过）
- `appVersion < latest_version` → **可选更新**（可跳过）
- 下载链接来自 `config.download.primary`（阿里云稳定链接）

---

## 6. 源分发机制

App 从 6 个端点竞速拉取 `sources.enc.json`：

- 加密：`python encrypt_sources.py` → 输出到 `mg-data/sources.enc.json`
- 合规版：`sources-green.enc.json`（仅 5 个源，Google Play 用）
- 磁盘缓存：72 小时过期
- 更新生效：缓存过期后自动拉取，或用户清数据后立即生效

---

## 7. 签名信息

详见 `APP-SIGNING.md`。关键点：

- **Keystore 备份位置**：`releases/magnetgoogo-release-new.keystore`（git 追踪）
- **构建引用**：`android/app/build.gradle` → `file('../../../releases/magnetgoogo-release-new.keystore')`
- **versionCode 只能递增**
- **⚠️ `npx expo prebuild --clean` 会删除 keystore！** 执行前必须确认 keystore 在 `releases/` 目录有备份

---

## 8. 事故记录

### 2026-06-01: v0.1.11 蓝奏云链接部署错误

- **严重程度**：中
- **根因**：config.json 中蓝奏云链接更新在 CF Pages 部署**之后**，导致端点②⑤服务旧链接
- **影响**：用户点更新提示中的蓝奏云链接看到 `REPLACE_WITH_NEW_LINK`
- **修复**：重新部署 CF Pages
- **教训**：**config.json 必须先改完再部署，不能分步操作**

### 2026-06-01: APK 稳定链接未更新

- **严重程度**：高
- **根因**：只上传了蓝奏云，忘记上传阿里云稳定下载链接
- **影响**：官网下载按钮下载的还是旧版 APK
- **修复**：`scp` 上传到 `/var/www/apk/magnetgoogo.apk`
- **教训**：**APK 上传和 config.json 更新是两条独立链路，都要做**

### 2026-06-01: Release Keystore 丢失

- **严重程度**：高（详见 `APP-SIGNING.md`）
- **根因**：`npx expo prebuild --clean` 删除 `android/` 目录，keystore 从未 git 提交
- **影响**：签名重建，所有用户需卸载重装
- **防护**：keystore 现存于 `releases/` 目录，git 追踪

### 2026-05-13: 官网下载链接未更新 (v0.1.8 → v0.1.10)

- **严重程度**：高
- **根因**：旧页面使用带版本号的 APK URL，发版后未替换
- **修复**：全站统一为稳定链接
- **教训**：**永远不要在 SEO 页面中硬编码版本号或蓝奏云链接**
