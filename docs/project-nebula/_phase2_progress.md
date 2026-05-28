# Phase 2 进度跟踪

> Agent 在执行 `CRAWLER-V3-PHASE-2-PLAN.md` 时**逐源**填表。每完成一个源（不论 PASS/FAIL/SKIP）必须在此处加一行 + 单独 commit。

## Task E — WAF 品牌 CloakBrowser 解锁（8 源）

| ID | brand | origin | 终态 | 用时 | n_magnets | 备注 / 关键发现 |
|---|---|---|---|---|---|---|
| E.01 | seedhub | https://www.seedhub.cc | WAF-HARDER | 0 | CF 403, CloakBrowser 0 results, search_template 无 {query} | |
| E.02 | 0magnet | https://0magnet.co | DEAD | 0 | domain expired, for sale on porkbun.com | |
| E.03 | 磁力星球 | https://www.cilixingqiu.net | WAF-HARDER | 0 | CF 403, CloakBrowser 42s 0 results | |
| E.04 | 天堂磁力 | https://www.tiantangcili.net | WAF-HARDER | 0 | CF 403, CloakBrowser 43s 0 results | |
| E.05 | 磁力夜 | https://www.ciliri.shop | WAF-HARDER | 0 | CF 403 | |
| E.06 | bt4gprx | https://bt4gprx.com | DEAD | 0 | 404 on search endpoint | |
| E.07 | magnetcatcat | https://magnetcatcat.com | WAF-HARDER | 0 | CF 403 | |
| E.08 | BTSearch | https://btsearch.org | DEAD | 0 | redirects to btsearch.pl via tracking URL | |

**Task E 小结**（完成后填）：
- N/8 GREEN-promoted
- 净增独立品牌：N

## Task F — Selector 失效品牌批量修复（45 源）

> 终态枚举：`GREEN-promoted` / `YELLOW-tweaked` / `DEAD` / `WAF-HARDER` / `SKIP`
> 优先做：**F.35 / F.41 / F.43**（thatcdn 镜像）→ **F.40**（?ref=eeenav 模板分析）→ 其它

| ID | brand | origin | 终态 | n_magnets | 备注 |
|---|---|---|---|---|---|
| F.01 | btso | https://btso.cc | _pending_ | | |
| F.02 | btbtt | https://btbtt12.com | DEAD | 0 | connection timeout, unreachable |
| F.03 | animetime | https://animetime.cc | DEAD | 0 | connection timeout, unreachable |
| F.04 | BT联盟 | https://btlm.work | _pending_ | | |
| F.05 | 搜番 | https://sofan.run | _pending_ | | |
| F.06 | BT蚂蚁磁力 | https://btmayi.top | _pending_ | | |
| F.07 | 磁力多 | https://ciliduo.cyou | _pending_ | | |
| F.08 | 磁力星球(mirror) | https://cilixingqiu.de | _pending_ | | mirror of E.03 |
| F.09 | BTHaHa | https://bthaha.top | _pending_ | | |
| F.10 | 磁力管家 | http://www.ciliguanjia.buzz | _pending_ | | |
| F.11 | BTFOX | http://btfox.cyou | _pending_ | | |
| F.12 | 找磁力 0Mag | https://1000mag.xyz | _pending_ | | |
| F.13 | U3C3 | https://u3c3.org | _pending_ | | 老牌 |
| F.14 | 磁力王 | http://movih.com | _pending_ | | |
| F.15 | Pirate Bay 海盗湾 | http://pirateproxy.tube | _pending_ | | |
| F.16 | 磁力树 | http://bthook.club | _pending_ | | |
| F.17 | 磁力搜索神器 | https://cilishenqi.me | _pending_ | | |
| F.18 | BT电影天堂 | https://www.btbtt10.com | _pending_ | | |
| F.19 | BT搜索 | https://btcherries.xyz | _pending_ | | |
| F.20 | 磁力窝 | https://ciliwo.com | _pending_ | | |
| F.21 | BT吃力 | http://jukan.xyz | _pending_ | | |
| F.22 | 磁力海 | https://uuyter56der.xyz | _pending_ | | |
| F.23 | 快马搜索 | http://www.km153.xyz | _pending_ | | |
| F.24 | 磁力星 | http://cixing.org | _pending_ | | |
| F.25 | BTSOW | https://btsow.icu | _pending_ | | 老牌 |
| F.26 | 磁力蜘蛛 | https://btmovi.icu | _pending_ | | |
| F.27 | 磁力口袋 | https://clkd.com | _pending_ | | |
| F.28 | BTMET | http://gobtmet.com | _pending_ | | |
| F.29 | 52BT | http://529952.xyz | _pending_ | | |
| F.30 | 磁力大全 | https://www.cilihezi.cn | _pending_ | | |
| F.31 | bthaha(mirror) | http://wangzhi.men/bthaha | _pending_ | | mirror of F.09 |
| F.32 | 博世 | http://berrl.com | _pending_ | | |
| F.33 | 磁力宅 | https://www.cilizhai.com | _pending_ | | |
| F.34 | 磁力狐 | https://bt43.foxs.vip | _pending_ | | |
| F.35 | 磁力熊猫(mirror) | https://soxiongmao.top | GREEN-promoted | 5 | **thatcdn — tier_override added** |
| F.36 | 磁力链 | https://cililian.one | _pending_ | | |
| F.37 | 无极磁链 | https://0cili.nl | _pending_ | | |
| F.38 | 磁力多(eeenav) | https://ru.cilido.top | _pending_ | | mirror of F.07 |
| F.39 | 搜番(eeenav) | https://mr.sofan1.cc | _pending_ | | mirror of F.05 |
| F.40 | 91BT(eeenav) | https://911173.xyz | _pending_ | | **eeenav 模板分析锚点** |
| F.41 | 吴签磁力(mirror) | https://wuqianyx.top | GREEN-promoted | 5 | **thatcdn — tier_override added** |
| F.42 | BT1207(eeenav) | https://bt1207yx.top | _pending_ | | possibly thatcdn |
| F.43 | 磁力柠檬(mirror) | https://lemonzc.top | GREEN-promoted | 5 | **thatcdn — tier_override added** |
| F.44 | 无极磁链(eeenav) | https://wuji.me | _pending_ | | mirror of F.37 |
| F.45 | 磁力发(eeenav) | https://www.jzcilifa1.shop | _pending_ | | |

**Task F 小结**（完成后填）：
- N/45 GREEN-promoted
- M DEAD
- K WAF-HARDER（提报 Task K thatcdn-style 逆向候选）
- 净增独立品牌：N

## §eeenav 模板分析（做完 F.40 后填这里）

落地 URL：
真实搜索结构：
是否 thatcdn：
处理策略：

## Task G — brand 字段补全

- [ ] 写 `_infer_brands.py`
- [ ] 输出建议 CSV
- [ ] 人工 review
- [ ] batch 写回 sources.json
- [ ] validate_enum.py 加 brand 软约束

最终 brand 覆盖：__/240

## Task H — CLI 增强

- [ ] `recheck` 子命令
- [ ] `brand-stats` 子命令

## Phase 2 总结（全完成后填）

- 起点 GREEN 品牌数：48
- 终点 GREEN 品牌数：__
- ΔBrand：__
- 总耗时：__h
- tag：`crawler-v3-phase2-complete` ✅/⏸
