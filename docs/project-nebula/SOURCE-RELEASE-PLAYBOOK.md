# 搜索源发布、续期与 App 消费权威手册

> **用途**：源规则发生变化、只刷新加密 envelope、源端点异常、K30S 未拿到最新源时，统一按本文执行。
>
> **核心数据**：`sources.json` 是开发侧规则真源；用户只能拿 `sources.enc.json`；App 只接受能成功下载、解密、通过 freshness/版本/green 校验的 authority。
>
> **红线**：任何脚本/CI **不得自行修改 `health.status`**。测试先产证据，状态升降级必须由用户/开发者明确确认后再修改。

---

## 1. 先区分两种“源发布”

### A. 源内容发布

适用：

- 新增规则；
- selector/handler/template 修复；
- 用户明确批准 health 状态变化；
- quality/pool/capability 变化。

链路：

```text
sources.json
→ 合约/爬虫测试
→ 人工确认状态
→ encrypt_sources.py
→ mg-data/sources.enc.json
→ GitHub Raw / Pages / Gateway / Aliyun / CDN
→ exact SHA convergence
→ K30S 实际消费 + 搜索
```

### B. envelope-only 续期

适用：源 payload 不变，只是 72h 加密 envelope 快到期。

链路：

```text
mg-data source pack
→ refresh_source_envelopes.py 解密校验
→ payload hash 保持不变
→ 更新 issued_at/expires_at
→ 重新加密
→ source-envelope-bot commit
→ 公网 authority convergence
→ 阿里云定时同步
→ App 前台/定时自动刷新
```

两条链不能混为一谈。续期不能偷偷改变源 payload。

---

## 2. 当前文件与物理目录

### m023 工作区

```text
D:\lpproduct\m023\sources.json
D:\lpproduct\m023\encrypt_sources.py
D:\lpproduct\m023\mg-data\sources.enc.json
D:\lpproduct\m023\mg-data\config.json
```

### 官网/Pages 主项目

官网目录当前实际位于：

```text
D:\lpproduct\magnet\magnetgoogo-site\
```

其中包含：

```text
config.json
sources.enc.json
sources-green.enc.json
```

**不要因为 m023 没有 `magnetgoogo-site` 就假定官网不存在。**

---

## 3. `sources.json` 状态治理

唯一有效 `health.status`：

```text
green
yellow
gray
```

唯一有效 `health.status_detail`：

```text
ok
healed
waf
404
expired
unreachable
parsing_failed
```

### 当前唯一 GREEN 证据标准

源升级 `green` 必须：

1. 源可达；
2. 用**不同 bait** 做搜索；
3. 至少两次都能抽取合法 magnet；
4. 两次 info-hash 集合显著不同：

```text
overlap = |A ∩ B| / max(|A|, |B|) < 0.8
```

这是为了排除“首页固定 magnet / 假搜索结果”。

单次 magnet、HTML 含磁力关键词、只看到列表 DOM，都不足以升级 green。

### 自动脚本的治理边界

这些旧入口包含自动写状态能力：

```text
scripts/health_check.py --update
scripts/health_check.py --deploy
python -m magnet.crawler_v3 recheck ... --commit
magnet/funnel_pipeline.py --update-sources
```

在**当前人工确认规则下**：

- 默认只用报告模式；
- 先保存证据；
- 用户/开发者明确批准后才允许写 `sources.json`；
- 不允许定时 CI 自动升降级。

`.github/workflows/health-check.yml` 中历史 `--update` 自动提交逻辑属于**旧治理遗留**，不作为当前状态变更 authority；修改/启用它前必须先与本条红线对齐。

---

## 4. 源内容修改后的本地门禁

### 4.1 enum 契约

```bat
python magnet/validate_enum.py
```

必须：

```text
ALL VALID
```

### 4.2 静态 delivery contract

```bat
python scripts/audit_source_delivery.py sources.json
```

必须：

```text
hardFindingCount = 0
```

重点防：

- 重复 rule id；
- 无效 origin；
- green 没 pool；
- green 没 executor；
- 无 query token；
- 未知 handler；
- contract 字段错误。

