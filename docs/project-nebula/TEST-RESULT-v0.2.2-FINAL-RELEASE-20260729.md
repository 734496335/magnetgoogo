# v0.2.2 最终正式发布验收

时间：2026-07-29（UTC+8）

## 裁决

`RELEASE=LIVE`

v0.2.2 已完成正式全量发布。最终 APK、App 更新配置、GitHub Release、阿里云稳定与版本化下载、Cloudflare Pages 官网、阿里云国内官网、蓝奏云备用下载均已上线。

当前没有阻塞性发布债务。jsDelivr `@main/config.json` 已在清理缓存后收敛到 v0.2.2。

## 更新内容

更新弹窗仅保留一条更新内容：

- 大幅优化影视内容加载速度

蓝奏云密码属于下载说明，不计入更新内容。

## 最终安装包

- APK：`D:\lpproduct\magnet\releases\magnetgoogo-v0.2.2.apk`
- 包名：`com.magnetgoogo.app`
- versionName：`0.2.2`
- versionCode：`6`
- ABI：仅 `arm64-v8a`
- 大小：`33,562,462` 字节
- SHA-256：`2ceb675b6d85cb5341e41fa219b0629f7e2a104bee89960359c508fabd9248eb`
- 签名证书 MD5：`df1e684bf483ceffe49062d285b17c06`
- Hermes 字节码 magic：`c61fbc03c103191f`

最终包晚于早期候选构建，以上 SHA 为唯一正式发布字节权威。

## 代码与构建门禁

- TypeScript：PASS
- 媒体长期增量缓存策略：PASS
- 媒体签名与哈希安全门禁：PASS
- Release 构建契约：PASS
- App 对抗测试：`52/52 PASS`
- Gradle Release：`BUILD SUCCESSFUL`
- R8 混淆与资源压缩：启用
- 原生库检查：仅 `arm64-v8a`
- APK 签名验证：PASS，备案签名与旧正式版一致

## K30S 正式包验收

- `adb install -r releases/magnetgoogo-v0.2.2.apk`：Success
- 安装后包身份：`0.2.2 / versionCode 6`
- 前台 Activity：`com.magnetgoogo.app/.MainActivity`
- 冷启动：正常
- 资源页：正常显示
- 电影详情：基础内容与完整资源正常显示
- 同一电影本地复开：正常
- 关闭网络并重启进程后读取已加载详情：正常
- Fatal Exception / ANR / native fatal signal：`0`
- 测试结束后 Wi-Fi 恢复，移动数据保持原关闭状态

正式包不会输出 Debug 性能埋点，因此不使用 `uiautomator dump` 的约 2 秒耗时作为 App 页面性能数据；该耗时主要来自 MIUI 页面树抓取。Debug 完整点击链路已验证首次完整详情约 193ms、本地复开约 45ms，用户现场确认新实现打开明显变快。

## GitHub Release

- Release：`https://github.com/734496335/magnetgoogo/releases/tag/v0.2.2`
- 状态：正式发布，非 Draft、非 Prerelease
- 资产：`magnetgoogo-v0.2.2.apk`
- 资产大小：`33,562,462` 字节
- 完整回下载 SHA-256：与本地最终 APK 一致
- Release 说明：仅一条更新内容，并包含新蓝奏云链接及密码

## 阿里云下载与国内站点

- 稳定 APK：`/var/www/apk/magnetgoogo.apk`
- 版本 APK：`/var/www/apk/magnetgoogo-v0.2.2.apk`
- 两个服务器文件 SHA-256：均与最终 APK 一致
- 从服务器通过公开 HTTPS 地址回下载：两个地址 SHA-256 均一致
- 国内配置端点：`latest_version=0.2.2`，镜像和唯一更新文案正确
- 国内中文首页、英文页、FAQ：HTTP 200，新镜像与密码正确
- Nginx 配置校验：PASS
- 站点回滚目录：`/var/www/magnetgoogo-site.pre-v022-20260729T231536`

本机 Windows Schannel 对 `cn.magnetgoogo.com` 仍存在既有 TLS 握手兼容问题，因此国内域名采用阿里云服务器侧公开 HTTPS 回读作为权威验证；这不是服务器或公网证书故障。

## 蓝奏云

- 地址：`https://wwbdy.lanzn.com/imCPX3zgpbkb`
- 密码：`8888`
- Chromium 打开并解锁：PASS
- 显示文件：`magnetgoogo-v0.2.2.apk`
- 显示大小：`32.0 M`
- 下载操作：可见并可触发

蓝奏云下载域名启用动态中转与反自动化挑战，本轮未取得可复验的完整 APK 字节，因此不声称蓝奏云文件 SHA 一致。GitHub 与阿里云承担可校验的正式字节权威；蓝奏云承担人工备用下载入口。

## App 更新配置

`mg-data` 发布提交：

`2a76265dba1e91246e322d72fe98fd6f5fbd1635`

以下配置端点最终均返回：

- `latest_version=0.2.2`
- `min_version=0.1.10`
- `announcement=大幅优化影视内容加载速度`
- 10 种语言均只有对应的一条更新内容
- GitHub 镜像指向 v0.2.2 APK
- 蓝奏云镜像指向 `imCPX3zgpbkb`

已验证端点：

1. `https://magnetgoogo.com/config.json`
2. `https://cn.magnetgoogo.com/config.json`（服务器侧公开 HTTPS 回读）
3. GitHub Raw `mg-data/main`
4. `https://api.naoshiquan.com/config.json`
5. `https://maggoogo-gateway.734496335lp.workers.dev/config.json`
6. jsDelivr 不可变提交 `mg-data@2a76265d...`
7. jsDelivr `mg-data@main`（清缓存后已收敛）

本次发布 APK 内的不可变 CDN 最末级兜底仍可能指向构建时的旧提交；App首先竞速多个权威端点，且上述端点现已全部正确，不影响 v0.2.2 更新和下载。当前源码已为未来构建固定到 `2a76265d...`。

## 官网

- Cloudflare Pages 最终部署：`https://04b9acd5.magnetgoogo-site.pages.dev`
- 自定义域名：`https://magnetgoogo.com`
- 阿里云国内站点：`https://cn.magnetgoogo.com`
- 本地生成：`911` 个 HTML 页面
- 阿里云完整站点：`963` 个文件
- 含新蓝奏云下载入口的 HTML 页面：`182`
- 含 GitHub v0.2.2 直链的 HTML 页面：`173`
- 活动发布面旧蓝奏云链接、旧 v0.2.1 APK 直链残留：`0`
- Cloudflare 代表页：中文首页、英文页、日文页、指南页、替代页、FAQ、Pages 预览，`7/7 PASS`
- 阿里云代表页：中文首页、英文页、FAQ，`3/3 PASS`

## Git 记录与边界

- 主仓库发布控制提交：`b136f6ec6d6273222281a134994389920e92aa80`
- 主仓库发布证据提交：`1805209414f04935919458abf38028d80ae3ca33`
- `mg-data` 远程配置提交：`2a76265dba1e91246e322d72fe98fd6f5fbd1635`
- `mg-data` 工作树：干净
- 主仓库未配置 Git remote，且仍包含多个并行开发的既有脏改动；本轮未将无关改动混入发布操作

## 最终结论

v0.2.2 已完成可升级正式包、更新弹窗、GitHub、阿里云、Cloudflare、远程配置、全站下载入口和蓝奏云备用地址的完整发布。所有可校验 APK 分发端字节一致，所有活动下载入口已替换为新版本和新蓝奏云链接。