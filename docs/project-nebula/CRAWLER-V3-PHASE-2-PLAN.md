# crawler_v3 Phase 2 实施手册：品牌覆盖率扩展

> **Phase 1 已完成于 2026-05-28** — 4-Tier 架构落地、thatcdn handler 实现、web 端迁移、回归测试。tag `crawler-v3-stable`。详情见 `docs/project-nebula/DEV-LOG.md`。
>
> **Phase 2 目标**：把可用独立品牌数从 **48 → 98（+104%）**，**不靠加新源**，靠把现有 53 个 yellow 源真正打通。
>
> **本文档读者**：MiMo v2.5 Pro。Token 预算无限，**不怕苦活**。优先「逐源单独验证 + 单源单 commit」的精细化，胜过「批量改完一锅交」。
>
> **回滚锚点**：tag `crawler-v3-stable`（commit `1802c9a`）。

---

## 0. 必读：当前真实状态

### 品牌（不是源数）级覆盖现状

| 维度 | 数 |
|---|---|
| 总源数 | 240 |
| 独立品牌总数（推断）| ~143 |
| **green 池覆盖品牌** | **48** ⭐ |
| yellow 池覆盖品牌 | 57 |
| **yellow-only 品牌（unlock = 净增覆盖）** | **50** |

**绝大多数 green 是镜像冗余**：thepiratebay 12 域名 = 1 品牌、磁力宝 24 域名 = 1 品牌。所以 101 green 源真正只贡献 48 个独立资源池。每个独立品牌 = 一个独立站长 + 一个独立索引库。

### 这次要解锁的是

**Task E（8 源 / 8 品牌）**：站点本身正常，被 CF/WAF 挡住，CloakBrowser 一行配置就能过。
**Task F（45 源 / 42 品牌）**：站点能访问，但选择器过期 / 站点改版，需要逐源修选择器。

理论解锁 50 个独立品牌（一些 F 源可能死/废弃，实际 ~30-40 个）。

### Phase 1 已建好的工具（拿来用，别重写）

| 工具 | 用途 |
|---|---|
| `python -m magnet.crawler_v3 search "Q" --origin X --limit 5` | 单源搜索测试 |
| `python -m magnet.crawler_v3 classify --origin X` | 看 Tier 路由计划 |
| `python -m magnet.crawler_v3 verify-yellow "Q"` | 批量跑 yellow |
| `magnet/crawler_v3/_debug_probe.py` | CloakBrowser 探针（dump HTML / 自动找搜索框） |
| `magnet/crawler_v2/smart_list.py` | Smart List Detector（**别重写，import 用**） |
| `magnet/crawler_v3/parser/__init__.py::extract_results_from_html` | 选择器优先 + smart_list 兜底的统一解析入口 |
| `magnet/health_check.py::_probe_with_v3` | health 走 v3 orchestrator |

### Phase 2 增量目标清单（精确 ID）

源清单已写入 `docs/project-nebula/_phase2_targets.json`，按 Task E / F 分组。每个 entry 含 `id, name, origin, brand, detail, search_template`。**Agent 起手第一件事是读这个 JSON**。

---

## 1. 启动后的 5 分钟 onboarding

```powershell
# 1. 看回归测试还过
python -m pytest magnet/tests/crawler_v3 -m 'not integration' -q
# 期望：48/48 passed

# 2. 看 v3 主路径还活
python -m magnet.crawler_v3 search "Inception" --origin uindex.org --limit 3
# 期望：3 magnets in <3s

# 3. 看清单
type docs/project-nebula/_phase2_targets.json | findstr origin | Measure-Object -Line
# 期望：~53 行（8 + 45）

# 4. 看本文档 §3 / §4 的精确流程后再开干
```

任何一步失败 → **停下问用户**，不要瞎试。

---

## 2. 全局规约（每个 Task 都遵守）

### 2.1 工作流

**单源单 commit**。每完成一个源（不管 Pass 还是 Skip）都立刻 commit：

```
git add sources.json magnet/crawler_v3/handlers/<file>.py docs/project-nebula/_phase2_progress.md
git commit -m "feat(crawler_v3-phase2): <brand>(<origin>) -> <result>

Task: E.<NN> or F.<NN>
Result: PASS (n=<count> magnets in <T>s) | FAIL (<reason>) | SKIP (<reason>)
Changes:
 - sources.json: <what changed>
 - <other files if any>"
```

