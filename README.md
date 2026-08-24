# open-session-watchdog

Hermes Agent 会话成本看门狗: 检测活跃会话是否达 token 临界值(累计输入 / 上下文压缩次数), 超限输出提醒, 提示落盘现场 + 开新窗口续接, 避免压缩循环烧 token 掉质量。

A lightweight watchdog for [Hermes Agent](https://github.com/NousResearch/hermes-agent) sessions: detects when the active desktop session hits token thresholds (cumulative input / context-compaction count) and warns — before repeated compression degrades quality and burns tokens.

## 为什么需要 (Why)

- Hermes 内置自动上下文压缩(`compression.threshold`, 默认 50%), 超窗会自动处理 — 不用管。
- 真正的问题是**反复压缩**(压缩循环): 质量下降 + token 消耗。实测数据: 压缩是"全有全无" — 297 个会话 0 压缩, 18 个 >50 条; 一旦压缩, 单次事件就标记 50+ 条消息。
- 结论: **压缩出现 = 该换窗口了**, 不用等它压几轮。

## 阈值 (Thresholds, env-overridable)

| Signal | Default | Env override | Rationale |
|---|---|---|---|
| cumulative `input_tokens` | `300000` | `SESSION_HEALTH_INPUT_THRESHOLD` | cost guard |
| `compacted` messages | `10` | `SESSION_HEALTH_COMPACT_THRESHOLD` | fires on first compaction (quality guard) |

## 用法 (Usage)

```bash
python session_health_watch.py
```

- Over threshold → prints a Chinese alert to stdout (for cron/no_agent push); otherwise **zero output**, exit code always `0`.
- Alerts once per session (dedupe file `.session_health_alerts.json` next to the script).
- Read-only SQLite connection to `%LOCALAPPDATA%\hermes\state.db`; NULL-safe, GBK-safe, corrupted-state safe.

### 会话内自律 (In-session rule — the intended use)

在长任务每个阶段边界跑一次: 有输出 → 落盘现场进度 + 开新窗口续接; 无输出 → 继续。不需要任何 cron / 推送基础设施。

## 工作原理 (How it works)

1. 找活跃桌面会话: `sessions` 表 `source='desktop'`, title 非空, 非 cron/feishu 会话, `last_activity_at` 在 2 小时内, 取最新。
2. 统计该会话 `messages` 表 `compacted=1` 的消息数。
3. 任一阈值超限 → 一次性提醒(去重), 建议按交接协议落盘后开新窗口。

## License

MIT
