# v0.2.4 四评分客户端消费与兼容性测试结果

- 日期：2026-08-01
- 分支：`release/v0.2.4-four-ratings`
- 版本：`0.2.4` / Android `versionCode=8`
- 结论：`PASS_WITH_SUPPLY_BOUNDARY`
- 发布状态：仅完成候选开发与验证，未发布，公网正式 v0.2.3 未修改。

## 1. 本轮目标

补齐媒体 release 中 IMDb、豆瓣、烂番茄、Bangumi 四种评分的客户端消费链，覆盖协议解析、catalog 映射、detail 水合、本地缓存、列表与详情展示、排序/推荐/高分口径以及旧 revision/空字段兼容。

## 2. 实现结果

### 2.1 协议与模型

- `mediaReleaseProtocol.ts`
  - catalog 新增 `rotten_tomatoes_rating`、`bangumi_rating`；
  - detail 新增两种评分的数值、文本、URL，以及 `bangumi_subject_id`；
  - 所有新增字段均为可空字段，旧 revision 缺失时解析为 `null`。
- `resourceFeedProtocol.ts`
  - `MovieFeedItem` 完整保留 IMDb、豆瓣、烂番茄、Bangumi 的数值与详情元数据；
  - 无字段、`null`、0分和越界分值均不会生成错误展示。
- `mediaReleaseMapping.ts`
  - catalog 卡片映射到列表对象时保留四评分；
  - detail 水合时采用 detail 优先、catalog 回退，缺失字段不会覆盖已有评分；
  - 纯映射模块不依赖 Expo 原生模块，可执行单元测试。
- `mediaReleaseCache.ts` 现有对象缓存保存完整 `MovieFeedItem`，经解析与断网冷启动验证四评分模型不会被裁剪。

### 2.2 展示设计

列表：
- 顺序固定为：豆瓣 → IMDb → 烂番茄 → Bangumi；
- 烂番茄显示百分数，例如 `52%`；其余显示一位小数；
- 评分和清晰度标签分行，避免四评分挤占质量标签；
- 缺失评分不显示空占位。

详情：
- 使用两列评分卡；四评分齐全时为 2×2；
- 三项评分时第三项自然占下一行；
- 评分来源与数值分层展示，质量标签在评分区之后独立显示。

### 2.3 明确业务口径

- 列表排序：只使用 release `rank`，常量 `MEDIA_LIST_SORT_POLICY='release-rank'`；不按评分重排。
- 精品推荐：只使用服务端 `recommended`，常量 `MEDIA_RECOMMENDATION_POLICY='server-recommended'`；不由客户端临时计算。
- 高分/标题强调主评分优先级：豆瓣 → IMDb → Bangumi → 烂番茄。
- 十分制精品/高分阈值：6.0 / 8.0。
- 烂番茄百分制精品/高分阈值：60% / 80%。
- 只有主评分决定高分强调；其他评分作为补充信息，不会因单个次级来源高分覆盖主评分判断。

## 3. 兼容性验证

- 旧 catalog 不含烂番茄、Bangumi：PASS，解析结果为 `null`。
- 旧 detail 不含新增字段：PASS，不覆盖 catalog 已有评分。
- 四种评分全部为空：PASS，不渲染评分区。
- 部分评分为空：PASS，只展示有效项，无空胶囊。
- 越界评分：IMDb/豆瓣/Bangumi >10、烂番茄 >100 或非正数均隐藏。
- 正式 v0.2.3 下载配置仍指向 v0.2.3，0.2.4 候选构建未误改线上更新链。

## 4. 数据证据

冻结签名 release `20260726T000000Z-b8c702d5`：
- 唯一媒体卡片：200；
- catalog 中 IMDb 153、豆瓣99、烂番茄82、Bangumi96；
- detail 中烂番茄82、Bangumi96；
- 四字段均非空的唯一条目14；按客户端有效范围四项均可展示的唯一条目5。

当前线上 revision8：
- 唯一媒体卡片444；
- 烂番茄非空62；
- Bangumi非空0；
- 四评分齐全0。

因此 0.2.4 客户端已具备 Bangumi 消费能力，但当前线上 revision8 尚无 Bangumi 数据，不能把“客户端支持”表述为“线上已有 Bangumi 展示”。后续评分工具写回并发布新 revision 后，无需再次修改客户端。

## 5. 自动化测试

- TypeScript：PASS。
- `test:resource-feed`：PASS，含四评分顺序、量纲、主评分、排序、推荐、空值与旧 revision。
- `test:media-cache`：PASS，四评分字段进入缓存模型并兼容旧对象。
- `test:media-security`：PASS，协议、映射、旧字段回退、签名与回滚门禁均通过。
- `test:media-network`：PASS，冻结签名 release 与线上双端完整对象链通过。
- App 对抗测试：54/54 PASS。
- 流畅性测试：17/17 PASS。
- 更新下载策略：PASS，仍绑定正式 v0.2.3。
- 0.2.4 发布构建契约：PASS，versionCode 8。
- 源枚举：357 / ALL VALID。
- Android arm64 Debug：BUILD SUCCESSFUL，K30S 安装成功。

## 6. K30S 真机验证

设备安装身份：
- package：`com.magnetgoogo.app.debug`
- versionName：`0.2.4`
- versionCode：`8`

在线列表：
- “超级少女”实际显示豆瓣5.4、IMDb6.1、烂番茄52%；
- “恶魔之口”仅有烂番茄33%，其他空评分不产生占位；
- 质量标签与评分分行；
- “超级少女”主评分豆瓣仅5.4但仍位于精品推荐，证明推荐来自服务端 `recommended`，不是评分计算。

在线详情：
- 豆瓣、IMDb 第一行两列，烂番茄第二行；
- detail 水合后评分、简介和资源数量均保留；
- UI 无遮挡或异常换行。

离线缓存：
- 先在线完成详情水合；
- 临时关闭 Wi-Fi 与移动数据并强制停止 App；
- 通过详情深链冷启动；
- 豆瓣5.4、IMDb6.1、烂番茄52%、简介和资源数全部从本地缓存恢复；
- 测试后 Wi-Fi、移动数据和三个系统动画比例均恢复，动画比例确认均为1。

稳定性：
- Fatal：0
- ANR：0

## 7. 已记录的测试过程失败

以下均为测试工具/命令问题，已记录在 `docs/project-nebula/_failures/`，没有降低门禁：
- 误用不存在的 `npm run test:app`，改用实际对抗测试脚本；
- Node 直接导入含 Expo 原生依赖的 client 失败，推动纯映射模块拆分；
- Python 默认 User-Agent 读取媒体端被403，改用正式协议测试 User-Agent；
- Windows `findstr` 编码与 Git Bash `/sdcard` 路径转换干扰 ADB 取证，改为设备端命令；
- MIUI `uiautomator` 输出缺失主题配置栈，但仍成功生成 UI hierarchy，不影响取证。

## 8. 最终判断

`IMPLEMENTATION=PASS`

`PROTOCOL_MAPPING_CACHE=PASS`

`FOUR_RATING_UI_CONTRACT=PASS`

`LEGACY_REVISION_COMPATIBILITY=PASS`

`K30S_ONLINE_OFFLINE=PASS`

`SUPPLY_BOUNDARY=LIVE_REVISION_8_HAS_RT_BUT_NO_BANGUMI`

`PUBLICATION=NOT_PERFORMED`