这样回滚 / review 都到单源粒度，**避免一次 commit 50 个源混在一起**。

### 2.2 状态机

每个源走完一次都必须落到**5 个终态**之一：

| 终态 | 含义 | sources.json 操作 |
|---|---|---|
| **GREEN-promoted** | v3 跑通 ≥3 magnets，2 次不同 query 都过 | `health.status=green, status_detail=ok, magnets_found=<n>, sample_title=...` |
| **YELLOW-tweaked** | v3 跑通但只 1 次能过 / 数量 <3 | 留 yellow，但更新 selectors / requires_browser 等字段，记 progress |
| **DEAD** | 域名 DNS 解析失败 / 持续 connection refused | `health.status=gray, status_detail=expired` |
| **WAF-HARDER** | CloakBrowser 也过不去（不是 thatcdn 类，是 reCaptcha v2/v3 / Arkose） | 留 yellow，加 `notes: "needs_tier2_handler_or_2captcha"`，**不动代码** |
| **SKIP** | 域名内容明显违规 / 用户偏好不要的源 | 不动 |

### 2.3 苦活分批的边界

每完成 5 个源（不论 Pass/Fail）：
1. 停下，跑 `python validate_enum.py`（必须 ALL VALID）
2. 跑 `python -m pytest magnet/tests/crawler_v3 -m 'not integration' -q`（必须 48/48）
3. 把这一批写进 `docs/project-nebula/_phase2_progress.md`（见 §6）
4. 再继续下一批

### 2.4 不许做

- ❌ 不许批量正则改 sources.json（必须逐源人工读 HTML 决定）
- ❌ 不许把多个源合并为一个 commit
- ❌ 不许写新的 helper 脚本除非 Task H 需要（避免膨胀）
- ❌ 不许动 Phase 1 的 4-Tier 框架（`tiers/`、`orchestrator.py`、`detector.py`）
- ❌ 不许动 crawler_v1 / crawler_v2（基线）
- ❌ 不许动 cf-gateway / RN 客户端 / verify-extension（已删）

---

## 3. Task E — WAF 品牌 CloakBrowser 解锁（8 源 / 8 品牌）

### 3.1 单源工作流（每个 E.NN 都按此模板执行）

```
对于每个 E.NN ∈ {E.01 .. E.08}：

[1] 读取 _phase2_targets.json 拿到 origin / search_template
[2] 跑 Tier 0 看不出意外失败（确认这源真的需要 Tier 1）：
      python -m magnet.crawler_v3 search "蜘蛛侠" --origin <host> --limit 5
    期望：tier0_http 失败（curl_cffi 拿到 challenge HTML / 403），自动降级到 tier1_cloak
[3] 看 Tier 1 是否能搞定。两种情况：
    (a) tier1_cloak 直接拿到 ≥3 magnets → 走 [4]
    (b) tier1_cloak 还是 0 results → 用 _debug_probe.py 看 HTML：
          python -m magnet.crawler_v3._debug_probe "<full_search_url>"
        判断是「selector 错」还是「captcha 没过」
        如果 selector 错 → 走 [5]
        如果 captcha 没过 → 标 WAF-HARDER 终态，commit 跳过
[4] 标 requires_browser=true 到 sources.json，跑 2 次不同 query：
      python -m magnet.crawler_v3 search "蜘蛛侠" --origin <host> --limit 5
      python -m magnet.crawler_v3 search "Inception" --origin <host> --limit 5
    都过 ≥3 magnets → GREEN-promoted（更新 health 字段）
    只过 1 次 → YELLOW-tweaked
[5] selector 错的情况：
    用 _debug_probe.py 输出的 HTML 在浏览器里渲染（保存为 .html 文件 in tmp_html/）
    人工读 HTML 找 list_item / title / magnet 的 CSS selector
    填进 sources.json 的 search.parse_metadata.selectors
    回到 [4] 重测
[6] commit（按 §2.1 模板）
[7] 写一行进 _phase2_progress.md
```

### 3.2 Task E 8 源精确清单

