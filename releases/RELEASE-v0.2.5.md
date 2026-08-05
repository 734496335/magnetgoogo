# MagnetGoogo v0.2.5 正式包

状态：**已完成全链路公开发布并通过K30S公网升级验收**

## 制品

```text
D:\lpproduct\m023\magnetgoogo-app\android\app\build\outputs\apk\release\app-release.apk
```

```text
package=com.magnetgoogo.app
versionName=0.2.5
versionCode=9
size=38,510,706 bytes
sha256=642447c18e12f81b167f5a9b711726a6ced28079d7f078678151d05bdea9da70
abi=arm64-v8a
certificate_sha256=475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d
```

签名证书与正式v0.2.3一致，可以保留数据覆盖升级。

## 主要功能

- 新增烂番茄、Bangumi评分协议、缓存和UI支持；
- 列表和详情支持豆瓣、IMDb、烂番茄、Bangumi四评分；评分统一使用0.2.3紧凑胶囊样式，不使用大卡片；
- 修复0.2.3旧缓存同revision升级后不补齐新评分；
- 修复SSBC bytes/KiB混合导致的1024倍容量错误；
- 修复多磁力详情页容量错绑、同Hash大小合并异常；
- 修复Hash占位、泛化标题、非法BTIH和Base32/Hex重复卡片；
- 修复日期、文件数量及详情页磁力提取错误；
- 新增逐源搜索结果质量审计。

## K30S验收

- 正式0.2.3与0.2.5证书一致，保留数据覆盖升级成功；
- 使用正式0.2.3和公开0.2.5配置完成生产更新E2E：显示3条更新说明、App内从R2下载、自动拉起MIUI安装器、系统显示“0.2.3→0.2.5 / 安装来源：MagGoogo”、用户确认后数据保留升级PASS；
- 正式搜索覆盖影视、软件、动漫和代码型资源；
- 四评分在线补齐、详情水合和断网冷启动PASS；
- 前后台搜索完成后服务自动清理；
- Fatal=0，ANR=0；
- 147源/51池保持，不因国内网络失败批量收敛。

完整证据：

```text
docs/project-nebula/TEST-RESULT-20260803-v0.2.5正式包K30S充分验收.md
docs/project-nebula/TEST-RESULT-20260804-v0.2.3到v0.2.5-App内更新全链路.md
docs/project-nebula/TEST-RESULT-20260805-v0.2.5全链路公开发布与0.2.3公网升级验收.md
```

## 公开渠道

- GitHub Release：`https://github.com/734496335/magnetgoogo/releases/tag/v0.2.5`
- R2：`https://api.naoshiquan.com/download/v0.2.5/magnetgoogo-v0.2.5.apk`
- 阿里云：`https://cn.magnetgoogo.com/download/magnetgoogo.apk`
- 蓝奏云：`https://wwbdy.lanzn.com/iWEhg40m9q5c`，密码`8888`
- 官网、mg-data、maggoogo-sources、Gateway及jsDelivr配置均已发布为0.2.5。

`min_version`保持`0.1.10`，不强制升级；搜索源包和影视revision未随本次App发布变更。
