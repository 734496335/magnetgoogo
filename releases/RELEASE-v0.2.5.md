# MagnetGoogo v0.2.5 正式包

状态：**已构建并通过K30S验收，尚未公开发布**

## 制品

```text
D:\lpproduct\m023\magnetgoogo-app\android\app\build\outputs\apk\release\app-release.apk
```

```text
package=com.magnetgoogo.app
versionName=0.2.5
versionCode=9
size=38,510,714 bytes
sha256=2d89e372d24ee951d49ad69f17631b7b66b323e7a78d1eb23b31213a2b463b93
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

- 从正式0.2.3保留数据升级到0.2.5成功；
- 正式搜索覆盖影视、软件、动漫和代码型资源；
- 四评分在线补齐、详情水合和断网冷启动PASS；
- 前后台搜索完成后服务自动清理；
- Fatal=0，ANR=0；
- 147源/51池保持，不因国内网络失败批量收敛。

完整证据：

```text
docs/project-nebula/TEST-RESULT-20260803-v0.2.5正式包K30S充分验收.md
```

## 尚未执行

- GitHub Release上传；
- R2、阿里云、蓝奏云上传；
- 官网和远程更新配置更新；
- 提高最低强制升级版本；
- 搜索源包或媒体revision发布。
