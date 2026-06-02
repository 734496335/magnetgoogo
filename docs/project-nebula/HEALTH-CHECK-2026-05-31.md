# 源健康检查报告 — 2026-05-31

> 测试工具：`python magnet/health_check.py --include-gray --workers 8`
> 测试时间：2026-05-31
> 网络环境：HTTP_PROXY=http://127.0.0.1:7897 (Clash Verge 混合代理)
> 结果文件：`health_check_report_proxy2.json`
> **注意**：本次仅记录，未写回 sources.json

---

## 总览

| 指标 | 数值 |
|---|---|
| 总源数 | 239 |
| GREEN | 56 (23%) |
| YELLOW | 14 (6%) |
| GRAY | 158 (66%) |
| None (custom handler) | 11 (5%) |
| 总磁力数 | 1058 |

## 失败原因分布

| 原因 | 数量 |
|---|---|
| parsing_failed | 80 |
| unreachable | 48 |
| 404 | 35 |
| waf | 8 |
| None (skip) | 11 |

## 状态变迁（对比 sources.json 原始状态）

| 变迁 | 数量 |
|---|---|
| green -> green | 49 |
| gray -> gray | 79 |
| **green -> gray** | **42** |
| yellow -> gray | 36 |
| green -> None | 10 |
| yellow -> yellow | 8 |
| gray -> yellow | 4 |
| green -> yellow | 3 |
| **gray -> green** | **6** |
| yellow -> green | 1 |
| gray -> None | 1 |

## 与无代理测试对比

使用 `HTTP_PROXY=http://127.0.0.1:7897` 显式走代理后，3 个之前 unreachable 的源恢复：

| 源 | 无代理 | 有代理 | 说明 |
|---|---|---|---|
| 磁力搜搜(cc) | unreachable (timeout) | green (ok) | GFW 解锁 |
| 磁力搜搜(co) | unreachable (timeout) | green (ok) | GFW 解锁 |
| 磁力链接(cililianjie) | unreachable (timeout) | green (ok) | GFW 解锁 |

GREEN 53 -> 56，unreachable 51 -> 48。

## 新升 GREEN（6 个）

| 源 | 原状态 | 磁力数 | 说明 |
|---|---|---|---|
| thepiratebay.baby | gray | 20 | 新镜像 |
| seedhub.cc | yellow | 0 | detail-follow |
| 0cili.org | gray | 0 | detail-follow |
| 0cili.com | gray | 0 | detail-follow |
| 磁力搜搜(cc) | gray | 0 | proxy 恢复 |
| 磁力搜搜(co) | gray | 0 | proxy 恢复 |

## 回归 GREEN->GRAY（42 个）

### 404 域名失效（24 个，不可逆）

clb1.xyz, clb12.top, clb13.cc, clb13.top, clb13.xyz, clb15.top, clb16.top, clb17.top, clb17.xyz, clb18.top, clb19.top, clb2.cc, clb20.top, clb3.me, clb6.cc, clb6.me, nyaa.si, sukebei.nyaa.si, 磁力宝(clb21-clb26) x6

### parsing_failed 选择器失效（13 个，可修）

| 源 | 详情 |
|---|---|
| 6v520.com | page too short (37 chars) |
| bt43.foxs.vip | page too short (18 chars) |
| btsow.icu | page too short (366 chars) |
| clb.biz | page too short (0 chars) |
| 磁力天堂(cltt03) | page too short (71 chars) |
| 磁力猫(clm51,53,54,56,57,58,59) x7 | page too short (31 chars) |
| 阿狸搜 | page too short (0 chars) |

### unreachable（4 个）

| 源 | 详情 |
|---|---|
| BTDigg | HTTP 429 |
| 磁力狗(clg54) | connection error |
| bt1207yx.top | variable reference error (health_check bug) |
| 磁力链接(cililianjie) | ~~timeout~~ -> proxy 下已恢复为 green |

### WAF（1 个）

| 源 | 详情 |
|---|---|
| UIndex | HTTP 403 |

## WAF 源清单（8 个）

