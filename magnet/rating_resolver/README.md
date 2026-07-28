# rating_resolver — 独立影视评分爬虫

## 目标

稳定获取豆瓣 / IMDb / 烂番茄 / Bangumi 等在**某一时期**的评分。
不要求实时、不要求片名完美匹配；有分即可。

## 依赖

- Python 3.10+
- `curl_cffi`（优先）或 `requests`
- 可选环境变量：
  - `OMDB_API_KEY` — 烂番茄/IMDb 补偿
  - `HTTP_PROXY` / `HTTPS_PROXY`
  - `RATING_MIN_INTERVAL` — 每 host 最小间隔秒（默认 0.7）

## 用法

```bash
cd D:\lpproduct\magnet   # 或把 magnet 包加入 PYTHONPATH

# 单查
python -m magnet.rating_resolver lookup "肖申克的救赎" --year 1994
python -m magnet.rating_resolver lookup "Inception" --year 2010 --imdb-id tt1375666

# 指定源
python -m magnet.rating_resolver lookup "群体" --sources douban,imdb,bangumi

# 只读扫库缺分
python -m magnet.rating_resolver enrich-scan \
  --db data/resource_index/sixv_latest_50.db \
  --limit 20 \
  -o data/rating_cache/scan_report.json

# 验收门禁
python -m magnet.rating_resolver self-check --no-cache
```

## 源策略

| 源 | 主路径 | 补偿 |
|----|--------|------|
| douban | suggest + subject 页 | — |
| imdb | **Cinemeta** 第三方快照 | IMDb 页面刮削 |
| rotten_tomatoes | OMDb（有 key） | RT 搜索/详情刮削 |
| bangumi | 公开 API | — |

## 验收

见 `GOAL.md`。`self-check` 打印 `GOAL_MATCHED=true` 即为达标。
