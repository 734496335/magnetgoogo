# 搜索资源大小跨源充分审计与关联字段修复

日期：2026-08-01（UTC+8）
工作树：`D:\lpproduct\m023`
起始基线：`03bb4ddc3555ad99d37fff6400711f4899c17b43`
范围：全部148个运行时绿色搜索源、通用详情解析、专用API handler、前台/后台/legacy合并、日期与文件数量；不修改线上源包、不发布正式APK。

## 一、审计方法

本轮没有只围绕“消失的人”单点复测，而是组合以下证据：

1. 静态枚举所有148个运行时绿色源及16类handler；
2. 审计所有数值型大小字段的单位和格式化路径；
3. K30S使用`benchmark=1&cold=1`逐主机穷尽执行；
4. 以相同info-hash跨源对比大小，筛查4倍以上冲突；
5. 检查非法大小、极端TB值、Hash/标题粘连、日期格式和文件数量；
6. 对异常源读取真实搜索页、详情页或原始JSON API；
7. 修复后对中文影视、软件ISO、代码型资源和英文影视再次执行148源穷尽复验。

前后共检查约3,768条逐源结果观测，后置四轮真机共执行592个源主机任务。

## 二、新发现的真实问题

### 2.1 通用详情页覆盖了正确列表大小

`16mag.net`和`0cili.nl`搜索列表本身返回正确大小：

```text
流浪地球 4K             4.35 GB
流浪地球2 1080P          3.91 GB
流浪地球2 2160P          4.32 GB
```

但旧逻辑进入详情页取磁力后，会用详情页的错误回退结果覆盖列表值。

### 2.2 DOM文本无分隔粘连成巨大容量

旧代码直接使用：

```ts
$('body').text()
```

HTML相邻节点没有空格，产生以下错误：

```text
推荐热度 2780 + 1.01 GB  -> 27801.01 GB
文件名末尾 4 + 4.35 GB  -> 44.35 GB
其他标题数字 + 761 MB   -> 10872.03 GB
```

真实前置反例：

```text
hash bd55ff89...：多数源3.91GB，16mag=27801.01GB
hash 3f89b5eb...：多数源4.35GB，16mag=44.35GB
Ubuntu 12.04 hash：多数源761MB，16mag=10872.03GB
```

### 2.3 Hash片段被识别为字节大小

`0cili.nl`的详情大小selector为宽泛的`dd`。旧代码固定取第一个`dd`，第一个元素实际是Hash。

正则在Hash内部把以下片段识别成大小：

```text
...a7b5308 -> 7 B
...b5...89... -> 89 B
```

真实前置反例：

```text
3.91GB -> 7B
4.35GB -> 89B
1.98GB -> 5B
2.53GB -> 98B
```

### 2.4 “同Hash取最大值”会放大巨大误解析

上一轮为解决`24.7MB -> 23.5GB`增加了“同Hash保留最大值”。该规则能处理单位缩小，但面对`27801GB`等错误巨大值会反向保留异常值。

因此最大值不是可靠权威，必须使用独立来源共识。

### 2.5 日期字段原样透传，多个源发生串位

旧`cleanDate()`无法识别时直接返回原文本，导致：

```text
APIBay Unix时间戳字符串：1339547627
Knaben大小串入日期：1.85 GB
PirateBay计数串入日期：148
PirateBay相对时间：4 days, 21 hours
Rutor俄文日期：26 Июн 26
1377x短年份：May. 19th '15
```

修复前`Inception`逐源报告中有158条非法日期。

### 2.6 文件数量被丢弃或被错误猜测

- CiliMo API有`file_count`，旧App未映射；
- CLKD API有`fileList`，旧App未计算数组长度；
- Lulutang、BTSOW和通用JSON字段未统一映射；
- `searchRunner`又会丢掉handler已解析的`fileCount`；
- UI曾把任意1—4位纯数字日期猜成文件数量，因此错误日期`148`会伪装成“文件数148”。

### 2.7 legacy dedup重复记录会虚增来源数

同一个源重复返回同一Hash时，旧`deduplicateResults()`先无条件`sourceCount++`，即使来源名称已存在，也会虚增多源可信度。

## 三、修复方案

### 3.1 详情字段绑定优先级

详情页大小改为：

```text
搜索列表绑定大小
→ selector中第一个真正可解析的大小
→ 带Size/大小标签的值
→ 保留DOM节点分隔后的第一个有效值
```

不再用整页最大值覆盖列表绑定值。

### 3.2 大小边界防护

统一大小解析新增左右ASCII字母数字边界检查，拒绝：

```text
Hash内部的7B/89B
文件名与大小粘连形成的44.32GB
其他普通文本内部的伪单位片段
```

仍支持：

```text
B/KB/MB/GB/TB
KiB/MiB/GiB/TiB
简繁中文单位
有空格/无空格
小数/千分位
```

### 3.3 同Hash来源共识

