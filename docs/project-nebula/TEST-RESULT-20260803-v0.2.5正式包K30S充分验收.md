# v0.2.5正式签名包与K30S充分验收

日期：2026-08-03（UTC+8）
分支：`release/v0.2.5`
设备：K30S，序列号`a1ea223a`
结论：`FORMAL_APK=PASS / K30S=PASS / PUBLIC_RELEASE=NOT_STARTED`

## 一、正式制品

```text
文件：D:\lpproduct\m023\magnetgoogo-app\android\app\build\outputs\apk\release\app-release.apk
包名：com.magnetgoogo.app
版本：0.2.5
versionCode：9
大小：38,511,674 bytes
SHA-256：d0b866a2c54d1fdc7fabaa4fee6763436516bed4f28f1b7526bfb4988ab7500b
ABI：arm64-v8a only
证书SHA-256：475fc1647359524cef27e180421ef17401171f476e4ab41f8b423746ef0ef49d
```

`apksigner`确认0.2.5与正式0.2.3使用完全相同的发布证书，可覆盖升级。

## 二、升级安装

K30S安装前：

```text
versionName=0.2.3
versionCode=7
firstInstallTime=2026-07-28 21:17:01
```

执行`adb install -r`后：

```text
versionName=0.2.5
versionCode=9
firstInstallTime=2026-07-28 21:17:01
lastUpdateTime=2026-08-03 21:46:56
```

首次安装时间未变化，证明是保留App数据覆盖升级，不是卸载重装。

## 三、发布前发现并关闭的阻断

### 3.1 现象

首次0.2.5正式候选从0.2.3保留数据升级后，资源页“超级少女”仍只显示：

```text
豆瓣 5.4
IMDb 6.1
```

线上revision8已包含烂番茄52%，但因为pointer revision未变化，0.2.3生成的旧Feed缓存被直接返回，新客户端没有重新执行四评分映射。

### 3.2 修复

- Feed缓存消费版本从`media-app-feed-cache/2`升级到`/3`；
- 旧`/2`缓存仍可在离线环境使用，不会因升级导致资源页为空；
- 网络可用且pointer未变化时，检测到旧消费版本会重新读取长期缓存的原始Catalog并执行新映射；
- 原始Catalog按内容Hash复用，不重复下载全部目录对象；
- Detail缓存升级到`media-app-detail-cache/3`；
- 旧详情缺少新评分时，不得覆盖Catalog中已经补齐的烂番茄和Bangumi字段。

### 3.3 真机复验

不清除任何K30S App数据、线上revision仍为8，再次覆盖安装修复后的正式包：

```text
超级少女：豆瓣5.4 / IMDb6.1 / 烂番茄52%
其他首屏条目：出现烂番茄75%、33%
MEDIA_CACHE_COMMIT_FAILED=0
Fatal=0
ANR=0
```

该反例证明同revision旧缓存可以自动升级，而不是要求用户清缓存。

## 四、正式包搜索验证

### 4.1 资源大小原始反例

关键词`消失的人`：

```text
完成结果：18条
首条：2160p / 60fps / WEB-DL / HEVC
显示：25.13 GB / 2026-08-03
```

未再出现历史错误`24.7 MB`，也没有B级容量、Hash标题或异常TB放大。

### 4.2 多类型正式UI

| 查询 | 完成结果 | 主要验证 |
|---|---:|---|
| Inception | 122 | 720p、1080p、4K容量合理；无Hash标题 |
| Ubuntu | 126 | 761MB—2.53GB区间合理；日期正常 |
| One Piece | 222 | 单集、季度包和文件数展示正常 |
| SSIS-001 | 67 | 合法BTIH、标题、容量及文件数正常 |
| The Matrix | 58 | 前后台恢复并完成，4K标题正常 |

示例：

```text
Inception 720p：1.07 GB
Inception 1080p：1.85 GB / 8.14 GB
Inception UHD Remux：86.2 GB
Ubuntu：761 MB / 1.79 GB / 1.98 GB / 2.29 GB / 2.53 GB
One Piece 1080p单集：1.36 GB
One Piece 720p单集：707.79 MB
One Piece S02季度包：6.03 GB
```