| ID | brand | origin | search_template | detail |
|---|---|---|---|---|
| **E.01** | seedhub | https://www.seedhub.cc | `/categories/1/movies/` | parsing_failed |
| **E.02** | 0magnet | https://0magnet.co | `/search?q={query}` | waf |
| **E.03** | 磁力星球 | https://www.cilixingqiu.net | `/?q={query}` | waf |
| **E.04** | 天堂磁力 | https://www.tiantangcili.net | `/?q={query}` | waf |
| **E.05** | 磁力夜 | https://www.ciliri.shop/?ref=eeenav.com | `/?q={query}` | waf |
| **E.06** | bt4gprx | https://bt4gprx.com | `/search?q={query}&p=1&orderby=seeders` | waf |
| **E.07** | magnetcatcat | https://magnetcatcat.com | `/search?q={query}` | waf |
| **E.08** | BTSearch | https://btsearch.org | `/search/{query}` | waf |

### 3.3 E.NN 验收

每个 E.NN commit 必须包含其中之一的证据（粘到 commit message 或 progress.md）：

- **GREEN-promoted**：`tier1_cloak n=<X> in <T>s`，X≥3，**两次不同 query 都过**
- **WAF-HARDER**：完整的 `_debug_probe.py` 输出截图（HTML 长度 + title + magnet count = 0）+ 简短分析（"是 reCaptcha v2，需要 Task K thatcdn-style 逆向"）
- **DEAD**：`curl -I https://<host>` 返回 NXDOMAIN / connection refused 的截图

### 3.4 Task E 总验收

完成 8 个 E.NN 后：

```bash
# 跑批量验证，看实际几个 GREEN
python -m magnet.crawler_v3 verify-yellow "蜘蛛侠" 2>&1 | findstr /C:"PASS" /C:"FAIL"
# 期望：≥5 个新 PASS（含 thatcdn 已有 4 个）
```

填进 `_phase2_progress.md`：「Task E 完成，N/8 GREEN-promoted」

---

## 4. Task F — Selector 失效品牌批量修复（45 源 / 42 品牌）

### 4.1 现实预期

45 个源里大概率：
- **30%（~14 个）真死**（域名失效 / 永久 503） → DEAD 终态
- **30%（~14 个）跳转链镜像**（`?ref=eeenav.com`） → 跟主站合并处理（见 §4.4）
- **40%（~18 个）选择器修复有效** → GREEN-promoted

实际净增 GREEN 品牌：**~15-20 个**（保守估计）。

### 4.2 单源工作流（每个 F.NN 都按此模板）

```
对于每个 F.NN：

[1] 健康存活探测（30s 超时）
      curl -I -m 30 <origin>/
    返回 NXDOMAIN / 连不通 → DEAD 终态，commit 跳过
    返回 200/3xx → 继续
[2] 跑现有 selector 看是不是 smart_list 兜底就能解决
      python -m magnet.crawler_v3 search "Inception" --origin <host> --limit 5
    n≥3 → 啥都不改，直接更新 health 走 GREEN-promoted（说明上次健康检查时点抖动）
    n<3 → 继续
[3] 探针拿真实搜索页 HTML
      python -m magnet.crawler_v3._debug_probe "<origin><search_template_with_query>" > tmp_html/F<NN>.html
[4] 人工读 HTML：
    - 找列表容器（典型 class：item / list-item / row / tr）
    - 找标题链接（a[href*=/detail/], h3 > a）
    - 找 magnet（a[href^=magnet:]）
    - 写下 4 个 CSS selector 候选
[5] 改 sources.json 的 search.parse_metadata.selectors，跑 2 次：
      python -m magnet.crawler_v3 search "蜘蛛侠" --origin <host> --limit 5
      python -m magnet.crawler_v3 search "Inception" --origin <host> --limit 5
    都过 ≥3 magnets → GREEN-promoted
    只过 1 次 → YELLOW-tweaked + 留 selector 改动
    都不过 → 走 [6]
[6] 看是不是详情页才有 magnet（v1 已知模式）：
    如果列表页只有 /detail/<id> 链接而没 magnet → 配 detail 选择器：
      sources.json: search.detail.selectors.magnet = "a[href^=magnet:]"
    再走 [5]
    如果详情页也没 magnet → 标 DEAD 或 SKIP
[7] commit + progress
```

### 4.3 Task F 45 源精确清单（按品牌集中度排序）

