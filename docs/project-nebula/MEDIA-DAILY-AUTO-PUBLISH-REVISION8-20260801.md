# 影视每日自动发布与 Revision 8 正式上线记录（2026-08-01）

## 最终结论

`AUTO_CRAWL=ENABLED`

`AUTO_PUBLISH=ENABLED`

`REVISION_8=PASS`

`R2_ALIYUN_CONSISTENCY=PASS`

`APP_V0.2.3_COMPATIBILITY=PASS`

阿里云每日影视任务已从 candidate-only 切换为正式自动发布：每天抓取四个影视来源、补充四类评分、构建签名 revision、发布阿里云与 R2、双端验证后原子提升 current。无内容变化时只记录 no-change，不重复生成 revision。

## 发布前候选审计

最新自动抓取候选：

- 电影：217；
- 电视剧：227；
- 影视合计：444；
- 磁力资源：3,597；
- cloud：0；
- 零资源影视：0；
- 非法 info-hash：0；
- 重复 info-hash：0；
- 缺标题：0；
- 封面 Bundle：444/444 PASS；
- 年份范围：2004—2026；
- regression：0。

相对 revision 7：候选新增28个媒体身份、移除4个目录卡片，其中“后室”和“谜探休格”属于来源身份重算/季拆分变化，不是内容实质丢失；净增加25部影视、56条磁力。

评分抽样复核了新写入的豆瓣/IMDb记录，原名、年份与IMDb ID能够对应；0.2.3不展示烂番茄和Bangumi，后两者仍保留在数据中供0.2.4使用。

## 自动发布 Worker

部署长期专用 Worker：

- Worker：`magnetgoogo-media-auto-uploader`；
- 自定义域名：`https://media-auto-publisher.magnetgoogo.com`；
- 模式：`production-auto`；
- R2绑定：`magnetgoogo-media`；
- 认证：64位随机令牌，仅保存在Cloudflare Secret和服务器root权限环境文件；
- 未授权健康检查：HTTP 401；
- 阿里云授权健康检查：HTTP 200；
- `currentPromotion=true`。

Worker只允许：

- `v1/objects/*`；
- `v1/covers/*`；
- `v1/releases/*`；
- `staging/pointers/*`；
- 通过专用 `/promote` 接口单调提升 `v1/current.json`。

提升接口拒绝revision回退、同revision不同内容、缺失Manifest、Manifest SHA不一致、非法schema和超大current对象。

## 正式签名切换

本地正式Ed25519私钥经验证：

- 与服务器正式公钥一致；
- 与0.2.3内置公钥一致；
- key ID：`339487293160996f`。

第一次正式发布被安全门禁阻断：本地候选release曾用非生产候选密钥签名，同一release内容不能由生产公钥验证。线上revision 7未发生变化。

处理方式：

1. 隔离旧候选签名release；
2. 保留最新抓取数据库、评分状态和封面缓存；
3. 使用正式私钥重新构建release；
4. 不使用签名绕过或override；
5. 发布成功后删除候选私钥备份、旧候选release和临时令牌文件。

## Revision 8 正式身份

- pointer revision：8；
- release ID：`20260731T000000Z-06b2c7ff`；
- pointer SHA-256：`36cd24b62a2d2041c3a2f045bb4186193886bd0d5e9c1f4da1bdac5edd454ab6`；
- Manifest SHA-256：`83b9763f59d8759e9a1a699032b6671cabfce6738e32b694aac6eb1deecaa5c6`；
- min_app_version：`0.2.3`；
- 电影：217；
- 电视剧：227；
- 磁力：3,597；
- 封面：393个唯一对象；
- Detail：444；
- Catalog：21；
- Manifest内对象：1,302。

正式release独立复验：

- 签名PASS；
- 1,302个对象SHA/大小/路径PASS；
- 资源身份唯一PASS；
- media ID唯一PASS；
- cover完整PASS；
- unknown series resource=0；
- cross-season resource=0；
- regression=0。

## 双端发布收据

阿里云Filesystem：

- 总对象：1,302；
- 新增：208；
- 复用：1,095；
- current提升：PASS。

R2 Worker：

- 总对象：1,302；
- 新增：183；
- 复用：1,120；
- current提升：PASS。

发布后：

- R2 current SHA：`36cd24b62a2d2041c3a2f045bb4186193886bd0d5e9c1f4da1bdac5edd454ab6`；
- 阿里云 current SHA：相同；
- 双端 current 字节一致；
- 双端 Manifest SHA：`83b9763f59d8759e9a1a699032b6671cabfce6738e32b694aac6eb1deecaa5c6`；
- 双端 Manifest 字节一致。

## 每日自动发布计划

Systemd service：

`ExecStart=/opt/magnet-media/app/deploy/resource-index/linux/run-media-daily.sh publish`

Timer：

- 每天03:30（Asia/Shanghai）；
- 随机延迟0—5分钟；
- `Persistent=true`；
- 当前enabled/active；
- 下一次：2026-08-02 03:32:47 UTC+8。

每周日14:30只读audit继续保留，不抓取、不补评分、不发布。

## 自动发布安全边界

- Docker：768MiB内存、1280MiB含Swap、1 CPU、256 PID；
- systemd：4小时硬超时；
- 每日评分：电影40＋剧集40次尝试；
- 磁盘：使用率达到80%或可用低于2GiB时拒绝运行；
- 仅磁力过滤发生在评分、Bundle和签名之前；
- regression、签名、对象hash、双端current任何一步失败均不会记录成功；
- R2提升失败时阿里云本地current自动回滚；
- 无内容变化时不产生新revision；
- 上传令牌文件权限0600；
- 正式私钥权限0600；
- 临时令牌、临时密钥文件和候选私钥已清理；
- Git中没有提交任何生产私钥或上传令牌。

## 验证

- Linux自动发布部署测试：9 passed；
- Worker安全测试：7 passed；
- Shell语法：PASS；
- Worker未授权：401；
- Worker授权：200；
- 正式release独立验证：1,302对象PASS；
- 双端current：字节一致；
- 双端Manifest：字节一致；
- revision 8公网读取：PASS。

## 当前结论

影视爬虫现在每天自动抓取和自动发布。新数据只有在抓取、仅磁力过滤、评分持久化、封面审计、正式签名、回归门、阿里云发布、R2发布和双端current验证全部通过后，才会成为客户端可见revision。
