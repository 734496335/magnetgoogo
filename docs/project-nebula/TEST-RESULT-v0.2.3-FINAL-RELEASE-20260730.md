# v0.2.3正式发布与公网复核

## 发布结论

- `RELEASE=PASS`
- 正式版本：`0.2.3 / versionCode 7`
- 正式APK：`releases/magnetgoogo-v0.2.3.apk`
- 大小：`38,486,986`字节
- SHA-256：`bbbe9b5900d69262c903ef8153c0954466956d416934ad7504caf159d6ad960d`
- 本地源码提交：`01555edc217fcf8db63c9af1f20c099a786337c0`

## 更新说明

1. 优化国内更新下载速度。
2. 修复 App 内下载后无法安装的问题。
3. 提升影视加载和离线使用稳定性。

## 已发布渠道

### GitHub Release

- Tag：`v0.2.3`
- Release ID：`362457736`
- 资产：`magnetgoogo-v0.2.3.apk`
- GitHub API报告大小：`38,486,986`字节
- GitHub API digest：`sha256:bbbe9b5900d69262c903ef8153c0954466956d416934ad7504caf159d6ad960d`
- 状态：非草稿、非预发布。

### Cloudflare R2国内主下载

- URL：`https://api.naoshiquan.com/download/v0.2.3/magnetgoogo-v0.2.3.apk`
- HEAD：`200`
- Content-Length：`38,486,986`
- Content-Type：`application/vnd.android.package-archive`
- 完整回下载SHA：`bbbe9b5900d69262c903ef8153c0954466956d416934ad7504caf159d6ad960d`

### 蓝奏云

- URL：`https://wwbdy.lanzn.com/iDcyE3zn4rcf`
- 密码：`8888`
- K30S浏览器页面标题：`magnetgoogo-v0.2.3.apk - 蓝奏云网盘`
- 页面文件名：`magnetgoogo-v0.2.3.apk`
- 页面显示大小：`36.7 M`

### 阿里云

- 稳定文件：`/var/www/apk/magnetgoogo.apk`
- 版本文件：`/var/www/apk/magnetgoogo-v0.2.3.apk`
- 两个服务器文件SHA均为正式SHA。
- 旧APK回滚：`/var/www/apk/magnetgoogo-v0.2.2-pre-v0.2.3-20260730.apk`
- 官网回滚目录：
  - `/var/www/magnetgoogo-site.pre-v0.2.3-20260730T2138`
  - `/var/www/magnetgoogo-site.pre-v0.2.3-r2-primary-20260730T2148`

## 配置与官网

- `mg-data`发布提交：`a7cc908`
- Cloudflare Pages最终部署：`https://efdb7645.magnetgoogo-site.pages.dev`
- 官网共911个HTML页面。
- 全站主下载统一为R2 v0.2.3。
- 全站旧v0.2.2 GitHub资产引用：0。
- 全站旧蓝奏云链接：0。
- 全站阿里云旧主下载硬编码：0。
- GitHub Raw、Cloudflare Pages、两个Gateway、jsDelivr `@main`及不可变提交均返回字节一致的v0.2.3配置。
- 配置SHA-256：`7d4f7accc078b2be9cb3e7de746ca37d17f89d33bc0e0d30819df7080733a8c5`

## K30S发布后验证

- 使用正式0.2.2保留数据降级后启动，收到`v0.2.3`更新提示。
- 三条更新说明逐字正确。
- 备用链接1实际打开新蓝奏云`iDcyE3zn4rcf`。
- 备用链接2实际打开GitHub v0.2.3 APK。
- K30S最终恢复正式`0.2.3/code7`。
- 最终启动Fatal/ANR：0。

## 影视缓存验证沿用的正式候选证据

- revision 6：498部电影、469部电视剧、3720个资源。
- 电影与电视剧Feed及共享index提交事务已串行化。
- K30S断网强杀后仍恢复非内置电影“超级少女”和非内置剧集“聪明镇”。
- `MEDIA_CACHE_COMMIT_FAILED`、`FileAlreadyExistsException`：0。

## 已知边界

1. 已发布0.2.2自身缺少`REQUEST_INSTALL_PACKAGES`，因此0.2.2升级0.2.3仍可能需要通过蓝奏云或浏览器完成一次安装；安装0.2.3后，后续版本具备App内安装基础。
2. `cn.magnetgoogo.com`在部分外部客户端仍存在TLS握手异常。官网和App主下载均已改为R2，不再依赖该域名；阿里云服务器上的APK和站点文件已正确更新。
3. v0.2.3 APK内的jsDelivr不可变兜底仍固定到旧配置提交，但只有五个权威端点全部失败时才会使用；当前五个权威端点中的Cloudflare Pages、GitHub Raw和两个Gateway均已验证为v0.2.3。后续版本应更新不可变兜底提交。

## 最终裁决

`v0.2.3`已完成正式发布，公开资产、远程配置、官网、蓝奏云、GitHub、R2、阿里云和K30S用户路径均完成复核。上述已知边界不阻塞本次发布。
