# 搜索资源大小单位误识别修复与K30S真机验证

日期：2026-08-01（UTC+8）
工作树：`D:\lpproduct\m023`
基线：`55d4df9e66b377f456e6c3efe273acf06ce3b35a`
范围：搜索结果大小解析、同hash合并、后台结果恢复；不发布正式APK、不修改线上源状态。

## 一、用户反例

关键词：`消失的人`

目标资源：

```text
【高清影视之家发布 www.BBEGGE.com】消失的人[60帧率版本][高码版][国语配音+中文字幕].2026.2160p.YK.WEB-DL.H.265.HDR.HFR.HQ.DTS5.1-PandaQT
info-hash=60459b611ef202e13a3492733a5ff5b8bd38a435
```

修复前K30S正式逻辑显示：

```text
24.7 MB
```

用户核对的真实大小约：

```text
23.5 GB
```

## 二、真实复现

使用K30S已安装Debug包搜索`消失的人`：

```text
搜索结果=143
berrl.com结果=5
movih.com结果=5
```

两个源属于同一SSBC平台家族并返回相同hash和相同错误大小：

```text
60459b611ef202e1 -> 24.7 MB
ceef519bd3c7f430 -> 1.7 MB
2f83a6e5f88a197c -> 2.5 MB
83969a527eb790a0 -> 3.3 MB
```

因此问题不是列表展示小数点错误，也不是某一张卡片缓存污染，而是SSBC平台处理链的系统性单位错误。

## 三、根因证据

### 3.1 SSBC字段是KiB，旧代码当成bytes

SSBC真实API对目标hash返回：

```json
{
  "infohash": "60459b611ef202e13a3492733a5ff5b8bd38a435",
  "size": "24672993",
  "createdate": "2026-08-01",
  "category": "影视"
}
```

旧实现：

```ts
const sizeBytes = parseInt(t.size, 10) || 0;
if (sizeBytes >= 1e6) size = `${(sizeBytes / 1e6).toFixed(1)} MB`;
```

即把`24672993`直接当作bytes，得到约`24.7 MB`。

实际字段是KiB计数：

```text
24672993 × 1024 bytes
= 23.5299997 GiB
≈ 23.5 GB
```

数量级正好相差1024倍，与用户反例完全一致。

### 3.2 同hash合并会冻结错误值

三条结果链此前均有缺陷：

```text
前台增量累积：只在existing.size为空时补大小
旧dedup：保留第一个非空大小
后台快照合并：后一个非空大小无条件覆盖
```

因此同一info-hash即使后续源返回正确总大小，也可能无法纠正先到达的错误小值，或被后到达的错误值再次覆盖。

### 3.3 通用容器只取第一个大小

部分HTML结果行可能同时包含：

```text
样片大小
单文件大小
种子总大小
```

旧回退正则只取第一个匹配值，容易把样片/附件大小当成torrent总大小。

## 四、修复内容

### 4.1 统一大小权威

新增：

```text
magnetgoogo-app/src/core/resourceSize.ts
```

统一支持：

- `B / KB / MB / GB / TB`；
- `KiB / MiB / GiB / TiB`；
- 中文`字节/千字节/兆字节/吉字节/太字节`及繁体对应形式；
- 有空格与无空格，例如`23.5 GB`、`23.5GB`；
- 小数与千分位；
- 一个文本中存在多个大小时选择最大的有效总大小；
- 明确不支持裸`K/G`单位，防止把`4K HDR`识别成`4 KB`。

### 4.2 修复SSBC单位

新逻辑：

```ts
const size = formatSsbcSize(t.size);
```

其契约为：

```text
SSBC size = KiB
bytes = KiB × 1024
```

### 4.3 修复同hash冲突合并

以下路径统一改为按解析后的bytes保留较大值：

- `searchResultAccumulator.ts`：前台增量搜索；
- `backgroundSearchProtocol.ts`：后台搜索快照恢复；
- `dedup.ts`：旧去重路径。

语义依据：相同info-hash代表同一个torrent，torrent总大小不会小于其中单个文件或样片大小，因此冲突时较大值更接近总大小权威。

### 4.4 改进结果行回退解析

结果容器中有多个有效大小时不再取第一个，而是选择最大的有效值，降低样片/附件大小污染。

## 五、永久回归测试

新增覆盖：

```text
24672993 KiB -> 23.5 GB
24.7MB + 23.5GB -> 23.5GB
1.5 GiB -> 1.5 GB
1024 bytes -> 1024 bytes
23.5吉字节 -> 23.5 GiB
4K HDR -> 不识别为大小
前台同hash合并 -> 23.5GB覆盖24.7MB
后台同hash合并 -> 小值不得覆盖大值
旧dedup -> 23.5GB覆盖24.7MB
SSBC handler必须调用formatSsbcSize(t.size)
```

## 六、自动化验证

```text
npx tsc --noEmit                                      PASS
node scripts/app-adversarial-tests.mjs                53/53 PASS
node scripts/fluency-extreme-tests.mjs                17/17 PASS
npm run test:resource-feed                            PASS
npm run test:media-cache                              PASS
npm run test:media-security                           PASS
npm run test:media-network                            PASS
npm run test:update-download                          PASS
npm run test:release-build                            PASS
python magnet/validate_enum.py                        ALL VALID / 357 rules
npm run android:k30s                                  BUILD SUCCESSFUL / install Success
```

扩展门禁首次发现`update-download-policy-tests.mjs`仍硬编码已退役的v0.2.2下载地址。该问题与大小修复无关，已按规则记录：

```text
docs/project-nebula/_failures/20260801-1741-v023-update-download-stale-fixture.log
```

仅将测试fixture更新为已正式发布的v0.2.3地址，生产更新逻辑未改变；重跑PASS。

## 七、K30S修复后真机证据

安装新Debug包后再次搜索`消失的人`：

```text
结果数=142
hash=60459b611ef202e1 -> 23.5 GB
hash=83969a527eb790a0 -> 3.16 GB
hash=2f83a6e5f88a197c -> 2.42 GB
```

UI明确显示：

```text
电影 · 23.5 GB · 2026-08-01
```

Debug report中`berrl.com`与`movih.com`对同一hash均记录为：

```json
{
  "hash": "60459b611ef202e1",
  "size": "23.5 GB",
  "relevance": 100
}
```

原错误`24.7 MB`在目标hash结果中已不存在。

原生日志：

```text
Fatal=0
ANR=0
```

MIUI `uiautomator dump`仍会输出设备自身缺失`theme_compatibility.xml`的已知测试工具堆栈，但UI层级正常生成，与App无关。

## 八、影响与发布边界

### 已解决

- SSBC家族所有源的1024倍单位缩小错误；
- 同hash正确大小无法覆盖错误小值；
- 后台恢复时错误小值覆盖正确大值；
- 结果行首个样片/附件大小被误当总大小的常见情况。

### 未改变

- 搜索排序策略；
- 源健康状态；
- 源数量和池策略；
- 正式v0.2.3 APK；
- 线上远程配置；
- 影视离线Feed。

### 发布要求

当前公开v0.2.3 APK仍是旧代码，无法通过远程配置修复客户端解析逻辑。本修复已在K30S Debug包验证，需随下一App正式版本打包发布后，普通用户才会获得修复。
