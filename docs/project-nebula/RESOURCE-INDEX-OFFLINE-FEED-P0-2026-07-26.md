# 影视离线Feed P0数据质量修复与一键运行证据

日期：2026-07-26（UTC+8）

## 目标

关闭《影视离线Feed数据质量问题-交接爬虫AI.md》中的P0-1至P0-4，并保证整条生产链可以在Windows本地电脑上一键运行，运行时不调用LLM、不需要人工逐条判断。

## 一键入口

```bat
deploy\resource-index\run-media-offline.bat
```

首次运行自动创建Python虚拟环境并安装锁定依赖，随后顺序完成四来源抓取或恢复、严格聚合、质量门禁、资源隔离、本地封面Bundle和离线审计。

真实一键执行结果：

- SixV电影选择`D:\lpproduct\magnet\data\resource_index\sixv_latest_50.db`，100/100，当前执行0 HTTP；
- DYTT选择`dytt8899_latest_25.db`，50/50，当前执行0 HTTP；
- SixV电视剧选择`sixv-series_latest_50.db`，50/50，当前执行0 HTTP；
- 美剧迷选择`meijumi_latest_50.db`，100/100，当前执行0 HTTP；
- 电影Bundle 100条、352个App支持资源、100张本地封面，重建0 HTTP；
- 电视剧Bundle 100条、1331个资源、100张本地封面，重建0 HTTP；
- 命令最终输出：`Offline media data is ready. No LLM was used in the runtime path.`

## P0-1 本地封面

新增内容寻址封面打包器：

- 多候选URL回退；
- 图片解码、尺寸和内容哈希校验；
- JPEG压缩与最长边控制；
- `cover_asset_path/width/height/content_hash/byte_size`；
- manifest断点复用；
- 只有全部封面完成才替换最终Feed。

离线审计：

| Bundle | 条目 | 封面 | 总字节 | 状态 |
|---|---:|---:|---:|---|
| movie | 100 | 100 | 4,139,597 | PASS |
| series | 100 | 100 | 5,064,591 | PASS |

App预构建实测复制100部电影、100部电视剧和200张已校验封面，正常路径不依赖资源站图片域名。

## P0-2 资源集数标题

资源身份按固定优先级提取：

```text
源标题 → 磁力dn → 下载文件名 → 清晰度标签
```

支持：

- `S01E01`
- `S01E01-E02`
- `1x03`
- `第1-2集`
- `E01`

输出结构化字段：

```text
season_number
episode_start
episode_end
episode_label
title_source
```

`E00/S00`、反向区间等无效身份会被判为未知，不再进入客户端协议。

## P0-3 跨季隔离

聚合器按规范剧名和季号分桶：

- 明确季资源且季号一致：进入正式条目；
- 季号不一致：`season_mismatch`；
- 条目季明确但资源无法证明季号：`season_unknown`；
- 无季页面若资源能识别多个季：拆分为多个季条目。

本次真实数据：

```text
season_mismatch = 1469
season_unknown = 686
quarantined_resource_count = 2155
dropped_zero_resource_count = 21
```

隔离后仍有电影146条、电视剧109条可用，严格输出电影100＋电视剧100。

`X战警97`反例已固定：条目按快照纠正为第二季，正式资源只保留S02，S01和未知季进入隔离。

## P0-4 类型和国家字段

所有来源在最终导出前统一执行纯规则归一化：

- 去除前导冒号和HTML残片；
- 清除异常尾部；
- 合并空白与同义分类；
- `惊悚 片\"> 惊悚 → 惊悚`；
- `纪录 片 → 纪录片`；
- `: 美国 → 美国`；
- `: 中国 大陆 → 中国、大陆`。

正式质量门禁要求：

```text
脏类型/国家标签 = 0
正式跨季资源 = 0
有集数身份但标题仅剩清晰度 = 0
空资源条目 = 0
```

当前`media_quality_report.json`状态为PASS。

## App资源边界

完整审计Feed保留页面公开的所有资源类型。App协议只接受`magnet/cloud`，离线Bundle会从完整候选池过滤并自动补位：前100候选若仅有`download/player`，不会放宽客户端协议，也不会导致App少于100条。

## 数据库选择修复

一键实测时发现：文件名为100的新partial DB可能抢占已完整的历史扩容库。现新增只读选择器，按以下证据排序：

1. 目标任务是否`success`且成功rank覆盖目标数量；
2. 成功rank覆盖；
3. 已持久化来源内容数；
4. SQLite `quick_check`；
5. 仅证据完全相同时按候选顺序。

任何候选存在活跃锁则整体停止。永久测试覆盖：完整legacy胜过partial exact、证据平局exact优先、损坏库回退、活跃锁阻断及CLI path-only输出。

真实反例中，误建exact库为58/100，历史扩容库为100/100；选择器正确选择完整库。partial DB被删除，正式SixV Feed由完整库0网络恢复为100条。

## 烂番茄与Bangumi评分占位

schema升级到0008，新增：

```text
rotten_tomatoes_rating
rotten_tomatoes_rating_text
rotten_tomatoes_url
bangumi_rating
bangumi_rating_text
bangumi_subject_id
bangumi_url
```

约束：

- 烂番茄：0—100百分制；
- Bangumi：0—10分制；
- 当前电影100＋电视剧100的7个字段均存在，非空数均为0；
- 独立评分工具回写后，爬虫的空值详情更新通过`COALESCE`保留已有评分；
- App仅在评分非空且有效时显示，烂番茄显示百分比，Bangumi显示10分制。

## 验证

- Resource Index：178 passed；
- 全部magnet非集成：241 passed，2 deselected；
- 一键数据库选择专项：40 passed；
- App资源Feed测试：PASS；
- App对抗测试：36/36；
- TypeScript：PASS；
- Expo Android prebuild：PASS；
- PowerShell：8/8解析通过；
- 四正式数据库doctor：4/4 PASS，integrity=ok，schema=0008；
- `compileall`：PASS；
- `validate_enum.py`：241/241 ALL VALID。

## 未完成边界

- P1日剧稳定来源未接入；
- 没有可审计依据前不生成“排行榜”；
- 本轮未发布、未部署、未打Tag；
- SQLite仍为单机单写。
