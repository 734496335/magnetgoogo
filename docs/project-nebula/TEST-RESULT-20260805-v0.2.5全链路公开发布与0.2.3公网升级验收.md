# v0.2.5全链路公开发布与0.2.3公网升级验收

日期：2026-08-05（UTC+8）
分支：`release/v0.2.5`
源码提交：`cdcf4a8c1677e6983619ae4dad4a7ca8d94dc4dd`
标签：`v0.2.5`
结论：`PUBLIC_RELEASE=PASS / PRODUCTION_UPDATE_E2E=PASS`

## 一、最终发布制品

```text
文件：D:\lpproduct\m023\releases\magnetgoogo-v0.2.5.apk
包名：com.magnetgoogo.app
版本：0.2.5
versionCode：9
大小：38,510,706 bytes
SHA-256：642447c18e12f81b167f5a9b711726a6ced28079d7f078678151d05bdea9da70
ABI：arm64-v8a only
证书SHA-256：475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d
```

签名证书与正式0.2.3完全一致。此次重建只刷新了内置搜索源包有效期，客户端功能、版本号和签名身份未变化。

## 二、公开下载渠道

- GitHub Release：`https://github.com/734496335/magnetgoogo/releases/tag/v0.2.5`
- R2主下载：`https://api.naoshiquan.com/download/v0.2.5/magnetgoogo-v0.2.5.apk`
- 阿里云稳定地址：`https://cn.magnetgoogo.com/download/magnetgoogo.apk`
- 阿里云版本归档：`https://cn.magnetgoogo.com/download/magnetgoogo-v0.2.5.apk`
- 蓝奏云：`https://wwbdy.lanzn.com/iWEhg40m9q5c`，密码`8888`

本地、R2、GitHub和阿里云文件均绑定同一SHA-256。蓝奏云密码落地页返回HTTP 200；蓝奏云文件本体受网页密码和脚本保护，本轮未伪造自动下载哈希结论。

## 三、更新说明

中文更新提示严格为3个短句：

```text
新增多平台影视评分展示。
优化搜索性能和结果准确性。
修复若干问题并提升稳定性；蓝奏云密码：8888。
```

GitHub Release中文和英文更新部分各3条：

```text
新增多平台影视评分展示。
优化搜索性能和结果准确性。
修复若干问题并提升使用稳定性。

Added multi-source media ratings.
Improved search performance and result accuracy.
Fixed known issues and improved stability.
```

`min_version`继续保持`0.1.10`，本次为可选更新，不强制旧版本升级。

## 四、配置与官网发布

以下端点均返回`latest_version=0.2.5`、R2主下载、新蓝奏云、新GitHub资产和3行更新说明：

- `https://magnetgoogo.com/config.json`
- `https://raw.githubusercontent.com/734496335/mg-data/main/config.json`
- `https://cdn.jsdelivr.net/gh/734496335/mg-data@main/config.json`
- `https://api.naoshiquan.com/config.json`
- `https://maggoogo-gateway.734496335lp.workers.dev/config.json`
- `https://cn.magnetgoogo.com/config.json`

配置提交：

```text
mg-data：355b76d
maggoogo-sources：24c9ba6
```

Cloudflare Pages正式部署完成。官网同步审计覆盖911个HTML文件，旧0.2.3 R2直链、旧GitHub资产和旧蓝奏云ID均为0；现行0.2.5 R2直链覆盖549处。

阿里云官网部署建立回滚目录：

```text
/var/www/magnetgoogo-site.pre-v025-20260805T091305
/var/www/magnetgoogo-site.pre-v025-linkfix-20260805T092436
```

## 五、K30S公网更新全链路

设备：Redmi K30S，序列号`a1ea223a`。

1. 从正式0.2.5保留数据执行`adb install -r -d`降级到正式0.2.3/code7；
2. `firstInstallTime=2026-07-28 21:17:01`保持不变；
3. 正式0.2.3从公开配置显示`v0.2.5`和3条新说明；
4. 点击“立即更新”，App内完成公开R2 APK下载；
5. 自动拉起MIUI安装包扫描；
6. MIUI明确显示“从0.2.3更新到0.2.5”和“安装来源：MagGoogo”；
7. 点击“继续安装”后升级完成；
8. 包版本变为0.2.5/code9，首次安装时间仍不变；
9. 冷启动资源页恢复“超级少女”、豆瓣5.4、IMDb6.1、烂番茄52%；
10. Fatal=0、ANR=0，Headless/KeepAlive残留服务=0。

该流程不是静默安装。App自动完成检测、下载和拉起安装器，用户仍需在MIUI安全页面确认安装。

## 六、发布边界

- 357条源规则、147个green源、51个池保持不变；
- 未因K30S中国大陆网络不可达批量移除海外源；
- 未提高最低强制升级版本；
- 未发布新的影视revision或搜索源包业务内容；
- Bangumi客户端能力已上线，但线上revision8仍无有效Bangumi评分数据。

## 七、12:07独立复核

本轮在不修改生产环境的前提下，重新核验公开发布结果：

- GitHub Release `v0.2.5` 为正式公开版本，中文和英文各3条短更新说明；GitHub资产大小为`38,510,706`字节，摘要为`sha256:642447c18e12f81b167f5a9b711726a6ced28079d7f078678151d05bdea9da70`；
- 本地正式制品、阿里云稳定文件和阿里云版本文件的大小与SHA完全一致；
- R2公网HEAD返回`200 / application/vnd.android.package-archive / 38,510,706 bytes`；独立全量回下载连续被DevSpace连接层502中断，因此未重复宣称新取得的R2 SHA，但原发布回下载证据和K30S真实公网下载安装证据仍有效；
- GitHub Raw、jsDelivr、Cloudflare Pages、两个Gateway及阿里云服务器配置均为`latest=0.2.5 / min=0.1.10 / 3行说明 / 新蓝奏云 / 新GitHub`；
- 官网本地911个HTML文件再次审计：旧0.2.3 R2链接、旧GitHub资产和旧蓝奏云ID均为0；线上中文、英文、日文及SEO页面抽查均只指向0.2.5；
- `npm run test:update-download` PASS；`npm run test:release-build` PASS；`python validate_enum.py`输出`ALL VALID`；
- K30S当前仍为正式`0.2.5/code9`，`firstInstallTime=2026-07-28 21:17:01`保持不变，近期Fatal/ANR为0，搜索服务无残留。

独立复核结论：`PUBLIC_RELEASE_REAUDIT=PASS / PRODUCTION_STATE_UNCHANGED=YES`。