前台增量、后台快照和legacy dedup统一保留“每个来源一条大小观测”，按15%范围聚类：

- 票数最多的独立来源簇胜出；
- `24.7MB vs 23.5GB`这类约1024倍单位丢失，在一对一时选择正确大值；
- `27801GB vs 3.91GB`这类DOM粘连巨值，在一对一时拒绝巨型异常；
- `44.35GB vs 4.35GB`这类同单位数字前缀粘连，选择未粘连值；
- 同一来源重复结果只更新该来源观测，不增加票数。

### 3.4 专用API数值字段统一

以下handler统一使用二进制字节格式化：

```text
BTSOW item.size
CiliMo item.length
CLKD item.torrentSize
Lulutang item.size（数字或数字字符串）
```

SSBC继续使用已确认的KiB专用换算，不能套用通用bytes规则。

### 3.5 日期权威

新增`resourceDate.ts`，只输出可靠的`YYYY-MM-DD`：

- 10/13位Unix时间戳；
- ISO、中英文日期；
- 英文短年份和序数后缀；
- 俄文月份；
- Today/Yesterday；
- 秒、分钟、小时、天、周、月、年相对时间。

大小、计数、时间点、未知文本等无法确认值直接隐藏，不再原样透传。

### 3.6 文件数量权威

文件数量只来自明确证据：

```text
JSON file_count/fileCount/files
CLKD fileList数组长度
详情页Files/文件标签
```

`searchRunner`和Debug报告保留该字段；UI取消“从纯数字日期猜文件数”。

## 四、K30S跨源结果

### 4.1 流浪地球

修复前：

```text
148/148源完成，445条逐源结果
4倍以上同Hash冲突：3组
典型错误：27801.01GB、44.35GB、7B、89B
```

修复后：

```text
148/148源完成，44个源有结果，425条逐源结果
非法大小：0
4倍以上同Hash冲突：0
16mag/0cili目标Hash统一为4.35GB、3.91GB、4.32GB
```

### 4.2 Ubuntu

修复前：

```text
148/148源完成，638条逐源结果
4倍以上同Hash冲突：5组
典型错误：5B、98B、241367B、10GB、43.32GB、10872.03GB
```

修复后：

```text
148/148源完成，53个源有结果，639条逐源结果
非法大小：0
4倍以上同Hash冲突：0
目标ISO统一为1.79GB、1.98GB、2.53GB、761MB、2.29GB
```

`cache.foxs.top`原来的10GB也恢复为2.29GB，证明修复覆盖的不只是16mag和0cili，而是通用详情回退链。

### 4.3 SSIS-001

```text
148/148源完成
41个源有结果
466条逐源结果
非法大小：0
4倍以上同Hash冲突：0
极端TB/字节异常：0
```

### 4.4 Inception日期与文件数量

修复前：

```text
148/148源完成，554条逐源结果
非法日期：158
```

修复后：

```text
148/148源完成，51个源有结果，601条逐源结果
有日期：277
非法日期：0
有文件数量：70
异常文件数量：0
Fatal：0
ANR：0
```

样例：

```text
1339547627        -> 2012-06-13
26 Июн 26         -> 2026-06-26
4 days, 21 hours  -> 2026-07-27（按运行时近似）
May. 19th '15     -> 2015-05-19
1.85 GB/148       -> 不再显示为日期
```

## 五、自动化验证

```text
npx tsc --noEmit                              PASS
node scripts/app-adversarial-tests.mjs        54/54 PASS
node scripts/fluency-extreme-tests.mjs        17/17 PASS
npm run test:resource-feed                    PASS
npm run test:media-cache                      PASS
npm run test:media-security                   PASS
npm run test:media-network                    PASS
npm run test:update-download                  PASS
npm run test:release-build                    PASS
python magnet/validate_enum.py                357 rules / ALL VALID
npm run android:k30s                          BUILD SUCCESSFUL / install Success
```

两次新增测试首次运行失败均已记录，均由新增契约暴露并修正：

```text
docs/project-nebula/_failures/20260801-1830-cross-source-size-regression-first-run.log
docs/project-nebula/_failures/20260801-1848-resource-date-relative-collision.log
```

## 六、裁决

```text
CROSS_SOURCE_SIZE_AUDIT=PASS
DATE_AND_FILECOUNT_AUDIT=PASS
K30S_148_HOST_EXHAUSTIVE=PASS
FORMAL_RELEASE=NOT_DONE
```

目前未再发现可复现的同类严重大小错误。已发现并关闭的相关问题包括：SSBC单位错误、通用详情DOM粘连、Hash片段误识别、最大值合并放大异常、日期字段串位、文件数量丢失/误猜、重复源虚增来源数。

## 七、发布边界

- 当前公网正式v0.2.3 APK没有改变，也未重新发布；
- 线上源包、源健康状态、池策略和影视Feed未修改；
- 本轮修复仅存在于下一版本代码和K30S Debug包；
- 普通用户必须安装后续正式App版本才会获得这些修复。
