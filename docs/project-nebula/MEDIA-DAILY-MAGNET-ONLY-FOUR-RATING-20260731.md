# 影视每日流水线仅磁力与四评分持久化开发记录

日期：2026-07-31（UTC+8）
分支：`feature/media-daily-automation`

## 一、结论

本批次已完成并通过充分测试：

```text
MAGNET_ONLY_IN_DAILY_PIPELINE=PASS
FOUR_RATING_PERSISTENCE=PASS
RATING_FAILURE_NON_BLOCKING=PASS
V0.2.3_FORWARD_COMPATIBILITY=PASS
PRODUCTION_TIMER=NOT_ENABLED
PRODUCTION_REVISION=UNCHANGED_AT_7
```

每日流水线现在按以下顺序运行：

```text
四源抓取/恢复
→ 跨源聚合
→ 仅磁力裁剪
→ 恢复历史评分状态
→ 豆瓣/IMDb/烂番茄/Bangumi补全
→ 原子持久化评分状态
→ 封面Bundle
→ 内容指纹
→ 签名候选/双端发布
```

## 二、实现内容

### 1. 仅磁力正式接入每日流水线

`media_daily.py`不再直接把聚合Feed交给Bundle，而是先调用`build_magnet_only_media_feeds`：

- 删除所有非磁力资源；
- 删除裁剪后没有磁力的影视项；
- 校验40位BTIH、URL和声明info-hash一致；
- 电影与剧集全局拒绝重复info-hash；
- 后续评分、封面、签名和发布全部只处理磁力目录。

因此自动运行不会重新把网盘资源带回新revision。

### 2. 新增跨运行评分状态层

新增：

```text
magnet/resource_index/pipeline/media_rating_state.py
```

正式状态文件：

```text
<state_root>/ratings/media-ratings.json
schema_version=media-rating-state/1
```

状态以稳定`movie_id`为主键，保存：

- IMDb：ID、评分、文本；
- 豆瓣：评分、文本、链接；
- 烂番茄：评分、文本、链接；
- Bangumi：评分、文本、subject ID、链接。

规则：

- 新一轮聚合先用持久状态填补缺失字段；
- 新评分只覆盖缺失值，不因失败清空旧值；
- 评分状态采用临时文件后原子替换；
- `0`、负数、超量程、NaN、Infinity不保存；
- 已知错误`the_odyssey_2026`烂番茄匹配不保存；
- IMDb ID等安全身份字段可在暂时没有分数时独立保存；
- 同一个`movie_id`出现电影/剧集类型冲突时硬停。

### 3. 四评分失败不阻止影视发布

每日流水线明确启用：

```text
douban
imdb
rotten_tomatoes
bangumi
```

评分提供方异常时：

- 状态写为`warning`；
- 保留已经恢复的历史评分；
- 继续生成影视候选；
- 不影响标题、封面和磁力资源发布。

但评分状态文件损坏、类型冲突或原子写入失败仍会硬停，因为这属于持久化完整性故障，不应被伪装成普通评分源失败。

### 4. 发布对象完整保留四评分

Release Builder专项测试直接读取生成的Catalog和Detail对象，确认以下字段都进入签名revision：

```text
imdb_rating
douban_rating
rotten_tomatoes_rating
bangumi_rating
```

详情对象同时保留评分文本、URL、IMDb ID和Bangumi subject ID。

### 5. 0.2.3兼容性

正式0.2.3的`mediaReleaseProtocol.ts`与本分支测试文件字节一致。

包含四评分的Catalog和Detail输入在0.2.3中：

- 豆瓣、IMDb正常解析；
- 烂番茄、Bangumi作为未来字段安全忽略；
- 不报协议错误；
- 不影响资源和缓存加载。

客户端缓存边界：

- Catalog缓存保存原始内容寻址字节，四评分不会丢；
- 0.2.3 Detail缓存保存解析后的`MovieFeedItem`，已打开过的详情可能不含未来两种评分；
- 0.2.4必须升级Detail缓存schema或执行一次旧Detail缓存失效，才能保证升级后详情页立即展示烂番茄/Bangumi；
- 服务端提前保存四评分仍然完全正确，无需等待0.2.4再抓历史数据。

## 三、真实数据与网络验证

### Revision 7评分状态回放

对正式revision 7的199电影、220剧集执行持久化、删除、恢复和逐字段比对：

```text
有评分相关数据的影视：287
有效评分/身份字段：584
恢复字段：584
逐字段验证：584/584 PASS
现有有效豆瓣评分：128
现有有效IMDb评分：0
现有有效烂番茄评分：0
现有有效Bangumi评分：0
```

这说明后续自动补全四评分具有实际增量价值。

### 四评分真实网络smoke

`Inception (2010, tt1375666)`：

```text
豆瓣：9.4 / ok / subject_abstract
IMDb：8.8 / ok / cinemeta
烂番茄：86 / ok / rt_scorecard
Bangumi：no_match，因标题不匹配被门禁拒绝
```

`葬送的芙莉莲 (2023)`：

```text
Bangumi：8.3 / ok / bgm_api
```

结论：四条通道均可运行；匹配不到时保守留空，不为了填满四评分制造误匹配。

## 四、测试结果

```text
定向：34 passed
评分状态/每日流水线/Release最终定向：32 passed
Resource Index：306 passed，1 skipped
全部magnet测试最终：381 passed，1 skipped
Python compileall：PASS
枚举契约：241 / ALL VALID
App 0.2.3 Media Cache：PASS
App 0.2.3 Resource Feed：PASS
App 0.2.3 Media Security：PASS
App 0.2.3 TypeScript：PASS
四评分未来字段兼容专项：PASS
Git diff --check：PASS（仅CRLF提示）
```

测试永久覆盖：

- 四评分跨运行恢复；
- 空值更新不清空旧评分；
- 无评分时仍保留IMDb ID；
- 无效/超量程/非有限评分拒绝；
- 已知烂番茄误匹配拒绝；
- 类型碰撞硬停；
- 评分提供方整体异常仍生成候选；
- 每日流水线真实移除网盘资源；
- Release Catalog/Detail保存四评分；
- 0.2.3安全忽略未来评分字段；
- 0.2.3最低版本默认值和示例配置正确。

## 五、配置调整

Linux示例配置更新为：

```text
min_app_version=0.2.3
min_movies=190
min_series=200
sixv=100
dytt8899=250
meijumi=100
sixv-series=100
```

`load_media_daily_config`缺省最低App版本也已从`0.2.1`改为`0.2.3`。

## 六、仍未完成的下一批

本批次没有启用生产Timer，也没有发布revision 8。

下一批仍需完成：

1. 外层运行锁增加死PID/启动时间恢复；
2. runs、releases、receipts、日志和缓存保留策略；
3. 当前2C2G服务器的内存/CPU硬限制；
4. Nginx目录原子迁移，禁止空目录切换；
5. candidate-only连续运行和heartbeat；
6. 双端pointer差异告警；
7. 通过候选运行后再决定是否在当前机器正式自动提升revision。
