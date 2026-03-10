---
name: a-share-summary
description: A-share market summary with daily and 5-minute modes. Fetches indices, breadth, sectors, and watchlists from akshare.
---

# A-Share Summary

Fetch and summarize A-share market data from akshare (free, no key required), with both daily and 5-minute briefing modes.

## Quick Start

```bash
# Daily full market summary (default mode)
python .claude/skills/the-one/skills/a-share-summary/scripts/fetch_a_share.py

# Daily fast mode (skip breadth snapshot processing)
python .claude/skills/the-one/skills/a-share-summary/scripts/fetch_a_share.py --skip-breadth

# Daily raw JSON only
python .claude/skills/the-one/skills/a-share-summary/scripts/fetch_a_share.py --json-only

# Daily with custom sector counts
python .claude/skills/the-one/skills/a-share-summary/scripts/fetch_a_share.py --industry-top 15 --concept-top 20

# 5-minute concise brief (watchlists from JSON config)
python .claude/skills/the-one/skills/a-share-summary/scripts/fetch_a_share.py --mode 5m --watch-config .claude/skills/the-one/skills/a-share-summary/watch-config.example.json

# 5-minute with CLI overrides (optional)
python .claude/skills/the-one/skills/a-share-summary/scripts/fetch_a_share.py --mode 5m --watch-config .claude/skills/the-one/skills/a-share-summary/watch-config.example.json --watch-sectors "AI应用,算力" --watch-stocks "600673:东阳光,300418:昆仑万维"

# 5-minute scheduled execution (external scheduler)
watch -n 300 "python .claude/skills/the-one/skills/a-share-summary/scripts/fetch_a_share.py --mode 5m --watch-config .claude/skills/the-one/skills/a-share-summary/watch-config.example.json"
```

## Output

- **Daily JSON file**: `output/a-share-{date}.json` (git-ignored, raw data)
- **5m JSON file**: `output/a-share-{date}-5m.json` (git-ignored, watchlist snapshot)
- **Stdout**: Formatted markdown summary (daily full tables or 5m concise brief)

## Workflow

### Daily workflow

1. Run `fetch_a_share.py` (default `--mode daily`) → get structured markdown summary + raw JSON
2. Review the data, add **market commentary** (the script provides facts, you provide analysis)
3. Save the final briefing to `briefings/YYYY-MM-DD-a-share.md`
4. Optionally cross-reference with news-briefing output for context

### Intraday 5m workflow

1. Run `fetch_a_share.py --mode 5m --watch-config <path-to-json>` with your watchlist JSON
2. Read four core blocks: regime / sector watchlist / stock watchlist / alerts
3. Use external scheduler (`watch` or cron) to trigger every 5 minutes
4. Track signal continuity across multiple snapshots (not single-point spikes)

## Commentary Guidelines

The script outputs raw data tables. Add value with:
- **Main themes**: Identify 2-3 driving narratives (e.g., geopolitical risk, sector rotation)
- **Cross-reference**: Connect market moves to news events (use news-briefing data)
- **Memory recall**: Relate to investment domain memories (a-share-investment, trading-cognition-douzi)
- **Overall judgment**: One-paragraph market tone assessment

## 5m Watchlist Config

`--watch-config` expects a JSON file with this shape:

```json
{
  "watch_sectors": ["AI应用", "算力"],
  "watch_stocks": [
    {"code": "600673", "name": "东阳光"},
    {"code": "300418", "name": "昆仑万维"}
  ]
}
```

A ready-to-edit template is provided at:

- `.claude/skills/the-one/skills/a-share-summary/watch-config.example.json`

Notes:
- `watch_stocks` also accepts plain code strings (e.g. `"600673"`)
- `--watch-sectors` / `--watch-stocks` can override config values when passed

### Market regime (`regime`)

- Score blends index momentum + breadth spread + limit-up/down spread
- Labels:
  - `risk_on`: score >= 20
  - `neutral`: -20 < score < 20
  - `risk_off`: score <= -20

### Sector watchlist (`sector_watchlist`)

- Match order: exact name first, then fuzzy substring match
- Status:
  - `strong`: change_pct >= 2.0 and strength >= 0.60
  - `weak`: change_pct <= -2.0 and strength <= 0.40
  - `neutral`: otherwise
  - `missing`: not found in current concept board snapshot

### Stock watchlist (`stock_watchlist`)

- Status:
  - `breakout`: change_pct >= 3.0
  - `breakdown`: change_pct <= -3.0
  - `active`: abs(change_pct) >= 1.5 and (turnover_rate >= 5 or volume_ratio >= 1.5)
  - `watch`: otherwise
  - `missing`: not found in current full-market snapshot

### Alerts (`alerts`)

- Aggregates non-neutral signals from regime + watched sectors + watched stocks into concise bullet points.

## Data Coverage

| Data | Source | Fields |
|------|--------|--------|
| Major indices (6) | ak.stock_zh_index_spot_em | close, change%, turnover |
| Market breadth | ak.stock_zh_a_spot_em | up/down/flat/limit counts |
| Industry sectors | ak.stock_board_industry_name_em | change%, up/down count, leader |
| Concept sectors | ak.stock_board_concept_name_em | change%, up/down count |
| Top stocks | ak.stock_zh_a_spot_em | top 10 gainers/losers |

## API Notes

- **Source layer**: akshare 聚合公开行情源（无需自行维护 push2 参数）
- **No auth required**, no API key
- Index data comes from `stock_zh_index_spot_em`
- Sector data comes from `stock_board_industry_name_em` and `stock_board_concept_name_em`
- Breadth and top/bottom stocks are computed from full A-share snapshot `stock_zh_a_spot_em`
- Invalid change values (`-`, `None`, NaN) are safely skipped or normalized

## Dependencies

All in `nix/development.nix`: `akshare`, `pandas`, `click`