> **注意**：标 `[mirror]` 的源是某个已存在 yellow-only 品牌的镜像，**做完主站后顺手处理**。
> 标 `[?ref=eeenav]` 的源全是导航站联盟的跳转页，结构都一样，**先做 1 个摸清模板再批量套**。

| ID | brand | origin | 备注 |
|---|---|---|---|
| F.01 | btso | https://btso.cc | |
| F.02 | btbtt | https://btbtt12.com | |
| F.03 | animetime | https://animetime.cc/ | |
| F.04 | BT联盟 | https://btlm.work | |
| F.05 | 搜番 | https://sofan.run | |
| F.06 | BT蚂蚁磁力 | https://btmayi.top | |
| F.07 | 磁力多 | https://ciliduo.cyou | |
| F.08 | 磁力星球 | https://cilixingqiu.de | [mirror of E.03] |
| F.09 | BTHaHa | https://bthaha.top | |
| F.10 | 磁力管家 | http://www.ciliguanjia.buzz | |
| F.11 | BTFOX | http://btfox.cyou | |
| F.12 | 找磁力 0Mag | https://1000mag.xyz | |
| F.13 | U3C3 | https://u3c3.org | 老牌成人 BT |
| F.14 | 磁力王 | http://movih.com | |
| F.15 | Pirate Bay 海盗湾 | http://pirateproxy.tube | |
| F.16 | 磁力树 | http://bthook.club | |
| F.17 | 磁力搜索神器 | https://cilishenqi.me | |
| F.18 | BT电影天堂 | https://www.btbtt10.com | |
| F.19 | BT搜索 | https://btcherries.xyz | |
| F.20 | 磁力窝 | https://ciliwo.com | |
| F.21 | BT吃力 | http://jukan.xyz | |
| F.22 | 磁力海 | https://uuyter56der.xyz | |
| F.23 | 快马搜索 | http://www.km153.xyz | |
| F.24 | 磁力星 | http://cixing.org | |
| F.25 | BTSOW | https://btsow.icu/?go | 老牌中文 BT |
| F.26 | 磁力蜘蛛 | https://btmovi.icu | |
| F.27 | 磁力口袋 | https://clkd.com | |
| F.28 | BTMET | http://gobtmet.com | |
| F.29 | 52BT | http://529952.xyz | |
| F.30 | 磁力大全 | https://www.cilihezi.cn | |
| F.31 | bthaha | http://wangzhi.men/bthaha | [mirror of F.09] |
| F.32 | 博世 | http://berrl.com | |
| F.33 | 磁力宅 | https://www.cilizhai.com | |
| F.34 | 磁力狐 | https://bt43.foxs.vip | |
| F.35 | 磁力熊猫 | https://soxiongmao.top | [mirror, thatcdn] **直接加 tier_override** |
| F.36 | 磁力链 | https://cililian.one | |
| F.37 | 无极磁链 | https://0cili.nl | |
| F.38 | 磁力多 | https://ru.cilido.top/?ref=eeenav.com | [mirror of F.07, ?ref=eeenav] |
| F.39 | 搜番 | https://mr.sofan1.cc/?ref=eeenav.com | [mirror of F.05, ?ref=eeenav] |
| F.40 | 91BT | https://911173.xyz/?ref=eeenav.com | [?ref=eeenav] |
| F.41 | 吴签磁力 | https://wuqianyx.top/?ref=eeenav.com | [mirror, thatcdn] **直接加 tier_override** |
| F.42 | BT1207 | https://bt1207yx.top/?ref=eeenav.com | [?ref=eeenav, possibly thatcdn] |
| F.43 | 磁力柠檬 | https://lemonzc.top/?ref=eeenav.com | [mirror, thatcdn] **直接加 tier_override** |
| F.44 | 无极磁链 | https://wuji.me/?ref=eeenav.com | [mirror of F.37, ?ref=eeenav] |
| F.45 | 磁力发 | https://www.jzcilifa1.shop/?ref=eeenav.com | [?ref=eeenav] |

### 4.4 ?ref=eeenav 子任务集中处理

`?ref=eeenav.com` 的 ~10 个源全是同一个导航站联盟生成的跳转页，模板高度雷同。**先做一个**（如 F.40 91BT）摸清模板：
1. 跳转后落地页是什么 URL？
2. 落地页的 search 结构？
3. 是不是又跳到 thatcdn 平台？

