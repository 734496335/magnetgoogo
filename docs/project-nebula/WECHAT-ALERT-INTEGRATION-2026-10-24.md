# 阿里云与 Oracle 微信告警：已部署与验收记录

日期：2026-10-24（Asia/Shanghai）。修正后实机检查21:30:51 / 21:31:06 CST；最后自然定时周期复核21:35:59 / 21:36:05 CST。
状态：**WECHAT_ALERTING_LIVE / PROVIDER_DELIVERY_CONFIRMED / PUBLISHER_FAULT_STILL_OPEN**。
用户授权：免费接入个人微信，提供本人 XTUIS Token，允许配置服务器和发送接入测试。
本报告取代当天19:46/20:06的待实施结论；此前只读证据仍保留在同一报告目录。

## 1. 已完成的结果

- 使用用户提供的 XTUIS 免费个人微信通道，两台服务器均已配置并取得实际发送成功回执。
- 阿里云3个、Oracle4个新增定时器已启用并运行：发送队列、影视健康检查、主机/应用巡检；Oracle另有低价通知转发。
- 当前 compute/finalizer 的独立健康检查已上线，不再依赖停用的旧 daily/retry 调度。它同时检查任务、定时器、完成时间和有效状态证据。
- Travel 的真实 Notifier.send_message 入口已接入微信队列。原有低价门槛、同一行程去重、每轮合并提醒和标记已提醒的逻辑保留；没有扫描历史价格数据库来生成通知。
- 已发送6条消息并分别得到平台成功回执：2条初始主机通道测试、1条真实影视发布故障、1条低价应用接入测试、2条故障/恢复演练。平台回执不等于用户已读。
- 两台主机当前队列已无待发送消息，Travel spool无积压或拒收文件。当前已确认的真实影视发布故障仍未修复，其微信通知已验证成功。

## 2. 覆盖范围

| 范围 | 当前检查内容 | 通知方式 |
| --- | --- | --- |
| Oracle低价机会 | 现有规则真正满足条件的新低价；原有批量摘要 | 容器写私有spool，宿主按event_id入队，30分钟过期 |
| Oracle低价健康 | 容器健康、调度器运行、last_error、watchdog/healthcheck/backup任务与定时器 | 60秒巡检，连续异常去抖 |
| Oracle影视计算/爬虫 | compute服务失败、运行超时、调度停止、完成证据缺失或超过30小时 | 独立media-health检查，每60秒 |
| 影视来源健康 | 当前compute报告的必需源、freshness group最低数量及冗余；当前证据为4/4 | 新鲜度、冗余、证据未知分别记录 |
| 阿里云影视发布 | finalizer结果、运行超时、定时器、完成证据及时效 | 已捕获真实PUBLISH_CONFIG_ERROR并发送 |
| 阿里云源包 | 同步失败、剩余有效期不足24小时、有效期无法判断 | 原有任务钩子接入新发送器；未知不清除旧故障 |
| 两台主机基础设施 | 服务、定时任务、Docker、磁盘、MemAvailable、15分钟CPU平均负载、互相TCP可达 | 每60秒检查，2/3次连续异常触发 |
| 其他已发现应用 | nginx、管理后台、analytics、Coastime API/采集/发布/区域发布/维护/备份、Postgres、searxng、看海、访问隧道 | 纳入实际主机配置 |
| 公网与证书 | 国内站HTTP、HTTPS证书剩余有效期、证书续期任务 | HTTPS剩余不足14天或持续不可用报警 |
| 通知进程 | 发送worker、media-health、Travel relay任务和定时器的运行/逾期 | 由ops-health检查 |

修正后，阿里云38项和Oracle27项通用检查均无失败。影视专门检查另有2项/5项；其中阿里云发布失败为真实业务异常，不能用通用巡检通过覆盖该事实。
该范围不等于所有电影链接均可播放，也未新增对全部App搜索源的逐条实时质量探测。来源评级没有自动修改。

## 3. 免费额度与提醒策略