### 4.3 crawler_v3 deterministic suite

```bat
python -m pytest magnet/tests/crawler_v3 -m "not integration" -q
```

Integration 测试必须与 deterministic gate 分开看。公网源数量会波动，不能因为某次 live provider 只返回 4 条而把 deterministic 功能误判坏掉。

### 4.4 关键源 live probe

按变更 scope：

```bat
python -m magnet.crawler_v3 search "Inception" --origin <host>
python -m magnet.crawler_v3 search "流浪地球" --origin <host>
```

需要 WAF/CF 的源按 `SOURCE-CRAWL-AND-TEST-PLAYBOOK.md` 使用 Tier1 / verify-interactive。

---

## 5. 加密发布包

### 5.1 生成

在项目根目录：

```bat
python encrypt_sources.py
```

脚本会：

1. 读取 `sources.json`；
2. 读取 `mg-data/config.json` 的：
   - `source_expiry_hours`
   - `min_version`
   - `source_schema_version`
3. 封装：
   - schema_version
   - issued_at
   - expires_at
   - min_app_version
   - payload
4. gzip；
5. AES-256-CBC；
6. HMAC-SHA256；
7. 写 `mg-data/sources.enc.json`；
8. 立即做 roundtrip 校验。

**不要在文档、聊天、日志里输出加密密钥。**

### 5.2 注意 `--verify`

当前 `encrypt_sources.py` 的 main 流程会先重新加密再 roundtrip 验证，所以：

```bat
python encrypt_sources.py --verify
```

也会产生新 IV/新密文字节。

因此“只想比较当前公网文件是否没变化”时不要用它作为只读 hash 命令。

---

## 6. 加密包发布前验证

至少检查：

```text
[ ] roundtrip OK
[ ] schema_version 正确
[ ] expires_at 在未来且剩余时间符合策略
[ ] min_app_version 正确
[ ] payload 中 green 数 > 0
[ ] 不是 0-green authority
[ ] 本地 sources.json enum ALL VALID
[ ] static audit hard=0
```

当前 App 会明确拒绝：

- 已过期 envelope；
- invalid expires_at；
- App 版本低于 min_app_version；
- 解密失败；
- **0 green** pack。

---

## 7. `mg-data` 发布

`mg-data` 是 source/config 公共 authority 仓库。

### 7.1 推荐手工可控路径

先确认：

```bat
cd mg-data
git status --short
git diff -- sources.enc.json
```

然后只提交需要的 source 文件：

```bat
git add sources.enc.json
git commit -m "chore: publish source pack"
git push origin main
```

如果是 green-compliance pack 也发生变化，再明确包含 `sources-green.enc.json`；不要习惯性 `git add -A` 把其它测试/配置带进去。

### 7.2 `encrypt_sources.py --deploy`

脚本支持自动 commit/push，但它内部会 `git add -A`。

因此只有在 `mg-data` 工作区确认**完全干净且所有变化都应该发布**时才使用：

```bat
python encrypt_sources.py --deploy
```

否则使用 7.1 的显式提交路径。

---

## 8. 当前 App 的 source authority 顺序

**这是 v0.2.6 当前真实代码，替代旧文档里的“6端点 Promise.any 最快者胜出”。**

`secureSourceStore.ts`：

### Authorities

按信任层依次尝试：

```text
1. https://magnetgoogo.com
2. https://raw.githubusercontent.com/734496335/mg-data/main
3. https://api.naoshiquan.com
```

每个 endpoint 都必须：

```text
HTTP 成功
→ body 非空
→ decrypt 成功
→ envelope fresh
→ usable green > 0
```

通过后才接受。

### Fallbacks

只有全部 authority 失败后：

```text
1. https://cn.magnetgoogo.com
2. https://cdn.jsdelivr.net/gh/734496335/mg-data@main
3. https://maggoogo-gateway.734496335lp.workers.dev
```

### 为什么不再 Promise.any

历史 bug：一个**更快但旧/过期**的镜像可能抢赢一个稍慢但正确的新 authority。

