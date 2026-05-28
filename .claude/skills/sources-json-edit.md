---
name: sources-json-edit
description: 修改 sources.json 时必须遵守的契约与流程。任何 sources.json 写操作前必须加载本 skill。
---

# sources.json 编辑契约

## 硬规则
1. **永不删除源**。降级而非删除：green → yellow → gray。
2. `health.status` 仅允许：`green` / `yellow` / `gray`
3. `health.status_detail` 仅允许：`ok` / `healed` / `waf` / `404` / `expired` / `unreachable` / `parsing_failed`
4. `health.fail_streak` 是整数，默认 0；连续失败 ≥3 才允许实际降级。
5. 修改后**必须**运行 `python magnet/validate_enum.py`，输出非 `ALL VALID` 一律回滚。

## 强制流程
1. 写改动前先 `git status`，确认 sources.json 无未提交脏改（如有先 stash/commit）。
2. 改动后立即跑 `python magnet/validate_enum.py`。
3. 跑 `python magnet/crawler_v3/cli.py brand-stats` 看 brand 覆盖与 green/yellow/gray 分布是否符合预期。
4. commit message 用 `sources(<brand>): <action>` 格式，例如 `sources(磁力狐): yellow→green via cache.foxs.top`。

## 字段最小骨架
每条 source 必须含 `id` / `brand` / `origin` / `search` / `selectors` / `health`。新增源时若无法填全 selectors，先置 health.status=yellow，detail=parsing_failed，待解析逻辑稳定后再升 green。

## 反模式（看到立即停下）
- 直接 `git checkout sources.json` 丢弃未提交改动
- 把 status 写成 red / dead / unknown（非法枚举）
- 同一域名既出现在 green 又出现在 gray
