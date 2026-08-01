# 影视每日流水线 Candidate-Only 无人值守加固（2026-07-31）

## 结论

`IMPLEMENTATION=PASS`

`REAL_REVISION7_REHEARSAL=PASS`

`ALIYUN_CANDIDATE_DEPLOYMENT=PASS`

`SOAK_DAY1=PASS`

`CANDIDATE_TIMERS=ACTIVE`

`PRODUCTION_AUTO_PUBLISH=SUPERSEDED_BY_REVISION8_RELEASE`

本批关闭死锁、历史膨胀、2GB主机资源失控、空目录切换Nginx、伪candidate、评分全量尖峰和冷启动重抓等阻塞，并完成阿里云candidate-only部署和首轮真实运行。本文记录候选阶段历史状态；后续正式自动发布结论见`MEDIA-DAILY-AUTO-PUBLISH-REVISION8-20260801.md`。

## 运行锁与共享状态

- 锁文件新增PID、Linux boot ID、随机token和开始时间；
- PID死亡或服务器重启后可安全回收残锁；
- PID仍存活、锁内容不完整或锁文件发生竞争变化时拒绝删除；
- 释放锁时只允许删除本次随机token对应的锁；
- 并发任务在拿到锁前不再创建run目录，也不再覆盖`status/latest.json`；
- weekly audit与daily candidate使用不同Docker容器名，真正由持久锁裁决并保留结构化状态。

## Candidate语义修复

原`--no-publish`只生成Feed和Bundle，没有构建签名release，不能证明正式发布链可用。现在candidate模式会完整执行：

1. 抓取或回放四源数据库；
2. 聚合；
3. 仅磁力过滤；
4. 四评分状态恢复与限额补抓；
5. 封面Bundle；
6. 读取线上revision 7 current和Manifest；
7. 用正式生产公钥验证上一Manifest；
8. 使用服务器本地非生产候选密钥构建revision 8候选；
9. 完整校验签名、对象路径、SHA和大小；
10. 停止，不上传、不提升current。

候选私钥不受0.2.3信任；阿里云不部署生产私钥和R2提升令牌。即使误把候选文件放到公网，正式客户端也不会信任其签名。

## 评分负载边界

- 新增`rating_lookup_limit_per_feed`，默认电影40、剧集40次查询尝试/日；
- 查询游标持久化到`ratings/progress.json`；
- 已完整四评分项目不消耗预算；
- 提供方报错也消耗预算并推进游标，防止故障项目永久卡住队首；
- 游标循环覆盖全部影视，`next_offset=0`回环已建立反例；
- 状态损坏时保守归零并记录，不阻塞标题/封面/磁力候选；
- weekly audit使用`--skip-ratings`，不与每日评分任务重复消耗网络。

真实网络限额演练：电影5次、剧集5次，双方错误均为0，游标分别推进到5，候选签名验证PASS，封面HTTP请求0。

## 历史保留与磁盘门禁

默认保留：

- run目录7份；
- 状态历史30份；
- 本地候选release和pointer各3份；
- 发布收据30份。

运行前和结束后均执行清理。活动run受保护；pointer引用的release不会被误删。清理失败只记录warning，不掩盖原始任务结果。

磁盘门禁：

- 使用率达到80%时拒绝新任务；
- 可用空间低于2GiB时拒绝新任务；
- 门禁发生在抓取和构建之前。

## 2GB主机资源限制

Docker默认上限：

- 内存：768MiB；
- 内存软保留：512MiB；
- 内存+Swap总上限：1280MiB；
- CPU：1.0核；
- PID：256；
- `/tmp`：128MiB tmpfs；
- drop all capabilities；
- no-new-privileges。

每日service固定运行`candidate`模式；weekly audit改到周日14:30，与每日03:30窗口分离。安装器默认不启用Timer，只有显式`ENABLE_TIMERS=1`才开启。

## Nginx原子迁移

切换前完整验证当前正式媒体树：

- current schema、revision和release ID；
- Manifest路径和SHA；
- Manifest中的每个对象路径、大小和SHA。

验证通过后先复制到同级临时目录，再原子替换`/var/lib/magnet-media/public`。目标已有效则幂等返回；目标非空但无效则拒绝覆盖。Nginx配置修改前备份原配置和snippet，`nginx -t`或reload失败会自动回滚。

真实revision 7演练：

- Manifest对象：1225；
- 验证字节：24,236,771；
- 原子迁移后文件：1227；
- revision：7；
- release ID：`20260730T000000Z-5c299304`；
- Manifest SHA：`83f38186a06457a8e5bb8ddcda7587b9accbfa1f93bd477b15213b2bff8f02e8`；
- 第二次执行：`already_ready`。

## 冷启动种子

种子目录：`D:\lpproduct\magnet-candidate-seed-20260731`

内容：

- SixV电影100条SQLite；
- DYTT8899 249条有效记录/250目标SQLite；
- Meijumi 100条SQLite；
- SixV-series 100条SQLite；
- 预热后的电影和剧集封面Bundle；
- revision 7已有287条评分/身份状态；
- candidate audit和逐文件SHA清单。