现在策略是：

```text
trust order > speed race
```

所以后续任何“优化速度”的改动都不能重新引入 stale-fast-mirror race。

---

## 9. Pages / Gateway / Aliyun 同步

### 9.1 Cloudflare Pages

主项目官网目录：

```text
D:\lpproduct\magnet\magnetgoogo-site
```

部署前把已确认的 source pack 同步进网站目录：

```powershell
Copy-Item -LiteralPath D:\lpproduct\m023\mg-data\sources.enc.json `
  -Destination D:\lpproduct\magnet\magnetgoogo-site\sources.enc.json -Force
```

先比较两个本地文件 SHA，完全一致后再部署：

```bat
cd D:\lpproduct\magnet
npx wrangler pages deploy magnetgoogo-site --project-name=magnetgoogo-site --branch=main
```

部署后 `https://magnetgoogo.com/sources.enc.json` 必须和 `mg-data/sources.enc.json` exact SHA 一致。

### 9.2 Gateway

Gateway 的 source 路径由当前 control plane 提供：

```text
https://api.naoshiquan.com/sources.enc.json
```

当前 Gateway 已采用 mutable config/source fail-closed：authority 总失败时返回错误，而不是用 `0.0.0` 或陈旧默认值降低门禁。

发布后必须验证 exact SHA，不只看 HTTP 200。

### 9.3 Aliyun

当前生产有 hourly：

```text
magnet-source-sync.service
```

它会检测新的 source pack，经 crypto/schema/freshness 验证后安装到阿里云。

历史真实续期已验证：source-envelope-bot 产生新 envelope 后，Aliyun 定时服务数秒内安装成功。

若阿里云未收敛：

- 先查 service/timer 状态与日志；
- 再查 TLS；
- 不要为了让 Aliyun 对齐而回滚其它已正确 authority。

---

## 10. 公网 exact-SHA 收敛验证

`mg-data` 内现有：

```bat
cd mg-data
python scripts/verify_public_source_authority.py
```

Required authority：

```text
GitHub Raw
magnetgoogo.com
api.naoshiquan.com
```

脚本会将远端 bytes 的 SHA256 与本地 `sources.enc.json` 比较，并有有限重试。

成功：

```text
SOURCE_AUTHORITY_CONVERGENCE_PASS
```

Optional：

```text
jsDelivr
old workers.dev
```

它们失败/陈旧应记录为 fallback debt，但不能冒充 required authority 已失败。

### 为什么不用“文件大小一样”作为最终证据

AES 密文不同可能大小相同；config/body 也可能同字节数不同内容。

**最终 authority 一律比较 SHA256。**

`scripts/verify_endpoints.ps1` 的旧版 size/version 输出只适合辅助排查，不作为最终 source convergence gate。

---

## 11. 自动 envelope 续期

`mg-data/.github/workflows/refresh-source-envelopes.yml`：

```text
schedule: 每 8 小时（17 */8 * * *）
validity: 72 小时
refresh threshold: 剩余 <= 32 小时
```

流程：

```text
pytest renewal state machine
→ refresh_source_envelopes.py
→ decrypt/HMAC/schema 检查
→ payload canonical hash
→ 只刷新 issued_at/expires_at
→ roundtrip 再验证 payload 不变
→ bot commit/push
→ purge jsDelivr
→ required authority convergence
```

GitHub Secret：

```text
SOURCE_ENCRYPTION_KEY_HEX
```

只说明变量名，不在本地日志/文档中写值。

### 手工强制续期

通过 GitHub Actions `workflow_dispatch force=true` 优先。

本地只有在安全环境已提供 `SOURCE_ENCRYPTION_KEY_HEX` 时：

```bat
cd mg-data
python scripts/refresh_source_envelopes.py --file sources.enc.json --expiry-hours 72 --refresh-before-hours 32 --force
```

随后仍要 commit/push + authority convergence。

---

## 12. App 端 source 生命周期

`SourceContext.tsx` 当前行为：

### 启动

