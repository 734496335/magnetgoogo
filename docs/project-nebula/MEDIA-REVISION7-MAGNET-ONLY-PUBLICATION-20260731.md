# 影视资源 Revision 7 仅磁力正式发布记录（2026-07-31）

## 最终结论

`RELEASE=PASS`

`POINTER_REVISION=7`

`APP_COMPATIBILITY=V0.2.3_PASS`

`RESOURCE_POLICY=MAGNET_ONLY`

本轮按用户确认边界正式发布新的影视资源 revision：

- 其他国家电视剧可以不在当前五类剧集频道展示；
- 烂番茄、Bangumi等评分字段可以保留，当前0.2.3不要求展示；
- 正式发布只允许磁力资源，所有网盘资源均移除；
- 不修改App版本、不重新打包APK。

## 正式身份

- pointer revision：7；
- release ID：`20260730T000000Z-5c299304`；
- pointer SHA-256：`0068f832ee016fa22d35939d5250d711f1aa40f60d121e4ad6501fe1f6c80f93`；
- Manifest SHA-256：`83f38186a06457a8e5bb8ddcda7587b9accbfa1f93bd477b15213b2bff8f02e8`；
- min_app_version：`0.2.3`；
- R2：`https://media.magnetgoogo.com`；
- 阿里云：`https://cn.magnetgoogo.com/media`。

## 磁力-only重裁

原四源聚合数据：

- 电影199部；
- 电视剧237部；
- 总资源4468条；
- 磁力3541条；
- 网盘927条。

正式过滤规则：

1. 只保留`resource_type=magnet`；
2. provider统一验证为`magnet`；
3. magnet URI必须包含唯一40位info-hash；
4. URI中的info-hash必须与字段值一致；
5. 电影和电视剧之间全局info-hash不得重复；
6. 移除网盘后没有任何磁力的影视不得进入revision。

最终结果：

| 类型 | 输入影视 | 正式影视 | 删除零磁力影视 | 正式磁力 |
|---|---:|---:|---:|---:|
| 电影 | 199 | 199 | 0 | 300 |
| 电视剧 | 237 | 220 | 17 | 3241 |
| 合计 | 436 | 419 | 17 | 3541 |

网盘资源移除927条；正式资源对象中cloud数量为0。3541个info-hash全部唯一。

## 封面与发布对象

此前四入口400张封面已经真实下载、解码和SHA-256验证。正式构建复用这些验证资产，不重新依赖当前异常的SixV封面TLS路径。

- 电影：199/199封面命中，网络请求0；
- 电视剧：220/220封面命中，网络请求0；
- 唯一封面对象：368；
- 详情对象：419；
- 资源对象：419；
- Catalog对象：19；
- Manifest对象：1；
- 不可变文件总数：1226；
- 总字节：24,235,882。

离线Bundle审计：

- movie：199条、199封面、300资源，PASS；
- series：220条、220封面、3241资源，PASS；
- 缺标题、缺封面、零资源、非法资源和重复资源均为0。

## 0.2.3展示兼容性

0.2.3自身TypeScript协议解析器对revision 7全部对象实测通过：

- `media-current/1`：PASS；
- `media-manifest/1`：PASS；
- `media-catalog/1`：19/19；
- `media-detail/1`：419/419；
- `media-resources/1`：419/419；
- 资源：3541条磁力、0条cloud；
- 标题、封面、详情路径、资源数量均可正常消费。

当前0.2.3页面实际可见范围：

| 页面频道 | 影视数量 | 磁力数量 |
|---|---:|---:|
| 电影 | 199 | 300 |
| 国产剧 | 50 | 318 |
| 美剧 | 108 | 2418 |
| 英剧 | 16 | 162 |
| 韩剧 | 23 | 112 |
| 日剧 | 2 | 2 |
| 可见合计 | 398 | 3312 |
| 其他国家剧集（无当前Tab） | 21 | 229 |

其他国家剧集仍能被客户端协议下载和缓存，但当前页面无入口；这是用户明确接受的边界。

烂番茄、Bangumi等评分字段不会破坏协议，但0.2.3不展示，留待下一App版本优化。

## 质量门禁

- 磁力-only专项：4 passed；
- Media Release专项：22 passed；
- Resource Index全量：300 passed，1 skipped；
- compileall：PASS；
- enum：241 rules / ALL VALID；
- App Resource Feed：PASS；
- App Media Security：PASS；
- App Media Cache：PASS；
- TypeScript：PASS；
- 0.2.3候选对象真实协议解析：PASS；
- 发布后双端App网络协议测试：PASS。

唯一“unknown series resource”原因为中文资源名“英雄四季全”。发布门禁原先只识别“全季”，本轮补充“季全”识别并加入永久测试；最终unknown=0、cross-season=0。

## R2不可变发布

首轮：

- 新上传：759；
- 已复用：467；
- 总验证：1226；
- Manifest上传并验证；
- current未发布。

第二轮：

- 新上传：0；
- 已复用：1226；
- 完整幂等复用：PASS；
- 临时上传Worker已删除。

## 阿里云不可变发布

部署脚本首次暴露Linux远程shell兼容问题：

- 默认shell不支持`pipefail`；
- PowerShell here-string的CRLF会污染远端命令。

正式修复：

- `set -euo pipefail`改为POSIX兼容的`set -eu`；
- SSH执行前将CRLF规范化为LF并Trim；
- 最小远程shell探针返回`media-shell-pass`。

正式同步结果：

- 首轮复制1226；
- 第二轮复用1226；
- Nginx配置检查PASS并reload；
- 公开Manifest与Catalog、封面、详情、资源对象抽验SHA全部匹配；
- current在数据发布阶段保持未发布。

## current原子提升

提升前：

- R2 current：revision 6；
- 阿里云current：404；
- 两端revision 7 Manifest均已存在并通过SHA验证。

提升后：

- R2 current：revision 7；
- 阿里云current：revision 7；
- 两端pointer字节SHA均为`0068f832ee016fa22d35939d5250d711f1aa40f60d121e4ad6501fe1f6c80f93`；
- 两端Manifest SHA均为`83f38186a06457a8e5bb8ddcda7587b9accbfa1f93bd477b15213b2bff8f02e8`；
- 发布后App双端协议测试均返回199电影、220电视剧、3541资源。

## 证据目录

`D:\lpproduct\magnet-revision7-magnet-only-20260731`

主要收据：

- R2首轮：`r2-worker-bridge-8384a82b53-20260730T000000Z-5c299304-r7-16f58b405fa1.json`；
- R2复用轮：`r2-worker-bridge-8384a82b53-20260730T000000Z-5c299304-r7-b1dcdd305169.json`；
- 阿里云：`aliyun-media-4ba2ec53acbf4101a8bf1a7bc2061ab4.json`；
- current提升：`media-current-4f0edb202ea4483a9c4accb530d43743.json`。

## 最终边界

- K30S在发布后未连接ADB，因此未补做真机页面点击和断网重启测试；
- 正式0.2.3的协议、缓存和上一版revision 6已完成过K30S验收，本轮revision 7使用相同协议；
- 本次没有修改0.2.3 APK、版本号或更新公告；
- 0.2.2及更旧版本不作为本revision目标客户端，pointer的`min_app_version`为0.2.3。
