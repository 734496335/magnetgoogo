# 影视自动抓取与发布长期无人值守稳定性终审

时间：2026-08-05（UTC+8）

## 最终裁决

`AUDIT=PASS_WITH_EXTERNAL_ALERTING_RESIDUAL`

当前阿里云影视流水线已经具备长期无人值守运行所需的主要能力：每日定时抓取、积压追赶、单源失败降级、评分确定性、封面与资源质量门禁、双端原子发布、无变化双端复验、陈旧锁恢复、异常容器清理和一次性延迟重试。

保留风险只有一个：第一次失败30分钟后会自动重试一次，但第二次仍失败时目前只记录systemd日志和结构化状态，没有短信、邮件、企业微信或其他外部主动通知。

## 生产现状

- 当前revision：10
- release ID：`20260805T000000Z-8013b446`
- pointer SHA：`d5c0be581d8bd26fb08509a5ffa810a7996054586ec7f267fc2ef324ce187eb5`
- manifest SHA：`f57967515c709ee4018469c349539a61109b9c2cdc36cfed1c86e6fba640ba21`
- 电影：247部
- 电视剧：249部
- 影视合计：496部
- 磁力资源：3892条
- 网盘资源：0
- 最低App版本：0.2.3

R2、阿里云和服务器本地`current.json`的SHA-256完全一致。

## 本轮重新审视发现的问题

### 1. 单源故障会放大成整条流水线失败

旧逻辑中四个源串行硬依赖，任意一个源出现DNS、超时、限流或页面临时异常，整次发布立即失败，即使服务器已有该源上一轮完整数据库。

修复后：

- 仅对明确的临时错误启用回退；
- 使用最近可信SQLite数据库；
- 默认最大允许年龄168小时；
- 超过7天或本地数据库不完整时继续硬停；
- 回退源会在结构化状态中标记`status=fallback`、错误码和数据年龄；
- 其他源仍可正常抓取和发布。

生产只读故障演练：人为向SixV注入`LIVE_HTTP_ERROR`，成功回退到4.22小时前的`100/100`可信数据库，没有执行网络抓取和发布。

### 2. 无变化时没有验证公网双端状态

旧逻辑只比较本地内容指纹。内容未变化时直接返回成功，即使R2或阿里云current丢失、落后或字节不一致，也可能被错误判断为健康。

修复后：

- 无变化路径仍读取线上current；
- 同时验证R2与阿里云的pointer、release、manifest和SHA；
- 双端一致才返回`no_change=true`；
- 任一端异常会进入修复发布，而不是假成功。

现场连续重放：revision 10发布后，相同输入第二次在19秒内完成，返回：

- `status=success`
- `no_change=true`
- `public_verified=true`
- `current_revision=10`
- `published=false`

两端仍保持revision 10，没有机械增加revision。

### 3. 评分状态重放不确定

revision 9之后的第一次无网络重放发现，相同影视数量和资源会生成不同内容指纹。根因是源站携带的评分字段存在脏值，而评分状态恢复只补空值：

- `0/10 from 0 users`被当作有效评分文本；
- Family Guy页面把季数22误解析为豆瓣22分；
- X战警页面把97误解析为豆瓣97分；
- 部分评分文本包含整页资源内容。

修复后：

- 持久评分状态成为可信评分字段的权威来源；
- 非法零分、负数和越界分数无可信状态时清空为暂无评分；
- 同一生产Feed独立重放两次，电影和电视剧语义SHA逐字节一致；
- 496条影视的非法评分项为0。

该修复产生一次有明确理由的revision 10，随后第二次重放稳定为no-change。

### 4. 长中文标题导致评分缓存文件名超过系统限制

生产评分阶段出现`OSError: [Errno 36] File name too long`。旧缓存直接使用最多180个字符的标题作为文件名，但中文UTF-8每个字符通常占3字节，字符数限制不能保证字节数低于255。

修复后缓存文件名使用：

- 最大96字节可读前缀；
- 24位SHA-256摘要；
- 原子临时文件替换；
- 兼容读取旧缓存文件。