```text
memory fresh
→ encrypted disk cache
→ bundled bootstrap
→ silent remote sync
```

### 前台恢复

如果距上次 sync attempt >= 30 分钟：

```text
silent source sync
```

### App 保持前台

每 6 小时：

```text
periodic silent sync
```

### 过期 fail-closed

远程续期失败且 active pack 已过期：

```text
sources=[]
meta=null
```

不继续长期使用过期内存源。

### bootstrap

bundled bootstrap 有自己的首次使用生命周期，用来解决首次启动/远程临时失败，但不能代替长期 remote renewal。

---

## 13. K30S 消费验收

**source 发布没有经过 K30S 实际搜索，不算闭环。**

推荐 Debug：

```bat
python scripts/test_k30s_search.py --compact --only "EN movie" --only "ZH movie" --output scripts/k30s-source-release-smoke.json
```

检查：

```text
sourcePackOrigin = 当前 authority/cache
loadedHostCount / loadedPoolCount 合理
completed=true
hardFindingCount=0
hash placeholder=0
```

必要时再跑：

```bat
python scripts/test_k30s_search.py --benchmark --compact --output scripts/k30s-source-release-benchmark.json
```

当前真实续期链曾验证：

```text
远端新 pack
→ Aliyun sync
→ K30S decrypt/cache
→ 148 hosts / 52 pools
→ Inception real search
```

---

## 14. 源发布后的 rollback 思路

不要直接删源。

若新源 pack 发现严重问题：

1. 确认问题来自 payload 而不是单个 endpoint；
2. 从 Git 历史恢复上一份正确 `sources.json`/规则变化；
3. 重新生成**新的 fresh envelope**；
4. 发布到 authorities；
5. exact SHA convergence；
6. K30S 消费验证。

不要直接拿已经快过期的旧密文覆盖回来。

---

## 15. 常见失败与处理

### 快镜像旧数据抢 authority

**历史 bug，当前已修复。**

任何重新出现 `Promise.any` / “最快 200 即接受”的 source selection 都应阻断 review。

### 0 green pack

App 必须拒绝，不得让一个可解密但空 green 的 pack 覆盖健康源。

### envelope 到期

先看 `issued_at/expires_at`，再看 renewal workflow / bot commit / authority SHA / Aliyun sync；不要直接怪爬虫。

### jsDelivr `@main` 缓存陈旧

它是 fallback。先确认 required authorities；可 purge，但不要让 CDN branch cache 成为 mutable authority。

### Windows TLS 对 `cn` 探测失败

区分 Windows Schannel 本机问题和真实公网可用性；Aliyun 是 fallback，不能因此否定 required authorities 已收敛。

---

## 16. 源发布最终 Gate

```text
规则层
[ ] 源变更有证据
[ ] status 变更已人工确认
[ ] validate_enum = ALL VALID
[ ] audit_source_delivery hard=0
[ ] crawler_v3 deterministic PASS
[ ] 变更源 live probe PASS

加密层
[ ] encrypt roundtrip PASS
[ ] envelope fresh
[ ] min app/schema 正确
[ ] green > 0

发布层
[ ] mg-data commit/push 正确
[ ] GitHub Raw exact SHA
[ ] Pages exact SHA
[ ] Gateway exact SHA
[ ] Aliyun/fallback 状态记录
[ ] required authority convergence PASS

消费层
[ ] K30S 拉到新 pack
[ ] loaded hosts/pools 合理
[ ] EN/ZH real search PASS
[ ] quality hard=0
[ ] hash placeholder=0
```

---

## 17. 相关文档

- `SOURCE-CRAWL-AND-TEST-PLAYBOOK.md`
- `SOURCE-SECURITY.md`
- `K30S-TEST-PLAYBOOK.md`
- `USER-IMPACT-INCIDENTS.md`
- `FAST-DISCOVERY-FUNNEL.md` — 漏斗算法历史/细节参考，状态判定以本文和 AI-RULES 为准
- `SOURCE-DISCOVERY-AND-VERIFICATION-STRATEGY.md` — 历史方法参考