写一段 30-50 行的笔记进 `_phase2_progress.md` 「§eeenav 模板分析」段，再批量套到 F.38 / F.39 / F.40 / F.42 / F.44 / F.45。

如果落地后是 thatcdn 平台 → 直接 `tier_override: tier2_handler/thatcdn`，零代码。

### 4.5 已知是 thatcdn 镜像的源（F.35 / F.41 / F.43）

直接 `tier_override: tier2_handler/thatcdn`，**不需要碰 selector**，跑一次 verify 就能升 GREEN。这 3 个先做（最快回报）。

---

## 5. Task G — sources.json `site.brand` 字段补全（间接价值）

### 5.1 现状

只有 50% 源有 `site.brand`，导致 search 端无法做品牌级去重 / 故障切换 / 多样性展示。

### 5.2 步骤

**[G.1]** 写脚本 `magnet/_infer_brands.py`（一次性工具，跑完删）：
- 加载 sources.json
- 对每个无 brand 的源，根据 `site.name` + `origin` host root 推断 brand
- 输出建议表（CSV / JSON）：`origin, current_brand, suggested_brand`

**[G.2]** 人工 review（240 源约 1h，可粗看）：
- 标记是否接受推断
- 把 thepiratebay 12 个域名都归到 brand="The Pirate Bay"
- 把磁力宝 24 个域名都归到 brand="磁力宝"
- thatcdn 系列归到各自原品牌（磁力熊猫 / 磁力柠檬 / 磁力吴签 / 磁力老王）

**[G.3]** 一次性 batch 写回 sources.json，**单 commit**：
```
chore(sources): backfill site.brand for 240 sources

Coverage: 50% -> 100%
Inferred from origin host-root + site.name patterns.
Reviewed manually for thepiratebay / 磁力宝 / thatcdn families.
```

**[G.4]** 在 `validate_enum.py` 加 `site.brand` 必填检查（**软约束**：缺 brand 不 fail，但 print warning）

### 5.3 验收

```bash
python -c "import json; d=json.load(open('sources.json','r',encoding='utf-8')); rules=d['rulesets'][0]['rules']; print(f'brand coverage: {sum(1 for r in rules if (r.get(\"site\") or {}).get(\"brand\"))}/{len(rules)}')"
# 期望：240/240
```

---

## 6. Task H — 验证基础设施增强（小工具）

### 6.1 新增 CLI 子命令 `recheck`

```python
# magnet/crawler_v3/cli.py 增加：
def cmd_recheck(args):
    """对 status=yellow 的源跑一次 v3，自动升级到 green if 通过."""
    # 默认 dry-run（只 print 不写）
    # --commit 才真正改 sources.json
    pass
```

用法：
```bash
python -m magnet.crawler_v3 recheck --query "蜘蛛侠"  # dry-run
python -m magnet.crawler_v3 recheck --query "蜘蛛侠" --commit  # 真改
```

### 6.2 新增 CLI 子命令 `brand-stats`

```python
def cmd_brand_stats(args):
    """打印当前 brand 级覆盖统计."""
    # 输出：
    # Total brands: N
    # Green-covered: G
    # Yellow-only: Y
    # Coverage: G/(G+Y) * 100%
```

### 6.3 不做的部分

- 不做 health_check 的 cron 改造（C.1 已经接 v3）
- 不做 batch_heal_yellow（写完 Task F 再决定是否需要）

---

## 7. Task I — 文档归档与最终交付

### 7.1 创建 `docs/project-nebula/CRAWLER-V3-PHASE-1-ARCHIVE.md`

- 把 Phase 1 完成的内容（v1/v2 → v3 4-Tier、thatcdn handler、web Tier 1 迁移）做一份归档摘要 ~150 行
- 这样 `CRAWLER-V3-PHASE-2-PLAN.md`（本文档）专注 Phase 2，不冗余

### 7.2 Phase 2 结束后，本文档增加 §8 完成报告

