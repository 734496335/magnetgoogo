# Resource Index 电影/电视剧品牌体系与多源聚合闭环

日期：2026-07-26（UTC+8）

## 1. 架构裁决

采用四层模型：

1. **品牌**：SixV、DYTT8899、美剧迷、EZTV等；
2. **品牌端点**：主站、官方镜像、跳转别名、发布页、候选、导航页；
3. **正式来源适配器**：电影/电视剧列表和详情解析；
4. **跨品牌聚合**：相同内容合并资源和来源证据。

不采用一个通用CSS解析器覆盖所有站点，也不按域名名称直接判断同品牌。

品牌注册表：

```text
magnet/resource_index/config/movie_source_brands.json
```

正式运行端点只有`active/standby`且具备解析器、source_id和证据的记录。候选站不会因一次可达就自动升级。

## 2. 品牌证据

### SixV

发布页和运行探测确认：

```text
6v520.com  primary
6v520.net  official_mirror
6v520.cc   official_mirror
```

三站首页字节指纹均为`1df2d960f82c`，旧版电影/电视剧解析器兼容。

现代分支：

```text
xb6v.com / hao6v.org / 6vdy.org
```

三站指纹一致但模板不同，保持`candidate`，没有错误复用旧版解析器。

### DYTT8899

```text
dytt8899.com  primary
dy2018.com    redirect_alias -> dytt8899.com
```

别名探测实际使用2次物理请求完成跳转，最终内容指纹与主站一致。

`dytt8.org`为不同模板独立站；`dianyingtiantang.me`为导航页，均不当作DYTT8899镜像。

### 其他候选

EZTV、YTS、蜜柑、动漫花园、迅雷电影、BTBTT及用户提供的独立站进入候选池。当前环境中EZTV返回访问挑战、YTS存在TLS问题；蜜柑和动漫花园可达，但未建立正式适配器前不自动抓取。

## 3. 正式来源

| source_id | 品牌 | 内容 | 默认数量 | 最小请求间隔 | 日预算 |
|---|---|---:|---:|---:|---:|
| sixv | SixV | 电影 | 50 | 10秒 | 80 |
| dytt8899 | DYTT8899 | 电影 | 25 | 15秒 | 50 |
| sixv-series | SixV | 电视剧 | 50 | 10秒 | 70 |
| meijumi | 美剧迷 | 电视剧 | 50 | 12秒 | 70 |

全部来源使用单并发、12小时网络检查门禁、24/48/72小时失败退避和独立SQLite。

## 4. 同品牌镜像切换

共享Runner使用品牌端点优先级获取快照。端点切换后用稳定`source_item_key`识别内容，不按完整域名URL判定新内容。

永久反例：

1. 首次从`6v520.com`抓取一条并写入详情；
2. 模拟主站失败；
3. 自动切换到`6v520.net`；
4. 只产生主站失败+镜像成功两个列表请求；
5. 详情调用次数保持1；
6. 数据库详情URL和`endpoint_origin`更新为镜像域名。

## 5. 美剧迷正式50条

正式文件：

```text
D:\lpproduct\magnet\data\resource_index\meijumi_latest_50.db
D:\lpproduct\magnet\data\resource_index\meijumi_latest_50_urls.json
D:\lpproduct\magnet\data\resource_index\meijumi_latest_50_feed.json
D:\lpproduct\magnet\data\resource_index\meijumi_latest_50.log
```

结果：

- 50/50成功，0失败，0运行中；
- 1个列表请求、初始50个详情请求；
- 50条均有标题、封面、简介、类型和公开资源；
- 1740条资源：1488磁力、126迅雷云盘、73夸克、53百度；
- 详情URL、source key和单内容资源URL重复均为0；
- 季数/集数解析升级后，仅1个列表请求更新49条状态，0详情重抓；
- 最后一条仅用1次定向详情请求补齐季数；
- 最终季数和当前集数缺失均为0，资源仍为1740。

安全检查：第一次仅1个列表请求、预留12/实际1；紧接着再次执行因12小时门禁0请求跳过。

## 6. SixV电视剧正式50条

来源入口：

```text
https://www.6v520.com/gvod/dsj.html
```

列表恰好50条，详情公开路径为：

```text
/dlz/  国剧
/rj/   日韩剧
/mj/   欧美剧
```

三类详情均复用SixV已有详情解析器。

正式文件：

```text
D:\lpproduct\magnet\data\resource_index\sixv-series_latest_50.db
D:\lpproduct\magnet\data\resource_index\sixv-series_latest_50_urls.json
D:\lpproduct\magnet\data\resource_index\sixv-series_latest_50_feed.json
D:\lpproduct\magnet\data\resource_index\sixv-series_latest_50.log
```

结果：

- 50/50成功，0失败，0运行中；
- 1个列表请求、50个详情请求；
- 50条均有标题、封面、简介和资源；
- 417条资源：308磁力、37迅雷、37夸克、35百度；
- 详情URL、source key、资源URL重复均为0；
- 2条类型为空，经独立复核确认源站详情没有类别字段；
- 对只写“更新09/全集”的条目保留源站状态，不虚构季数或总集数。

完成后普通重复运行`invocation_http_requests=0`，run数和详情统计均不增加。安全检查第一次只发1个列表请求，第二次12小时内0请求跳过。

## 7. schema 0007

新增字段：

```text
content_kind
series_title
season_number
episode_number
episode_label
update_status
brand_id
endpoint_origin
```

`latest_crawl_items`新增稳定`source_item_key`。历史0006数据库升级后旧电影默认为`content_kind=movie`，电影、资源和封面均无损保留。

## 8. 跨品牌聚合

正式统一Feed：

```text
D:\lpproduct\magnet\data\resource_index\media_latest_feed.json
```

输入：SixV电影50、DYTT电影25、SixV电视剧50、美剧迷50，共原始175条。

聚合结果：

```text
正式来源：4
聚合记录：158
电影：74
电视剧：84
跨品牌合并：17组
资源：2345
```

17组包括16组电视剧和1部电影。示例：

| 内容 | 来源 | 合并资源 |
|---|---|---:|
| 犯罪心理：演变 第十九季 | SixV + 美剧迷 | 96 |
| 尝试 第五季 | SixV + 美剧迷 | 88 |
| 谜探休格 第二季 | SixV + 美剧迷 | 74 |
| 龙之家族 第三季 | SixV + 美剧迷 | 66 |
| 恐怖角 第一季 | SixV + 美剧迷 | 45 |
| 后室 | SixV + DYTT | 4 |

剧集身份使用规范剧名+当前季；IMDb仅作为辅助别名。若一边缺季数，只在同名只有一个兼容季候选时合并，避免不同季误并。

## 9. 自动化与部署

默认安全调度包括：

```text
sixv,dytt8899,sixv-series,meijumi
```

每轮完成后重建`media_latest_feed.json`。Windows任务计划默认6小时触发，内部12小时门禁，多余触发零网络；设置`IgnoreNew`防止并行实例。

## 10. 安全边界

- 低频不能承诺永不触发反爬；
- 不处理验证码、WAF、登录或隐藏接口；
- 不绕过延迟释放或未公开资源；
- 候选品牌默认不联网自动抓取；
- 一个来源失败不会阻止其他来源和已有聚合Feed；
- SQLite仍为单机单写；
- App当前尚未切换到统一电影/电视剧Feed，UI接入是后续独立产品批次。
