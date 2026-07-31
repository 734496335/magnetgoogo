# 影视资源阿里云自动运行与容量审计

日期：2026-07-31（UTC+8）
审计对象：`feature/media-daily-automation` / 阿里云 `47.103.155.154`

## 一、最终裁决

```text
ALIYUN_STATIC_MEDIA_SERVING=PASS
CURRENT_SERVER_FULL_AUTOMATION=FAIL
CURRENT_AUTOMATION_PRODUCTION_READY=FAIL
SAFE_TO_ENABLE_TIMER_NOW=NO
RECOMMENDED_MINIMUM_SERVER=2C4G + 60GB ESSD
```

现有阿里云机器继续承载Nginx静态影视目录没有压力，但不能直接安装并启用当前`magnet-media-daily.timer`。阻塞同时来自代码、部署流程、证书和机器余量，并非单纯升级内存即可完全解决。

## 二、服务器实时状态

实例类型：`ecs.e-c1m1.large`

```text
CPU：2 vCPU
内存：1.8 GiB
已用内存：约1.4 GiB
可用内存：约461 MiB
Swap：4 GiB，已使用约541 MiB
系统盘：40 GiB，剩余约18 GiB
系统负载：0.00 / 0.00 / 0.00
现有媒体静态目录：约27 MiB
```

主要常驻内存：

```text
openclaw-gateway：约672 MiB
Node进程：约254 MiB
SearXNG：约124 MiB（Docker统计）
```

CPU和磁盘IO当前很空闲，但内存已经进入长期Swap状态。自动化脚本给容器配置`--memory 1500m --cpus 1.75`，相当于允许一个批处理任务占用接近整机内存和绝大多数CPU，缺少安全余量。

## 三、当前自动化代码阻塞

### P0-1 未接入仅磁力策略

Revision 7通过独立的`filter-media-magnets`流程生成。`media_daily.py`仍直接聚合完整资源并构建发布，可能在下一次自动revision中重新加入网盘资源。

### P0-2 自动评分负载不符合当前产品范围

`media_daily.py`对电影和剧集逐条调用四路评分解析。419条影视首次运行理论上可能触发上千次外部请求，且逐条推进；这会显著延长运行时间、增加不稳定来源，并可能因评分变化制造无必要revision。当前用户已明确评分留待下一App版本，自动流程应关闭评分阶段。

### P0-3 外层锁无法恢复

`_run_lock()`只使用`O_EXCL`创建`/var/lib/magnet-media/locks/media-daily.lock`，不校验PID是否仍存在。断电、Docker被杀、systemd四小时超时或主机重启后，锁文件可能永久保留，后续每日任务全部失败，必须人工删除。

### P0-4 示例配置与Revision 7不一致

```text
min_movies=400       当前仅磁力电影=199
min_series=350       当前仅磁力剧集=220
min_app_version=0.2.1  Revision 7要求=0.2.3
```

直接使用示例配置会导致仅磁力候选长期无法通过数量门禁，或错误允许旧客户端消费后续revision。

### P0-5 没有磁盘保留策略

当前每个完整本地Release约27 MiB，`runs/`、`releases/`、状态历史、收据、评分缓存和SQLite历史均没有自动清理。

若每天产生一个新Release：

```text
27 MiB × 365 ≈ 9.6 GiB/年
```

这还不含运行目录、数据库增长、Docker镜像和公开对象。现有18 GiB余量无法支撑长期无清理日更。

### P0-6 周审计与每日发布可能冲突

周审计为周日02:30，每日发布为03:30。审计模式仍执行评分、Bundle和线上控制检查，并非纯只读轻量审计。若运行超过一小时，每日任务会因外层锁直接失败，且没有同日重试。

### P0-7 安装脚本可能切断当前线上目录

当前Nginx从：

```text
/var/www/magnetgoogo-site/media
```

提供Revision 7。安装脚本会替换媒体Snippet，改为Alias：

