# Oracle / 阿里云影视发布恢复（2026-10-24）

## 当前状态

DEPLOYED_AWAITING_FRESH_COMPUTE_AND_PUBLICATION。容量修复已部署并经过实机传输验证；完整业务恢复仍以新的 Oracle 计算、阿里云 finalizer 成功、双端公开版本前进和真实微信恢复回执为准。

- 代码：`codex/media-manifest-cap-20261024`，`a480c5c4caa3e6e78b717eac56eabe8a65642837`。
- 新 Oracle 任务：`20261024T143623Z-3c1a1265`，22:36:21 CST 启动，当前仍在运行。
- 证据：`reports/media-manifest-fix-20261024/deployment-evidence.json`。

## 故障与跨机核对

Oracle 负责抓取、质量检查和计算包；阿里云通过 SSH 获取交接包，执行最终封面计数校验、正式签名、CN / R2 对象发布和双端指针推进。Cloudflare Worker 是 R2 写入接收端。

故障发生于阿里云 finalizer 上传 manifest：实际 2,472,375 字节超过 Python bridge 和线上 Worker 共同的 2,097,152 字节自定义上限。最后成功公开 revision 为 67；当天08:20的失败状态与现场错误一致。

旧计算包 `20261023T190055Z-f54f3f8a` 在 Oracle 与阿里云均为133,826,560字节，SHA-256均为 `d1ce4d4bca2d371431ddc60a31bcb2568e8c0670958f7312caf05993e782455b`。传输未损坏；此旧包在修复时已经超过正常发布时效，因此另起新计算，保留既有时效门禁。

## 修复内容

1. Python上传端和Worker接收端同步将正式发布清单上限改为8 MiB；普通对象仍为1 MiB，current仍为64 KiB。较大额度仅适用于实际远端key符合发布manifest路径、object_kind=manifest且内容类型为JSON的对象。
2. Worker健康接口公布实际限制；新客户端严格校验数值。旧接口没有限制字段时按旧1/2 MiB保守兼容，避免部分升级后再晚期失败。
3. finalizer在任何目标开始发布前，检查整个发布计划与两个目标；orchestrator在发布锁内再检查。真正upload继续核验文件大小、SHA、不可变对象与返回结果。
4. 对象先于manifest、指针最后推进的顺序、双端公开验证、回退禁止和失败恢复流程保留；全计划预检不等于跨服务事务保证。
5. 原生产 `ee3ca0d` 封面过滤后计数验证保留。新旧镜像此函数AST摘要一致，避免以旧分支覆盖生产特有修复。

Cloudflare官方[Workers限制](https://developers.cloudflare.com/workers/platform/limits/)与[R2限制](https://developers.cloudflare.com/r2/platform/limits/)说明该2 MiB值属于本应用限制。8 MiB是有限增长余量；实际容量用线上传输验证，未开通新的付费服务。

## 部署与回退依据

- Worker原版本：`d4ac8d0e-e750-4e46-a297-09fa79a9309a`；已读取实际线上脚本核对，不只读取仓库副本。
- Worker新版本：`655af3b8-df3f-4029-bc1e-fd23e894e78b`，原R2绑定、production-auto、Secret绑定、自定义域名均保留。
- 原finalizer镜像：`magnet-media-finalizer:cover-audit-ee3ca0d`，image ID `c830a7918764…`。
- 新镜像：`magnet-media-finalizer:manifest-cap-a480c5c`，image ID `6d279292a2b55…`；仅覆盖四个相关模块，显式0644权限，linux/amd64。
- 主机源码路径：`/opt/magnet-media-finalizer/releases/manifest-cap-a480c5c`；配置已切换到新镜像，原定时器仍启用。
- 备份：`/var/backups/magnet-media/20261024-manifest-cap`，含原finalizer配置、app目标路径和成功/失败状态、旧pointer。保留旧镜像和Worker版本。
- 代码回退可恢复镜像与Worker版本；不得为回退代码而直接覆盖已前进的公开指针、成功状态或生产数据。

## 已完成验证

- Python专项：85 passed / 2 skipped。跳过原因分别为Windows不可用symlink、未提供本地M1实物release夹具；不能把两项均写成POSIX测试。
- Worker：14 passed，含真实fetch处理器的8 MiB边界、越界、错误大小/摘要、鉴权、不可变冲突和重复复用。
- 实机新旧镜像质量校验函数AST相同，四个部署模块字节SHA与本地构建源一致，导入通过。
- 线上health：1048576 / 8388608；无认证请求返回401。
- 原失败清单2,472,375字节上传并深度读回SHA通过；摘要 `a508ab3d7fb41d529d6f7739a82ba3f83383ff0c79c4a85659a33dfd247052ce`。
- 恰好8,388,608字节的实机边界探针上传与深度读回通过；声明上限+1字节返回HTTP400。测试对象已删除并通过HEAD确认不存在。
- 上述探针没有推进公开指针，仍为revision67；完整业务发布结果将在本记录补充。

## 待闭合

新Oracle包的完成时间、质量门、最终计数和SHA；阿里云接收同一包与新镜像实际执行；新revision双端指针/manifest与关键资源读取；finalizer success/exit0和持久成功状态；微信真实恢复回执。下一次无人值守自然周期与本次人工触发完整业务周期分别记载。