[XTUIS官方](https://xtuis.cn/)当前基础额度为300次/天、30次/分钟。本次没有购买、订阅、捐助或开通付费功能。

| 项目 | 配置 |
| --- | --- |
| 阿里云发送预算 | 每日最多50次POST尝试 |
| Oracle发送预算 | 每日最多150次POST尝试 |
| 两机合计 | 200次/天，给免费上限留出余量；重试也计入预算 |
| 每台发送速度 | 最多10次/滚动分钟 |
| 每台回执查询 | 最多4次/滚动分钟 |
| 日切换 | Asia/Shanghai自然日 |
| 低价有效期 | 30分钟；失效机会不补发 |
| 普通故障消息有效期 | 24小时 |
| 新监控持续故障重复 | 6小时；恢复一次，正常检查静默 |
| 既有源包钩子 | 保留12/24小时重复策略和连续2次触发条件 |

发送worker每30秒执行；低价relay每30秒执行；主机及影视巡检每60秒执行。服务故障轮询及去抖通常需要约1—3分钟；已有业务任务仅在自己运行或出现状态变化后提供业务证据，不承诺毫秒级通知。

阿里云原有CloudMonitor尝试通过mirror保留；新增通用ops告警只走XTUIS。Travel旧通知路径与微信入队独立尝试。QQ邮箱微信备用没有配置；也没有把未验证的云平台出站送达当成微信成功。

## 4. 已修复的通知语义

- SQLite持久化队列区分pending、accepted（有msg_id）、confirmed和failed。只有明确成功回执才记confirmed。
- 同一检查项的故障和恢复有顺序；旧故障未完成处理时，恢复不会抢先发送。
- 网络不确定最多4次POST尝试，遵守Retry-After；已经有msg_id时只查回执，不重新POST。
- 平台不提供请求幂等承诺，因此丢失POST响应时仍可能出现少量重复；没有宣称exactly-once。
- 业务状态文件加锁并原子写入。dry-run不写状态/锁/队列，也不发送网络请求。
- HTTP200但缺少有效CloudMonitor响应code不再视作成功。
- 源包同步失败仍会独立检查临期；unknown、NaN、Infinity等值不能证明恢复。
- 正在运行的任务保留待完成状态；缺失、过期或对应旧运行的JSON不能清除事故。
- 通用巡检按每个任务的取样时间读取uptime，并处理/proc与systemd精度差；修复了任务在巡检过程中结束可能被误报“完成时间异常”的问题。修复前观察到该边界，未产生相应微信误报。
- Travel镜像COPY显式0644，避免私有暂存目录的0600权限进入以UID1001运行的容器。问题在生产更新前的独立镜像检查中被发现和修复。

## 5. 实际送达证据

| 消息 | 平台msg_id | 结果 |
| --- | --- | --- |
| 阿里云通道测试 | wx_20261024203413_2c61cccca1c0a553 | success |
| Oracle通道测试 | wx_20261024203952_e9a0c8b6d7d219a2 | success |
| 真实影视发布异常 | wx_20261024212039_22beeb9d01f3717c | confirmed |
| 故障演练 | wx_20261024212425_68a12a42103ed2bb | confirmed |
| 恢复演练 | wx_20261024212500_021a18bd3e5c2ca2 | confirmed |
| 低价应用接入测试 | wx_20261024212425_a1a5b11ac098e32b | confirmed |

演练使用独立key/state：第一次故障低于阈值不发送，第二次发送一次，第三次抑制，再恢复一次；没有停掉真实业务。低价测试明确标注测试，不冒充真实报价。实际4条队列消息均一次POST得到成功回执。

## 6. 当前业务故障与边界

**BL-094仍OPEN：影视发布失败。**

- 错误代码PUBLISH_CONFIG_ERROR；manifest.json为2,472,375 bytes，超过Worker bridge的2,097,152 bytes门禁。
- 今日只读核查的最后成功发布状态为revision67，状态文件mtime为10-17 05:14:52 CST；当时Oracle读R2、Aliyun读CN两个成功读面的指针一致。
- 本轮最终media-health仍确认finalizer失败，且对应微信告警已成功。
- 未修改发布体积限制、传输逻辑，未强制启动爬虫或发布任务。该故障不能记录为已修复。
- 之前短暂观察到Coastime区域发布exit1，21:19检查已看到后续成功完成；没有把该历史失败继续当成当前故障。

互相TCP探测可以在一台服务器仍能发送时发现另一台不可达；两台同时掉线、或唯一微信供应商整体不可用时，不能借同一通道保证发出通知。正常的免费服务额度和可用性也可能随供应商规则变化。

## 7. 代码、部署与回退

- 代码分支：codex/wechat-alerts-20261024。
- 核心提交：273af55；最后部署修正：f28c6c2c0e17bf20f95b0574342d35077cd77b4f。
- 基线为实际部署worktree的7fbfb2b32e40019cb1b65a28faca4e31722ff205，不把根checkout旧文件当线上版本。
- 通知/媒体脚本位于/opt/magnet-alerts；通用巡检位于/opt/magnet-ops-health。
- 私有配置：/etc/magnet-alerts/alert.env，root:root、0600。Token没有进入源码、Git、报告、普通日志或Travel容器。
- 两台原配置和代码：/var/backups/magnet-wechat/20261024-preinstall。
- Travel原配置/源码：/var/backups/magnet-wechat/20261024-travel；旧镜像tag为oracle-travel:before-wechat-20261024。
- Travel新镜像：sha256:356e3a5d466b235e6f7bd0af14e44cf40b30d69777910422308ca1d895d7a1cb。
- Travel基于正在运行的原镜像增加通知层，没有重新下载依赖。确认扫描空闲后只重建该容器；更新前后scheduler_running=true、last_error=null，最终Docker healthy。
- 本地Travel源码及compose同步更新于D:/lpproduct/travel；Git分支内deploy/alerts/travel保存相应部署快照。
- 回退先停止新增timer，再恢复对应备份；Travel恢复旧镜像及compose后重建单一服务。不要把历史价格spool重造为新事件。

没有push主分支，也没有覆盖根checkout并行源审计改动。实现说明见同分支deploy/alerts/WECHAT.md。

## 8. 验证与证据位置

- 告警完整专项：89 passed、6 skipped（Windows平台不具备相应POSIX条件）。
- 时钟边界修正后定向回归：19 passed，含3个新增时钟用例；未把重复运行算成新的独立测试。
- Oracle Linux源包行为：5 passed；FIFO非阻塞拒收另在真实Linux运行通过。
- Travel原通知、新spool、引擎去重/门槛测试：23 passed。旧引擎夹具的旅行日期止于10-20；仅测试进程把engine时钟固定为10-01。生产engine未修改，未将夹具过期造成的失败伪装成业务变更修复。
- 两台实际Python运行时编译、systemd单元验证、现场dry-run、自然定时运行、私有文件权限及部署SHA核对完成。
- 源证据：reports/wechat-alerts-20261024/read-only-evidence.json。
- 初始通道回执：reports/wechat-alerts-20261024/initial-channel-tests.json。
- 部署与验证：reports/wechat-alerts-20261024/deployment-verification.json；最终自然周期检查另见final-runtime.json。
- 可复现代码包：reports/wechat-alerts-20261024/wechat-alerts.tar.gz。

以上结果证明配置、定时执行、业务入口接线和供应商投递回执。手机是否显示、是否打开消息仍以用户端实际显示为准。
