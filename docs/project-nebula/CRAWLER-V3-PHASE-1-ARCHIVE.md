# crawler_v3 Phase 1 归档（2026-05-28 完成）

> 历史归档。最新进展见 `CRAWLER-V3-PHASE-2-PLAN.md`。
> tag：`pre-crawler-v3` (起点) → `crawler-v3-stable` (Phase 1 终点)

## 完成时间线

| 日期 | 里程碑 |
|---|---|
| 2026-05-28 18:30 | tag `pre-crawler-v3` 备份 v1+v2 |
| 2026-05-28 18:45 | 4-Tier 架构骨架 + 探针落地（commit `7c4b03b`）|
| 2026-05-28 19:14 | Phase 1 P0–P4 实测 + thatcdn 重新定性（commit `700d046`）|
| 2026-05-28 19:23 | Phase 1 工单文档（commit `6afd87c`）|
| 2026-05-28 20:30 | Phase 1 全部 Task A/B/C/D 完成 + tag `crawler-v3-stable`（commit `1802c9a`）|

## Phase 1 交付物

### 1. 4-Tier 统一架构

```
orchestrator.search(source, query)
  ↓ detector.classify(source) 决定顺序
  ├── Tier 0 HTTP        curl_cffi + Chrome TLS 指纹（90% 普通源）
  ├── Tier 1 Cloak       CloakBrowser headless + humanize（CF JS / Turnstile / 通用 SPA）
  ├── Tier 2 Handler     hello_js_reverse_skill 产出的纯 Python 算法（共享平台 anti-bot）
  └── Tier 3 Stub        VerifyWebView（移动端兜底，Python 端 stub）
```

文件树：
```
magnet/crawler_v3/
├── __init__.py / __main__.py / cli.py
├── config.py / detector.py / orchestrator.py
├── tiers/
│   ├── base.py            # Tier ABC + SearchResult + TierError
│   ├── tier0_http.py      # curl_cffi + httpx fallback
│   ├── tier1_cloak.py     # CloakBrowser 0.3.31 + humanize + smart polling
│   ├── tier2_handler.py   # 注册表 + 自动加载
│   └── tier3_stub.py      # 移动端占位
├── handlers/
│   ├── thatcdn.py         # thatcdn 平台逆向（220 LOC，4 yellow 源解锁）
│   ├── _example.py        # skeleton
│   └── README.md          # JS 逆向工作流
├── parser/__init__.py     # smart_list 复用 + 选择器路径
├── _debug_probe.py        # CloakBrowser HTML dump 工具
└── README.md
```

### 2. thatcdn 平台逆向（重大认知翻新）

**误判修正**：6 个月一直把 thatcdn 当 Cloudflare Turnstile，实际是平台自定义 anti-bot。

**逆向产出**（`magnet/crawler_v3/handlers/thatcdn.py`）：
- captcha challenge：`/anti/recaptcha/v4/{gen,verify}` 双段 API
- 导航站机制：`<meta name="rdata">` base64 反转 JSON 解码（xiongmaogb.top → xiongmaoqv.top）
- detail 二跳：搜索结果只给 detail 链接，需要二跳拿 magnet
- TLS 指纹：curl_cffi `chrome124` + 完整 Referer 链

4/4 yellow 源验证：
| 源 | 结果 |
|---|---|
| xiongmaogb.top 磁力熊猫 | 5 magnets ~10s ✅ |
| lemonun.top 磁力柠檬 | 5 magnets ✅ |
| wuqianso.org 吴签磁力 | 5 magnets ✅ |
| laowangzo.top 老王磁力 | 5 magnets ✅ |

### 3. web `route.ts` Tier 1 迁移

- Playwright + CDP → CloakBrowser `launch({ humanize: true })`
- `interactiveVerify`：execFile + verify-extension（MV3 cookie bridge）→ headed CloakBrowser 自动通过
- `CLOAK_FORCE_HEADLESS=1` 环境变量统一切 headless（生产侧用）
- 删除 `web/verify-extension/` 整目录（3 文件 7.8KB）
- 7 个自定义 handler（javbus/6v520/meijumi/yhg/zhongzidi/rarbggo/rrjav）保留不动

### 4. health_check 迁移

- `magnet/health_check.py::_probe_with_v3()` 集成
- yellow + tier_override 源走 v3 orchestrator
- `magnet/cloak_yellow_verify.py` 加 `DeprecationWarning`（2026-07-01 删除）

### 5. 回归测试

48 单测，0.39s 完成：
- `test_orchestrator.py`：TierError fallback 链 + classify 路由
- `test_tier0_http.py`：mock 200/403/429/timeout + anti-bot 检测
- `handlers/test_thatcdn.py`：rdata 正则 + magnet 正则 + 解析 + captcha 逻辑
- `.github/workflows/test-crawler-v3.yml`：CI on push/PR

### 6. sources.json 修正

- `clttone.top`：`request_template ?word=` → `?kw=`（form input name 是 `kw`）
- 4 个 thatcdn yellow 源：`tier_override: tier2_handler/thatcdn`

## §8 Definition of Done — 7/7 通过

| # | 验收项 | 实测结果 |
|---|---|---|
| 8.1 | classify yellow | 69 行 plan |
| 8.2 | Tier 0 uindex | 5 magnets ~1s |
| 8.3 | thatcdn 4/4 | 全过，5 magnets each |
| 8.4 | web build + verify-extension 删除 | build OK |
| 8.5 | health_check v3 | _probe_with_v3 集成 |
| 8.6 | pytest | 48/48 in 0.39s |
| 8.7 | validate_enum | ALL VALID |

## 关键学到的（沉淀给 Phase 2 用）

1. **不要相信"看起来是 CF Turnstile"** — 先用探针真测，很多自定义 anti-bot 模板长得跟 CF 像
2. **导航站和真站要分开** — `<meta name="rdata">` 这种藏起来的真域名很常见
3. **CloakBrowser 0.3.31 + humanize=True** 对 CF 类标准 challenge 几乎 100% 通过；对自定义 anti-bot 0% 通过
4. **Tier 0 用 curl_cffi 比 v1 fetch 快 5-10x**（TLS 指纹一次配置长期受益）
5. **AI Agent 接力可行**：Plan 文档结构（DoD + Don't-touch + Decision tree）是关键
6. **品牌覆盖才是真指标** — 101 green 源 ≠ 101 个独立资源池（很多是镜像）

---

Phase 1 implemented by Claude Opus 4.7 + MiMo v2.5 Pro on 2026-05-28.