```text
/var/lib/magnet-media/public
```

服务器当前不存在`/var/lib/magnet-media`有效数据。直接执行安装脚本会在数据尚未引入前把正式媒体地址切到空目录，造成404。

### P0-8 证书续期已实际失败

```text
证书到期：2026-08-02 00:06:13 UTC
certbot-renew.timer：active
certbot-renew.service：failed
失败原因：HTTP-01 challenge返回403
```

Timer处于等待状态不等于续期成功。国内镜像即将因TLS证书到期失效，必须先修复DNS-01或HTTP-01路径并完成一次真实续期。

### P1-1 缺少生产告警与自动降级

当前没有主动通知以下事件：

- Timer未执行或连续失败；
- 锁文件长期存在；
- 某来源长期不更新；
- 仅磁力数量低于门槛；
- 磁盘、内存或Swap越界；
- R2与阿里云Pointer不一致；
- 证书续期失败。

### P1-2 自动签名密钥安全边界偏弱

无人值守签名需要把Ed25519私钥和生产R2上传能力放到公开服务主机。该机器同时运行多个现有服务，任何主机级失陷都可能获得签名和发布权限。更稳妥的是使用独立任务机或至少独立系统用户、最小权限Worker和严格只读文件系统。

## 四、服务器能扛什么

### 当前2C2G可安全承担

- Nginx静态影视目录；
- Revision Pointer、Manifest、封面和资源对象分发；
- 每日一次轻量状态检查；
- 修复后、严格限额的候选模式增量抓取试运行。

### 当前2C2G不应直接承担

- 全量首次抓取；
- 四路评分补全；
- 1.5 GiB容器上限的图片与Release构建；
- 与现有服务并行的正式自动签名发布；
- 无清理策略的长期日更。

## 五、推荐生产配置

### 推荐方案A：独立或升级任务机

```text
CPU：2 vCPU
内存：4 GiB最低
磁盘：60 GiB ESSD最低，建议80 GiB
Swap：2—4 GiB，只作故障缓冲
运行频率：每日一次
容器限制：1 CPU，1.5 GiB内存，2 GiB memory-swap
```

若未来重新启用评分、浏览器渲染或更多来源，建议4C8G。

### 方案B：继续使用当前2C2G，仅限受控试运行

必须先完成全部P0修复，然后：

```text
模式：candidate / --no-publish
连续观察：至少7天
运行频率：每天一次
CPU限制：0.75—1.0 CPU
内存限制：640—768 MiB
memory-swap：不超过1 GiB
评分：关闭
来源：串行
历史保留：runs 7天、release 3个、失败证据30天
发布：试运行期间禁止提升current.json
```

若单次运行使Swap新增超过100 MiB、可用内存低于200 MiB、任务超过2小时或影响现有Node/OpenClaw服务，立即停止并升级到4 GiB。

## 六、建议上线顺序

1. 先修复并真实续期`cn.magnetgoogo.com`证书。
2. 将仅磁力过滤内置到`media-daily`正式流程，并永久测试cloud=0。
3. 完全关闭自动评分阶段。
4. 增加死PID锁恢复和systemd超时反例。
5. 增加run/release/object/log保留与磁盘水位门禁。
6. 更新门槛为Revision 7真实基线，`min_app_version=0.2.3`。
7. 改造安装流程：先在独立目录导入Revision 7，再原子切换Nginx Alias，禁止空目录切换。
8. 候选模式连续运行7天，记录峰值RSS、Swap增量、耗时和来源成功率。
9. 通过后再启用自动发布，并增加R2/阿里云双端Pointer告警。

## 七、结论

当前最合理的架构仍是：阿里云负责静态镜像，爬取和签名发布放到独立4GB任务环境。若必须复用当前机器，只能先做轻量、无评分、仅磁力、禁止发布的候选试运行，不能现在直接打开正式Timer。