```markdown
## 8. Phase 2 完成报告（2026-XX-XX）

### Task E 结果（8 源）
| ID | origin | 终态 | brand 解锁 |
|...|

### Task F 结果（45 源）
| ID | origin | 终态 | brand 解锁 |
|...|

### Task G 结果
- Brand 字段覆盖：50% → 100%

### 净增独立品牌
- Phase 1 后：48
- Phase 2 后：N
- ΔBrand：+M

### tag
git tag crawler-v3-phase2-complete
```

### 7.3 更新 DEV-LOG（每次 commit 都更新顶部最新版本块的「本次范围」段，而不是单独建 Phase 2 入口）

---

## 8. Definition of Done（Phase 2 完成判定）

跑下列**全过**才算 Phase 2 完成：

```bash
# [DoD.1] 测试不破
pytest magnet/tests/crawler_v3 -m 'not integration' -q
# 期望：48/48 passed (or more if 加了新测试)

# [DoD.2] 枚举 OK
python validate_enum.py | findstr "ALL VALID"

# [DoD.3] 品牌统计达标
python -m magnet.crawler_v3 brand-stats
# 期望：Green-covered ≥ 65 brands (从 48 涨 ≥17 个)

# [DoD.4] verify-yellow 大幅改善
python -m magnet.crawler_v3 verify-yellow "蜘蛛侠"
# 期望：≥20 个 PASS（含 Phase 1 的 4 个 thatcdn）

# [DoD.5] _phase2_progress.md 完整
findstr /C:"E." /C:"F." docs/project-nebula/_phase2_progress.md | Measure-Object -Line
# 期望：≥53 行

# [DoD.6] commits 一对一
git log --since='2026-05-29' --oneline | findstr /C:"phase2" | Measure-Object -Line
# 期望：≥45 行（45 + 部分跳过的也 commit）
```

全过 → `git tag crawler-v3-phase2-complete` 并填本文 §7.2 完成报告。

---

## 9. Decision Tree（Agent 模糊场景）

```
卡住？
├─ tier1_cloak 拿到 HTML 但 0 magnet
│   └─ 是 selector 错（80%）→ 用 _debug_probe.py 看 HTML，人工找
│   └─ 是 detail 二跳（15%）→ 配 search.detail.selectors.magnet
│   └─ 是 captcha 没过（5%）→ 标 WAF-HARDER，commit 跳过
│
├─ 单源耗 >20 分钟还没结论
│   └─ 标 SKIP，progress.md 记原因，下个源
│
├─ sources.json schema 不知道怎么填
│   └─ 找一个已 GREEN 的同类型源参考（如 fitgirl-repacks.site）
│
├─ 测试失败
│   └─ 不许 weakening 测试断言；先回滚最近改动定位再继续
│
└─ 真不确定
    └─ 在 commit message 写 RFC: 假设 + 选择，继续推进，等 review
```

---

## 10. 起点

**第一步**：读 `docs/project-nebula/_phase2_targets.json`。

**第二步**：从 **Task F.35 / F.41 / F.43**（thatcdn 镜像 3 个）开始 — 这 3 个只需要 `tier_override` 配置，5 分钟搞定 3 个新 GREEN 品牌（不对，这 3 个其实是已有品牌的镜像，但能让原品牌的镜像数从 1 → 2，提升可靠性）。

**第三步**：从 **E.01 → E.08** 顺序做（WAF 类，标 requires_browser 即可大概率通过）。

**第四步**：**F.40（91BT）** 摸清 ?ref=eeenav 模板。

**第五步**：F.01 → F.45 顺序做，跳过已处理的镜像。

**第六步**：Task G + H + I 收尾。

---

## 11. 不许触碰的清单

- `magnet/crawler/`、`magnet/crawler_v2/`（基线）
- `magnet/crawler_v3/orchestrator.py` / `detector.py` / `tiers/base.py`（核心架构）
- `magnet/crawler_v3/handlers/thatcdn.py`（已实现，除非发现 bug）
- `cf-gateway/`、`magnetgoogo-app/src/components/VerifyWebView.tsx`
- `web/src/core/browser-engine.ts`（Phase 1 已迁移）
- `magnet/cloak_yellow_verify.py`（保留 deprecation banner，2026-07-01 才能删）
- sources.json 的 `health.status` / `status_detail` 枚举（见 `validate_enum.py`）

---

**最终签名**：完成所有任务后，在文末加 `Phase 2 implemented by <agent-name> on <date>`，并报告净增独立品牌数。
