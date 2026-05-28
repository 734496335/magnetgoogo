# 版本发布完整指南 (Release Guide)

> **唯一权威发版文档。** 每次发布新版本时逐步执行，勾选完成项。
>
> 签名信息见 `APP-SIGNING.md`。变更日志见 `APP-CHANGELOG.md`。

---

## 1. 下载链接架构（核心设计）

### 1.1 稳定链接（永不变更）

以下链接 **始终指向最新版 APK**，在 800+ SEO 落地页中引用，发版时 **只需覆盖文件，无需改任何 HTML**：

| 链接 | 部署位置 | 用途 |
|------|----------|------|
| `https://cn.magnetgoogo.com/download/magnetgoogo.apk` | 阿里云 Nginx `/var/www/apk/` | **全站主下载按钮**（首页 + 所有 SEO 页） |
| `https://github.com/734496335/magnetgoogo/releases/latest` | GitHub Releases | **SEO 页备用按钮**（alt/guide 页） |

> **规则**：所有程序化生成的 SEO 页面（alt/blog/guide/多语言）的下载按钮 **必须** 指向上述稳定链接。
> 生成器脚本 `scripts/generate-seo-pages.js` 已遵守此规则。

### 1.2 易变链接（每次发版需更新）

| 链接 | 所在文件 | 更新方式 |
|------|----------|----------|
| 蓝奏云链接 `wwbdy.lanzoue.com/xxx` | `index.html` × 1 处 | 手动替换链接 ID |
| JSON-LD `softwareVersion` | `index.html` + 9 个 `{lang}/index.html` | 搜索替换版本号 |
| `config.json` 中的 `latest_version` / `min_version` / `mirrors` | `magnetgoogo-site/config.json` | 编辑 JSON |
| GitHub README_CN.md 蓝奏云链接 | `magnetgoogo/README_CN.md` | 手动替换 |

### 1.3 链接引用统计

| 页面类型 | 数量 | 主下载链接 | 备用链接 | 发版是否需改 |
|----------|------|------------|----------|:---:|
| `index.html`（主页） | 1 | 稳定链接 ✅ | 蓝奏云（易变） | **是**（仅蓝奏云+版本号元数据） |
| `{lang}/index.html` | 9 | 稳定链接 ✅ | — | **是**（仅 softwareVersion） |
| `alt/*.html`（旧中文替代页） | ~100 | 稳定链接 ✅ | GitHub /latest ✅ | **否** |
| `{lang}/alt/*.html`（新多语言替代页） | ~630 | 稳定链接 ✅ | — | **否** |
| `guide/*.html`（旧中文教程） | ~17 | 稳定链接 ✅ | GitHub /latest ✅ | **否** |
| `{lang}/guide/*.html`（多语言教程） | ~40 | 稳定链接 ✅ | — | **否** |
| `{lang}/blog/*.html`（多语言博客） | ~50 | 稳定链接 ✅ | — | **否** |

> **结论**：发版时只需更新 **10 个文件**（1 个 index.html + 9 个 lang/index.html + 1 个 config.json），800+ SEO 页面零改动。

---

## 2. 版本号位置索引

发版时需修改版本号的所有位置：

### 2.1 App 源码（3 处）

| 文件 | 字段 | 当前值 |
|------|------|--------|
| `magnetgoogo-app/app.json` | `expo.version` | `"0.1.10"` |
| `magnetgoogo-app/package.json` | `version` | `"0.1.10"` |
| `magnetgoogo-app/android/app/build.gradle` | `versionCode` / `versionName` | `7` / `"0.1.10"` |

### 2.2 远程配置（1 处）

| 文件 | 字段 | 说明 |
|------|------|------|
| `magnetgoogo-site/config.json` | `latest_version`, `min_version`, `download.mirrors`, `announcement`, `updated_at` | App 内更新检查的数据源 |

> App 启动时从 6 个端点竞速拉取 `config.json`（见 `configChecker.ts`）：
> cn.magnetgoogo.com → magnetgoogo.com → cdn.jsdelivr.net → raw.githubusercontent.com → api.naoshiquan.com → CF Worker

### 2.3 官网元数据（10 处）