种子证据：

- 417个文件；
- 37,583,895字节；
- 四库`PRAGMA integrity_check=ok`；
- 电影封面对象215；
- 剧集封面对象188；
- 第二次candidate audit封面HTTP请求0。

专用安装器会验证文件集合、每个文件SHA/大小、SQLite完整性和记录数；发现任务锁时拒绝安装；`sources`和`bundles`采用目录原子替换。SQLite验证使用`immutable=1`，确保验证本身不会生成`-wal/-shm`污染种子。

## 真实候选结果

基于四个可靠性数据库和预热Bundle，完整candidate audit得到：

- 电影214；
- 剧集220；
- 磁力3561；
- 过滤网盘1295；
- cloud最终为0；
- 候选revision 8；
- release ID：`20260730T000000Z-5faf7fdc`；
- 内容SHA：`6e80f78209dfd1f89b671f2b631ed2bf0db7934331eadf1e293cc83cd147f3af`；
- 对revision 7回归：无回归；
- 第二次执行：内容SHA和release ID一致，封面请求0。

另使用revision 7原始199/220 Feed进行独立候选重建：1225对象全部验证通过，候选pointer revision 8，正式上一版签名验证PASS。

## 7日Soak判定

`status/candidate-soak.json`按Asia/Shanghai自然日记录：

- 同一天重复成功只记1天；
- 必须连续7个不同日期成功；
- 任一正式daily candidate失败立即清零；
- weekly audit不计入；
- 达到7天后仅输出`ready_for_promotion=true`，不会自动提升current。

## 阿里云正式Candidate-Only部署

部署于现有`ecs.e-c1m1.large`主机，未部署生产私钥和R2上传令牌。

- Docker镜像ID：`sha256:694d13a70b72a3bdec5aa4e0bbb5b10e72c03f94e261ea5661a030d4ee15a7c8`；
- 镜像大小：291,317,206字节；
- 构建期间最低可用内存约483MiB，Swap未持续增加；
- 种子417文件、37,583,895字节安装成功；
- revision 7的1225对象、24,236,771字节原子迁移成功；
- Nginx配置测试PASS；
- 公网current与新状态目录current SHA均为`0068f832ee016fa22d35939d5250d711f1aa40f60d121e4ad6501fe1f6c80f93`；
- 公网仍为revision 7、release `20260730T000000Z-5c299304`。

部署过程中额外关闭：

- Docker Hub不可达：使用固定摘要的国内镜像代理基础镜像；
- 默认PyPI异常：构建参数显式指定阿里云PyPI；
- Windows `git archive`导出CRLF：新增`.gitattributes`和归档级LF门禁；
- 宿主Python 3.6：部署辅助脚本统一在Python 3.11容器执行。

## 首轮真实Candidate

运行时间：2026-08-01 00:16:34—00:41:11（UTC+8），约24分37秒。

结果：

- `status=success`；
- `candidate_verified=true`；
- candidate revision：8；
- 电影217；
- 剧集227；
- 磁力3597；
- cloud 0；
- release ID：`20260731T000000Z-67da50cd`；
- 内容SHA：`f18dd760cca273a01d16d72c495bcb2bff3d7cbd3b7a83d9dda5a4b0177ce946`；
- 无正式数据回归；
- 电影封面新增3张、剧集新增7张，其余全部复用；
- 四源抓取HTTP请求共37次；
- 评分严格限制为电影40次、剧集40次，双方0错误；
- 新增/补全豆瓣33、IMDb25、烂番茄28，Bangumi本轮无可靠匹配；
- 无OOM、无内核杀进程、无容器资源限制失败；
- 运行后主机可用内存约463MiB、Swap约491MiB。

Soak状态：

- 成功日期：2026-08-01；
- `consecutive_days=1`；
- `ready_for_promotion=false`；
- daily candidate Timer和weekly audit Timer均已enabled/active；
- 下一次daily candidate：2026-08-02 03:34:20 UTC+8；
- 下一次weekly audit：2026-08-02 14:35:49 UTC+8。

## 测试

- Python全量：424 passed，1 skipped；
- compileall：PASS；
- 枚举契约：241 / ALL VALID；
- Shell语法：PASS；
- diff-check：PASS；
- 锁、清理、磁盘、Soak、候选密钥分权、Nginx迁移、种子安装、评分轮转和CLI跨区域编码均有永久反例；
- 本地无Docker命令，容器构建必须在阿里云现有Docker环境完成。

## 后续状态

2026-08-01经用户明确授权并完成独立候选审计后，候选阶段已结束：

- 正式revision 8已发布；
- 服务器已安装正式签名链和root权限上传令牌；
- 每日Timer已切换为production publish；
- R2与阿里云current/Manifest字节一致；
- 当前剩余事项为外部heartbeat、失败告警和双端Pointer漂移告警。

完整证据见`MEDIA-DAILY-AUTO-PUBLISH-REVISION8-20260801.md`。
