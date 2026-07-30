# MagGoogo v0.2.3 正式发布

状态：已完成正式构建、K30S验收及全部公开渠道发布。

## 主要修复

- 修复影视 revision 6 长期缓存原子提交失败。
- 修复电影和电视剧并行同步时争用共享 `.index.json.backup` 的问题。
- 国内更新优先使用 R2 直连，蓝奏云排在 GitHub 前。
- App 下载增加多直链回退、APK体积和ZIP文件头校验。
- 新增 Android 安装包权限，为后续版本 App 内更新打通安装链路。
- Android 正式包固定为仅 `arm64-v8a`。

## 影视数据

- revision：6
- 电影：498
- 电视剧：469
- 资源：3,720
- Pointer SHA-256：`5efaf37f00447bafa3ea17d977d7b3a35a20a46a32c803b5ea1c7f4443bf7197`

## APK

- 文件：`magnetgoogo-v0.2.3.apk`
- 大小：`38,486,986` 字节
- SHA-256：`bbbe9b5900d69262c903ef8153c0954466956d416934ad7504caf159d6ad960d`
- 包名：`com.magnetgoogo.app`
- 版本：`0.2.3`
- versionCode：`7`
- ABI：`arm64-v8a`

## 更新说明

- 优化国内更新下载速度。
- 修复 App 内下载后无法安装的问题。
- 提升影视加载和离线使用稳定性。

## 下载

- 国内主下载：`https://api.naoshiquan.com/download/v0.2.3/magnetgoogo-v0.2.3.apk`
- 蓝奏云：`https://wwbdy.lanzn.com/iDcyE3zn4rcf`，密码`8888`
- GitHub：`https://github.com/734496335/magnetgoogo/releases/download/v0.2.3/magnetgoogo-v0.2.3.apk`

## 升级说明

已发布的 0.2.2 没有声明安装 APK 所需权限，因此 0.2.2 用户升级到 0.2.3 时，仍建议使用蓝奏云或浏览器下载完成一次迁移。安装 0.2.3 后，后续版本才具备稳定使用 App 内下载进度条并拉起安装器的基础。

## 验收

- K30S 保留数据从 0.2.2 升级到 0.2.3：PASS
- revision 6 电影、电视剧缓存提交：PASS
- 断网强杀后恢复非内置电影和剧集：PASS
- App 对抗：52/52 PASS
- 流畅性：17/17 PASS
- Fatal/ANR：0