| 文件 | 内容 | 说明 |
|------|------|------|
| `magnetgoogo-site/index.html` | JSON-LD `softwareVersion` | SEO 结构化数据 |
| `magnetgoogo-site/index.html` | 蓝奏云备用链接 | 国内用户 |
| `magnetgoogo-site/{lang}/index.html` × 9 | JSON-LD `softwareVersion` | 多语言首页 |

### 2.4 GitHub 仓库（2 处）

| 文件 | 内容 |
|------|------|
| `magnetgoogo/README_CN.md` | 蓝奏云下载链接 |
| GitHub Releases | 新 Release + APK 附件 |

---

## 3. 发版完整流程

### Step 1: 修改版本号（3 处源码）

```
magnetgoogo-app/app.json          → expo.version: "{NEW}"
magnetgoogo-app/package.json      → version: "{NEW}"
magnetgoogo-app/android/app/build.gradle → versionCode +1, versionName: "{NEW}"
```

### Step 2: 构建 Release APK

```bash
cd magnetgoogo-app
npx expo export --platform android
cd android
./gradlew assembleRelease
```

产出：`magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk`

### Step 3: 归档

```bash
cp magnetgoogo-app/android/app/build/outputs/apk/release/app-release.apk releases/magnetgoogo-v{VERSION}.apk
```

### Step 4: 上传分发渠道

| # | 渠道 | 命令/操作 | 链接性质 |
|---|------|-----------|----------|
| 4a | **阿里云** | `scp releases/magnetgoogo-v{VER}.apk admin@47.103.155.154:/var/www/apk/magnetgoogo.apk` | 稳定（覆盖同名文件） |
| 4b | **蓝奏云** | 网页手动上传，获取新链接（密码: 8888） | 易变（新链接 ID） |
| 4c | **GitHub Release** | PowerShell 脚本（见下方） | 稳定（/latest 自动指向） |

##### Step 4c: GitHub Release 命令

```powershell
$ver = "{VERSION}"
$body = @"
## What's New
- ...

---
- ...
"@
$json = @{ tag_name = "v$ver"; name = "v$ver"; body = $body; draft = $false; prerelease = $false } | ConvertTo-Json -Compress
$headers = @{ Authorization = "token $env:GITHUB_PAT"; Accept = "application/vnd.github+json" }

# 创建 Release
$release = Invoke-RestMethod -Uri "https://api.github.com/repos/734496335/magnetgoogo/releases" -Method Post -Headers $headers -Body ([System.Text.Encoding]::UTF8.GetBytes($json)) -ContentType "application/json; charset=utf-8"

# 上传 APK
$uploadUrl = $release.upload_url -replace '\{.*\}', ''
Invoke-RestMethod -Uri "$uploadUrl`?name=magnetgoogo-v$ver.apk" -Method Post -Headers $headers -ContentType "application/vnd.android.package-archive" -InFile "releases/magnetgoogo-v$ver.apk"
```

### Step 5: 更新 config.json

编辑 `magnetgoogo-site/config.json`：

```json
{
  "latest_version": "{NEW}",
  "min_version": "{NEW_OR_KEEP}",
  "download": {
    "primary": "https://cn.magnetgoogo.com/download/magnetgoogo.apk",
    "mirrors": ["https://wwbdy.lanzoue.com/{NEW_LANZOU_ID}"]
  },
  "announcement": "v{NEW}: 更新说明\n蓝奏云密码: 8888",
  "source_expiry_hours": 72,
  "source_schema_version": 1,
  "updated_at": "{ISO_TIMESTAMP}"
}
```

### Step 6: 更新官网首页（仅 10 个文件）

**PowerShell 批量替换版本号元数据**：

```powershell
$old = "0.1.10"  # ← 旧版本号
$new = "0.1.11"  # ← 新版本号
$oldLanzou = "ighZS3pb0h0h"  # ← 旧蓝奏云 ID
$newLanzou = "XXXXXXXXXX"    # ← 新蓝奏云 ID

# 只需更新 index.html 和 lang/index.html（10 个文件）
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

> ⚠️ **不需要改** 800+ SEO 页面（alt/guide/blog），它们使用稳定下载链接。

### Step 7: 更新 GitHub README

编辑 `magnetgoogo/README_CN.md`：替换蓝奏云链接为新链接。

### Step 8: 部署

