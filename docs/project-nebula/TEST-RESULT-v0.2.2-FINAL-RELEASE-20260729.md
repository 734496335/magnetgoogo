# v0.2.2 最终正式发布验收

时间：2026-07-29（UTC+8）

## 裁决

`RELEASE=LIVE_WITH_JSDELIVR_MAIN_CACHE_DEBT`

v0.2.2 已完成正式全量发布。最终 APK、App 更新配置、GitHub Release、阿里云稳定下载、Cloudflare Pages 官网、阿里云国内官网与蓝奏云备用下载均已上线。

唯一未收敛项为 jsDelivr `@main/config.json` 的历史分支缓存；五个权威配置端点和不可变提交端点均已正确，因此不阻塞发布。

## 更新内容

更新文案仅一条：

- 大幅优化影视内容加载速度

## 最终安装包

- APK：`releases/magnetgoogo-v0.2.2.apk`
- 包名：`com.magnetgoogo.app`
- versionName：`0.2.2`
- versionCode：`6`
- ABI：仅 `arm64-v8a`
- 大小：`33,562,462` 字节
- SHA-256：`2ceb675b6d85cb5341e41fa219b0629f7e2a104bee89960359c508fabd9248eb`
- 签名证书 MD5：`df1e684bf483ceffe49062d285b17c06`

22:44 重新构建的最终 APK 晚于 22:28 的候选验收记录，因此最终 SHA 与候选文档中的旧 SHA 不同。重新核验确认版本号、签名、ABI、大小、安装与运行均正确；本报告中的 SHA 为唯一正式发布权威。

## 自动化与真机门禁

- TypeScript：PASS
- 媒体长期增量缓存策略：PASS
- 媒体签名与哈希安全：PASS
- Release 构建契约：PASS
- App 对抗测试：`52/52 PASS`
- `adb install -r` 安装最终 APK：Success
- 最终包冷启动：`305ms`，前台 Activity 正常
- Fatal Exception / ANR / native fatal signal：`0`

旧版更新链路已实测：

1. K30S 保留数据降级安装公开 v0.2.1/versionCode 5：Success。
2. 启动后收到 `v0.2.2` 更新弹窗。
3. 弹窗文案为“大幅优化影视内容加载速度”。
4. 显示“备用链接 1 / 备用链接 2”。
5. 重新升级安装最终 v0.2.2/versionCode 6：Success，冷启动正常。

## 下载与发布面

### GitHub Release

- Tag：`v0.2.2`
- 状态：正式发布，非 Draft、非 Prerelease
- Release ID：`361846896`
- 资产：`magnetgoogo-v0.2.2.apk`
- 资产大小：`33,562,462` 字节
- 回下载 SHA-256：与最终 APK 一致
- Release 说明包含唯一更新文案、新蓝奏云链接及密码

### 阿里云稳定下载

- 路径：`/var/www/apk/magnetgoogo.apk`
- 公网地址：`https://cn.magnetgoogo.com/download/magnetgoogo.apk`
- 远端大小：`33,562,462` 字节
- 远端及公网回下载 SHA-256：与最终 APK 一致

### 蓝奏云

- 地址：`https://wwbdy.lanzn.com/imCPX3zgpbkb`
- 密码：`8888`
- Chromium 打开：HTTP 200
- 密码解锁：PASS
- 显示文件：`magnetgoogo-v0.2.2.apk`
- 显示大小：`32.0 M`
- 下载按钮：PASS

蓝奏云使用动态下载中转，本轮不声称完成完整文件 SHA 回下载；GitHub 与阿里云承担可校验的正式字节权威。

## 远程配置

`mg-data/main` 发布提交：

`2a76265dba1e91246e322d72fe98fd6f5fbd1635`

五个权威端点与不可变 CDN 提交均回读：

- `latest_version=0.2.2`
- `min_version=0.1.10`
- `announcement=大幅优化影视内容加载速度`
- GitHub 镜像指向 v0.2.2 APK
- 蓝奏云镜像指向 `imCPX3zgpbkb`
- `updated_at=2026-07-29T22:46:00+08:00`

已通过端点：

1. `cn.magnetgoogo.com`
2. `magnetgoogo.com`
3. GitHub Raw `mg-data/main`
4. `api.naoshiquan.com`
5. `maggoogo-gateway.734496335lp.workers.dev`
6. jsDelivr 不可变提交 `mg-data@2a76265d...`

App 源码未来构建的不可变 CDN 兜底已固定到 `2a76265d...`。本次已发布 APK 仍内置上一不可变兜底，但首先竞速五个权威端点，五者均已正确，因此不影响当前更新。

## 官网

- Cloudflare Pages Production 部署：`https://c1ff4610.magnetgoogo-site.pages.dev`
- 阿里云国内站点：完整 911 个 HTML 页面发布
- 新蓝奏云链接覆盖：184 个 HTML/JSON 文件
- 旧蓝奏云链接残留：0
- 抽查首页、英文页、日文页、指南页、FAQ：Cloudflare 与阿里云均 HTTP 200，新链接正确、旧链接为 0
- 阿里云 Nginx：配置校验 PASS，已 reload
- 阿里云回滚目录：`/var/www/magnetgoogo-site.pre-v0.2.2-20260729T231338`

## 已知缓存债务

jsDelivr `@main/config.json` 仍命中 v0.2.1 历史缓存，包含旧 GitHub 与旧蓝奏云链接。该端点不是当前 App 的权威竞速端点；五个权威端点均已收敛，且未来构建使用不可变提交 `2a76265d...`，因此记录为非阻塞 CDN 缓存债务。
