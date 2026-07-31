# 影视每日流水线 Candidate-Only 无人值守加固（2026-07-31）

## 结论

`IMPLEMENTATION=PASS`

`REAL_REVISION7_REHEARSAL=PASS`

`ALIYUN_CANDIDATE_DEPLOYMENT=READY`

`PRODUCTION_AUTO_PUBLISH=DISABLED`

本批关闭死锁、历史膨胀、2GB主机资源失控、空目录切换Nginx、伪candidate、评分全量尖峰和冷启动重抓等阻塞。正式revision 7与R2/阿里云current均未修改。

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

## 测试

- Python全量：424 passed，1 skipped；
- compileall：PASS；
- 枚举契约：241 / ALL VALID；
- Shell语法：PASS；
- diff-check：PASS；
- 锁、清理、磁盘、Soak、候选密钥分权、Nginx迁移、种子安装、评分轮转和CLI跨区域编码均有永久反例；
- 本地无Docker命令，容器构建必须在阿里云现有Docker环境完成。

## 尚未完成

- 尚未在阿里云构建新Docker镜像；
- 尚未安装candidate service/timer；
- 尚未执行服务器首轮手动candidate；
- 尚未开始7日Soak；
- 尚未增加外部heartbeat和双端Pointer告警；
- 正式自动发布继续禁止。