```powershell
# 8a. Cloudflare Pages（国际站）— 必须指定 --branch=main，否则只是 Preview！
cd magnetgoogo-site
npx wrangler pages deploy . --project-name=magnetgoogo-site --branch=main --commit-dirty=true

# 8b. 阿里云镜像（国内站）— 只需同步变更的文件
scp magnetgoogo-site/index.html admin@47.103.155.154:/var/www/magnetgoogo-site/index.html
scp magnetgoogo-site/config.json admin@47.103.155.154:/var/www/magnetgoogo-site/config.json

# 8c. mg-data GitHub（App 配置源）
# 复制 config.json 到 mg-data 仓库并推送
cp magnetgoogo-site/config.json mg-data/config.json
cd mg-data && git add -A && git commit -m "chore: v{VERSION} config" && git push

# 8d. maggoogo-sources 仓库（旧版 App 兼容）
# 同步 config.json
```

### Step 9: 验证

- [ ] 访问 `magnetgoogo.com` → 点下载按钮 → 确认 APK 是新版本
- [ ] 访问蓝奏云链接 → 确认文件名和版本正确
- [ ] 打开旧版 App → 确认弹出更新提示
- [ ] 随机抽查 2 个 SEO 页面下载按钮 → 确认指向稳定链接

### Step 10: 更新文档

- [ ] `docs/project-nebula/APP-CHANGELOG.md`：移动「未打包优化」到「已打包发布」
- [ ] `docs/project-nebula/DEV-LOG.md`：顶部插入新版本记录

---

## 4. APK 命名与存放

**命名格式**：`magnetgoogo-v{版本号}.apk`

**本地归档**：`releases/` 目录

```
releases/
├── magnetgoogo-v0.1.8.apk
├── magnetgoogo-v0.1.9.apk
├── magnetgoogo-v0.1.10.apk
└── ...
```

**远程分发位置**：

| 渠道 | 地址 | 链接性质 |
|------|------|----------|
| 阿里云 | `cn.magnetgoogo.com/download/magnetgoogo.apk` | **稳定**（同名覆盖） |
| GitHub | `github.com/734496335/magnetgoogo/releases/latest` | **稳定**（自动最新） |
| 蓝奏云 | `wwbdy.lanzoue.com/{ID}`（密码: 8888） | **易变**（每次新 ID） |

---

## 5. App 内更新机制

`configChecker.ts` 启动时从以下 6 个端点竞速拉取 `config.json`（首个成功即用）：

1. `cn.magnetgoogo.com/config.json`（阿里云）
2. `magnetgoogo.com/config.json`（Cloudflare Pages）
3. `cdn.jsdelivr.net/gh/734496335/mg-data@main/config.json`
4. `raw.githubusercontent.com/734496335/mg-data/main/config.json`
5. `api.naoshiquan.com/config.json`（CF Gateway）
6. `maggoogo-gateway.734496335lp.workers.dev/config.json`（旧 Gateway）

**更新逻辑**（`configChecker.ts`）：
- `appVersion < min_version` → **强制更新**（ForceUpdateModal，不可跳过）
- `appVersion < latest_version` → **可选更新**（OptionalUpdateModal）
- 下载链接来自 `config.download.primary`（当前：阿里云稳定链接）

> 因此 `config.json` 中的 `download.primary` 也使用稳定链接，无需改动。仅 `mirrors` 中的蓝奏云链接需更新。

---

## 6. 签名信息

详见 `docs/project-nebula/APP-SIGNING.md`。关键点：

- **Keystore 路径**：`magnetgoogo-app/android/app/magnetgoogo-release.keystore`
- **versionCode 只能递增**，不可回退
- 旧签名用户（v0.1.8 及之前）需卸载重装

---

## 7. 事故记录

### 2026-05-13: 官网下载链接未更新 (v0.1.8 → v0.1.10)

- **严重程度**：高
- **根因**：旧页面使用带版本号的 APK URL `api.naoshiquan.com/download/v0.1.8/...`，发版后未替换
- **影响**：全站 ~150 个 HTML 文件下载按钮指向旧版
- **修复**：
  1. 全站 APK 链接统一为稳定链接 `cn.magnetgoogo.com/download/magnetgoogo.apk`
  2. SEO 页面备用链接统一为 `github.com/.../releases/latest`
  3. 建立本文档防止复发
- **教训**：**永远不要在 SEO 页面中硬编码版本号或蓝奏云链接**
