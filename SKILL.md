---
name: open-session-watchdog
description: "Use when 会话token达临界值/压缩频繁/长任务是否换新窗口. 自查state.db, 超限落盘+提示开新窗."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [hermes, token, cost, session, watchdog, context, compression]
    related_skills: [hermes-session-management, hermes-usage-analytics]
---

# Open Session Watchdog (会话成本看门狗)

检测 Hermes 活跃桌面会话是否达 token 临界值(累计输入 / 上下文压缩次数), 超限自动落盘现场 + 提示用户开新窗口续接。**用户(2026-08-24)定: 不发飞书推送, 不建 cron 轰炸** — 触发靠会话内自律(阶段边界自查), 工具仅作本地自查手段。

## When to Use

**用户(2026-08-24)定: 本技能对全部会话生效, 是常驻规则, 不是可选流程。** 每个会话必须执行:

- 任务开始时自查一次(刚接活就确认起点)
- 长任务每个阶段边界自查(收到新任务/完成一个交付/暂停前)
- 用户问"这个窗口会不会太长了 / token 是不是烧多了 / 要不要开新窗口"
- 上下文压缩频繁出现(压缩循环), 需要量化证据决定是否交接
- 高token项目双倍时段暂停前, 确认交接时机

自查 = 跑一次脚本(见"用法"), 有输出→立即执行交接协议, 无输出→继续。不要等用户提醒。

## 背景: 什么才是真烧钱

- Hermes 内置自动压缩(`compression.threshold` 默认 50%), 上下文超窗自动处理, 不用管。
- 真正的问题是**反复压缩**(压缩循环): 质量下降 + 烧 token。真实数据: 压缩是"全有全无" — 297 个会话 0 压缩, 18 个 >50 条; 一旦压缩, 单次事件就标记 50+ 条消息。
- 结论: **压缩出现 = 该换窗口了**, 不用等它压几轮。

## 触发条件 (默认阈值, 环境变量可覆盖)

| 信号 | 默认 | 理由 |
|---|---|---|
| `input_tokens > 300000` | `SESSION_HEALTH_INPUT_THRESHOLD` | 累计输入过大(成本面) |
| `compacted > 10` | `SESSION_HEALTH_COMPACT_THRESHOLD` | 首次压缩即告警(质量面, 8-24 从100下调) |

## 用法

```bash
python scripts/session_health_watch.py
# 超限 → stdout 中文提醒(供 cron/no_agent 推送); 未超限/无活跃会话 → 零输出, 退出码恒0
# 每会话只提醒一次(去重文件 .session_health_alerts.json 在脚本同目录)
```

## 会话内自律规则 (核心用法, 不依赖任何 cron)

长任务中**每个阶段边界**(收到新任务/完成一个交付/暂停前)自查一次:

```bash
python "$LOCALAPPDATA/hermes/scripts/session_health_watch.py"   # Windows
```

- 有输出 → 立即执行交接协议: 落盘 `00_<项目>现场进度.md`(断点写成可直接续接步骤) + 告知用户开新窗口, 新窗口先读现场文件。
- 无输出 → 继续。
- 空闲时段(12-14点等低token时段)可选: 顺手跑一次, 超限就提示"低token时段可续接"。

## 交接协议

见 `hermes-session-management` 技能 references/high-token-handoff-protocol-2026-08.md: 现场落盘三处(进度文件头状态标记/待办区可续接步骤/环境备忘), 作废数字显式标注, 续接先读现场文件。

## 维护

- 脚本位置: `~/AppData/Local/hermes/scripts/session_health_watch.py`
- 改代码走 cc/c 交叉审核铁律(coding-agent-delegation 技能), 验收 = py_compile + 三场景实测(真实库静默/真实库超限告警/合成库压缩路径+去重)。
- 阈值调优看真实数据: `SELECT (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id AND m.compacted=1) FROM sessions s WHERE s.source='desktop'`。