| 源 | 原状态 | 新状态 |
|---|---|---|
| laoniubt.com | gray | gray |
| cilixingqiu.net | yellow | gray |
| cilimao.lol | yellow | gray |
| tiantangcili.net | yellow | gray |
| ciliri.shop | yellow | gray |
| BT4G | gray | gray |
| 磁力猫 (magnetcatcat) | yellow | gray |
| UIndex | green | gray |

## GREEN 源详情（56 个）

### 高产出（>=10 magnets，39 个）

| 源 | 磁力数 | 延迟 |
|---|---|---|
| mirrorbay.org | 100 | 1037ms |
| thepiratebay.isproxy.online | 100 | 1052ms |
| thepiratebay.isproxy.pics | 100 | 1257ms |
| thepiratebay.isproxy.space | 100 | 137ms |
| Mikanani | 20 | 3025ms |
| Nyaa(mirror) | 20 | 1216ms |
| animetosho.org | 20 | 1324ms |
| thepiratebay.xyz | 20 | 1503ms |
| tpb.party | 20 | 1119ms |
| thepiratebay10.org | 20 | 2431ms |
| thepiratebay0.org | 20 | 1284ms |
| thepiratebay.baby | 20 | 1349ms |
| thepiratebay.bond | 20 | 857ms |
| piratebay.party | 20 | 1134ms |
| thepiratebay.zone | 20 | 1412ms |
| piratebay.live | 20 | 1144ms |
| pirateproxy.live | 20 | 1413ms |
| thepiratebay.rocks | 20 | 1442ms |
| piratebayproxy.live | 20 | 1197ms |
| pirate-proxy.thepiratebay.rocks | 20 | 1452ms |
| pirateproxylive.org | 20 | 785ms |
| thepiratebay.party | 20 | 7135ms |
| thepiratebay10.xyz | 20 | 846ms |
| thepiratebay11.com | 20 | 891ms |
| thepiratebay7.com | 20 | 1041ms |
| thepiratebay10.info | 20 | 1114ms |
| rutor.info | 20 | 1426ms |
| rutor.is | 20 | 1543ms |
| u3c3.com | 20 | 1199ms |
| 動漫花園 | 20 | 1621ms |
| 動漫花園(mirror) | 20 | 1993ms |
| 磁力妹妹(CLMM) | 20 | 1623ms |
| tokyotosho.info | 20 | 8603ms |
| tokyotosho.org | 20 | 11817ms |
| Knaben | 19 | 2461ms |
| bitsearch.to | 18 | 2847ms |
| magnetdl.app | 10 | 2238ms |
| magnetdl.pro | 10 | 2195ms |

### 低产出（1-9 magnets，1 个）

| 源 | 磁力数 | 延迟 |
|---|---|---|
| fitgirl-repacks.site | 1 | 1597ms |

### detail-follow 模式（磁力在详情页，16 个）

| 源 | 详情链接数 | 延迟 |
|---|---|---|
| seedhub.cc | 150 | 517ms |
| 0cili.nl | 91 | — |
| 0cili.org | 91 | — |
| 0cili.com | 91 | — |
| ACG.rip | 30 | — |
| 种子吧 | 27 | — |
| 种子吧(zzb04) | 15 | — |
| 种子吧(zzb05) | 15 | — |
| 种子吧(zzb06) | 15 | — |
| 种子吧(zzb07) | 15 | — |
| 种子吧(zhongziba) | 15 | — |
| 种子吧(seed8) | 15 | — |
| yts.do | 17 | — |
| clb12.xyz | 10 | — |
| 磁力搜搜(cc) | — | — |
| 磁力搜搜(co) | — | — |

## 可修复项优先级

### P0 — parsing_failed 回归（13 个，选择器可修）

btsow.icu、bt43.foxs.vip、6v520.com、clb.biz、磁力天堂(cltt03)、磁力猫 7 个镜像、阿狸搜

### P1 — WAF 源（8 个，需 Phase 3 Cookie+VerifyWebView）

cilixingqiu.net、tiantangcili.net、ciliri.shop、cilimao.lol、magnetcatcat、UIndex、laoniubt.com、BT4G

### P2 — unreachable（3 个）

BTDigg(429)、磁力狗、bt1207yx.top(health_check bug)

### P3 — 404 域名失效（24 个，不可逆，需域名复活）

磁力宝 clb 系列 16 个 + nyaa.si/sukebei + 磁力宝 clb21-26