长中文标题回归测试通过。

### 5. Docker PID命名空间导致主锁无法判断旧进程死亡

锁文件记录容器内PID，Python进程通常是PID 1。旧容器被强杀后，新容器看到自己的PID 1仍存活，可能永远无法恢复旧锁。

修复后：

- 主锁每30秒刷新心跳；
- 心跳超过10分钟可恢复，即使PID看起来仍存活；
- 锁包含容器hostname和随机token；
- systemd结束后按CID/hostname只清理属于本容器的锁；
- 正常退出只删除自己token的锁。

现场演练：预置PID 1陈旧锁和同名停止容器后启动周审计，审计报告：

- `stale_lock_recovered=true`
- `stale_lock_reason=heartbeat_expired`
- candidate验证通过
- 服务退出码0
- 结束后容器、CID和主锁全部为空。

### 6. R2发布锁存在相同PID命名空间问题

被中止的发布演练留下R2发布锁，旧逻辑读取PID 1并认为发布者仍活着，后续发布返回`PUBLISH_LOCKED`。

修复后发布锁同样具备：

- 30秒心跳；
- 10分钟过期恢复；
- hostname和token；
- 仅锁拥有者可以删除。

生产现场自动回收旧锁后，revision 10发布成功；整个约18分钟的R2对象验证期间，锁mtime持续刷新，没有被误判为陈旧。

### 7. 失败后没有自动恢复

新增`magnet-media-retry.service`：

- 每日正式发布失败后由`OnFailure`启动；
- 等待30分钟；
- 若期间已有人工或其他成功运行，则自动取消重试；
- 否则只重试一次；
- 重试服务自身没有`OnFailure`，不会形成无限循环。

现场将延迟缩短为1秒验证，脚本识别到较新的revision 10成功状态，输出`media publish already recovered after the recorded failure`，没有重复启动正式发布。

### 8. 审计与正式状态互相覆盖

新增分模式状态：

- `latest-publish.json`
- `latest-candidate.json`
- `latest-audit.json`

运营状态脚本优先读取`latest-publish.json`，周审计不再把正式发布状态覆盖成candidate状态。保留策略永久排除这些权威文件和`candidate-soak.json`，不会把它们当历史文件删除。

## 真实运行和资源证据

- 当前镜像：`magnet-media-daily:173fdb9`
- 镜像ID：`sha256:a739e1daf1b951ce3acb0d9fe3260077a6856d9662551b86c845cf1deb2cdd64`
- 当前源码：`/opt/magnet-media/releases/173fdb9`
- 内存限制：768MiB
- 内存+Swap限制：1280MiB
- CPU限制：1核
- PID限制：256
- revision 10发布运行内存约76—134MiB
- 未发生OOM或内核杀进程
- 服务器磁盘40GB，剩余约16GB，使用率59%
- inode使用率21%
- 每日Timer与周审计Timer均为enabled/active
- 下一次每日任务：2026-08-06 03:34:54（UTC+8）
- 下一次周审计：2026-08-09 14:31:46（UTC+8）

旧Docker镜像和构建缓存已清理，保留当前镜像和两份近版本回滚镜像。

## 质量与验证

完整测试：

- `448 passed, 1 skipped`
- 枚举规则：241，`ALL VALID`
- compileall：PASS
- Shell语法：PASS
- systemd unit verify：PASS

revision 10 Manifest质量：

- `cover_complete=true`
- `media_id_unique=true`
- `resource_identity_unique=true`
- `cross_season_resources=0`
- `unknown_series_resources=0`
- `malformed_country_genre_values=0`
- 非法评分影视：0

## 尚未关闭的风险

### 外部主动告警

自动重试已经具备，但第二次失败后目前没有外部消息通知。故障仍会被写入：

- systemd Result和journal；
- `latest-publish.json`结构化状态；
- run历史状态文件。

该问题不会让错误数据上线，也不会破坏current，但可能让运维人员不能第一时间发现连续失败。后续可接企业微信、飞书、邮件或其他告警通道。