未复现以下历史问题：

- `27801GB / 10872GB / 7B / 89B`；
- `File Size 771.59MB → 文件数771`；
- 页面多个磁力共用同一个错误容量；
- 非法日文文本被放入BTIH；
- Download、Details、纯URL、纯Hash作为标题。

## 五、147源逐源质量门

正式包不包含Debug逐源日志接口，因此使用与正式包同一源码、同一147源内置包的0.2.5 Debug变体执行穷尽审计。

最终`Inception`复验：

```text
运行源：147/147
运行池：51/51
完成耗时：121.228秒
原始磁力：109
可访问源：53
有结果源：13
Hash占位标题：0
结果质量硬错误：0
结果质量告警：0
```

本次搜索代码此前完成八类最终矩阵：英文/中文电影、英文/中文动漫、英文/中文剧集、软件ISO、代码型标题，共1176次逐源执行、3288条结果，硬错误0。最终缓存修复不改搜索实现；本轮又对当前提交绑定源码重跑147源`Inception`，结果仍为0硬错误。

按用户要求，国外源不会因为K30S中国大陆网络超时而被全局移除：

```text
完整规则：357
运行green：147
运行池：51
```

只有已证明与网络地域无关、无论关键词均返回固定首页内容的`u3c3`被降为yellow保留。

## 六、四评分与详情页

正式资源列表：

```text
豆瓣、IMDb、烂番茄按固定顺序显示
超级少女：豆瓣5.4 / IMDb6.1 / 烂番茄52%
空评分不产生空胶囊
```

正式详情页：

```text
豆瓣 / IMDb / 烂番茄评分卡正常
剧情简介正常
查看资源（1）正常
```

线上revision8当前没有有效Bangumi条目，因此不能声称正式线上已看到Bangumi；Bangumi由签名冻结release、协议映射和2×2组件永久测试验证。

## 七、离线缓存

完成在线列表和详情水合后：

1. 关闭Wi-Fi与移动数据；
2. 强制停止正式App；
3. 冷启动进入资源页；
4. 再次进入“超级少女”详情。

离线仍恢复：

```text
豆瓣5.4
IMDb6.1
烂番茄52%
剧情简介
查看资源（1）
```

证明Feed `/3`、Detail `/3`及四评分已真正落盘。测试后Wi-Fi、移动数据和三项系统动画比例均恢复。

## 八、前后台与服务清理

搜索`The Matrix`后8秒切到后台，45秒后返回：

- Headless和KeepAlive服务正常接管；
- App热恢复，无崩溃；
- 国内网络下保留147源导致长尾接近6分钟；
- 最终完成58条结果；
- 两个搜索服务均自动消失；
- 没有幽灵前台通知、Fatal或ANR。

该耗时是“保留国外源、不因K30S国内环境收敛源”的明确成本，不属于服务泄漏。

## 九、自动化门禁

```text
搜索质量审计：12/12 PASS
源契约：357 rules / 147 green / 51 pools / hard=0
源枚举：ALL VALID
TypeScript：PASS
App对抗：54/54 PASS
流畅性：17/17 PASS
资源Feed：PASS
媒体缓存：PASS
媒体安全：PASS
双端真实媒体网络：PASS
更新下载策略：PASS
Release Build契约：0.2.5 / code9 / 147 / 51 PASS
Android signed Release：BUILD SUCCESSFUL
APK签名、版本、ABI、体积、SHA：PASS
```

## 十、设备最终状态

```text
正式包：com.magnetgoogo.app 0.2.5 / code9
Wi-Fi：开启
动画比例：1 / 1 / 1
搜索Headless/KeepAlive服务：无残留
Fatal：0
ANR：0
```

## 十一、发布边界

本轮只完成正式签名APK、K30S覆盖安装与充分验收：

- 未上传GitHub Release；
- 未上传R2、阿里云或蓝奏云；
- 未修改官网；
- 未修改线上更新配置；
- 未把最低强制升级版本从0.1.10提高；
- 未发布新的搜索源包或媒体revision。
