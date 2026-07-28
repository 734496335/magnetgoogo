# rating_resolver 目标（验收门禁）

## 北极星

独立可部署的评分爬虫工具，能**稳定拿到**豆瓣 / IMDb / 烂番茄 / Bangumi 等站点（或第三方等价源）在某个时期的评分。

## 明确不追求

- 不要求实时最新分
- 不要求片名 100% 精确匹配（有分即可，报告里带 matched_title）
- 一期不写回 movie_items / Feed

## 达标条件（全部满足才算 GOAL_MATCHED）

1. **独立入口**：`python -m magnet.rating_resolver lookup "片名" [--year YYYY]` 可运行
2. **至少 3 个源通道**在代码中可调用：douban / imdb（含 cinemeta 补偿）/ bangumi；rt 尽力 + 补偿
3. **金样例**（允许网络）：
   - `肖申克的救赎` 或 `The Shawshank Redemption` → 至少一个 `status=ok` 且有 `score`
   - `Inception` → 至少一个 `status=ok` 且有 `score`
4. **输出 JSON** 含 `ratings` 与 `display`（可用于后续落库）
5. **批量只读**：`enrich-scan --titles-file` 或 `--db` 能产出报告文件
6. **缓存**：同 query 重复调用命中本地 cache，不强制每次打源站
7. **失败可观测**：源失败时 `status` 为 `blocked|error|no_match`，不崩溃整次 lookup

## 验证命令

```bash
cd D:\lpproduct\magnet
python -m magnet.rating_resolver self-check
# exit 0 且打印 GOAL_MATCHED=true
```
