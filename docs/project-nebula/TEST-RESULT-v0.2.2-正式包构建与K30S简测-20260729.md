# v0.2.2 正式包构建与 K30S 简测

日期：2026-07-29（UTC+8）
状态：SUPERSEDED_BY_FINAL_RELEASE_REPORT

本文件记录正式包构建和K30S简测阶段。发布完成后的唯一权威报告为：

`docs/project-nebula/TEST-RESULT-v0.2.2-FINAL-RELEASE-20260729.md`

## 变更

- 中文影视加载文案由“正在加载影视…”改为“正在加载...”。
- 影视详情使用明文长期分片缓存、增量更新和卡片先显示方案。
- 清理仅用于K30S性能诊断的临时路由计时参数与Debug日志。
- 因公开版本已为0.2.1/versionCode 5，正式版本升级为0.2.2/versionCode 6。

## 最终产物

- APK：`D:\lpproduct\magnet\releases\magnetgoogo-v0.2.2.apk`
- 包名：`com.magnetgoogo.app`
- versionName：`0.2.2`
- versionCode：`6`
- ABI：仅`arm64-v8a`
- 大小：`33,562,462`字节
- SHA-256：`2ceb675b6d85cb5341e41fa219b0629f7e2a104bee89960359c508fabd9248eb`
- 签名MD5：`df1e684bf483ceffe49062d285b17c06`
- Hermes magic：`c61fbc03c103191f`

## 门禁与简测

- TypeScript：PASS
- 媒体长期增量缓存策略：PASS
- 媒体签名/哈希安全门禁：PASS
- Release构建契约：PASS
- App对抗测试：52/52 PASS
- Gradle Release：BUILD SUCCESSFUL
- K30S正式包安装：Success
- 冷启动、资源页、电影详情、本地复开和断网复用：PASS
- Fatal Exception / ANR / native fatal signal：0

## 后续状态

本候选已经完成GitHub、阿里云、Cloudflare、远程配置、官网和蓝奏云备用下载的正式发布，具体证据和最终发布边界见权威报告。