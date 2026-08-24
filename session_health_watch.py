#!/usr/bin/env python3
"""会话成本看门狗: 检测活跃桌面会话是否达临界值(token累计/压缩次数)。

no_agent cron 用法: 超限时 stdout 输出提醒(verbatim推送), 未超限静默(空输出=不推送)。
阈值可用环境变量覆盖(便于测试):
  SESSION_HEALTH_INPUT_THRESHOLD  累计输入token阈值, 默认 300000
  SESSION_HEALTH_COMPACT_THRESHOLD 压缩消息数阈值, 默认 10
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote

# GBK 代码页管道捕获中文/⚠️ 时避免 UnicodeEncodeError
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    / "hermes" / "state.db"
)
STATE_FILE = Path(__file__).parent / ".session_health_alerts.json"
ACTIVE_WINDOW_S = 2 * 3600  # 2小时内活跃才算"当前会话"


def _env_int(name, default):
    """读环境变量为整数; 非法/空/非正数一律回退默认值。"""
    try:
        v = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return v if v > 0 else default


INPUT_THRESHOLD = _env_int("SESSION_HEALTH_INPUT_THRESHOLD", 300_000)
COMPACT_THRESHOLD = _env_int("SESSION_HEALTH_COMPACT_THRESHOLD", 10)


def load_alerted():
    """读取去重状态; 文件损坏/为空/内容非字符串列表时回退空集合。"""
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError, TypeError):
        return set()
    if isinstance(data, list):
        return {x for x in data if isinstance(x, str)}
    return set()


def save_alerted(alerted):
    """写去重状态; 失败(如目录不可写)返回 False, 由调用方静默跳过本次提醒。"""
    try:
        STATE_FILE.write_text(json.dumps(sorted(alerted), ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False


def find_active_desktop_session(conn):
    now = time.time()
    row = conn.execute(
        """
        SELECT id, title,
               COALESCE(input_tokens, 0),
               COALESCE(output_tokens, 0),
               COALESCE(estimated_cost_usd, 0)
        FROM sessions
        WHERE source='desktop' AND title IS NOT NULL AND title != ''
          AND id NOT LIKE 'cron_%' AND id NOT LIKE 'feishu_%'
          AND last_activity_at > ?
        ORDER BY last_activity_at DESC LIMIT 1
        """,
        (now - ACTIVE_WINDOW_S,),
    ).fetchone()
    return row


def compacted_count(conn, session_id):
    return conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id=? AND compacted=1",
        (session_id,),
    ).fetchone()[0]


def main():
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(
        f"file:{quote(DB_PATH.as_posix(), safe='/')}?mode=ro", uri=True
    )
    try:
        sess = find_active_desktop_session(conn)
        if not sess:
            return
        sid, title, inp, out, cost = sess
        compacts = compacted_count(conn, sid)

        over_input = inp > INPUT_THRESHOLD
        over_compact = compacts > COMPACT_THRESHOLD
        if not (over_input or over_compact):
            return

        # 一次性去重: 每个会话只提醒一次
        alerted = load_alerted()
        if sid in alerted:
            return
        alerted.add(sid)
        if not save_alerted(alerted):
            return  # 写失败静默跳过本次提醒, 下次再试

        reasons = []
        if over_input:
            reasons.append(f"累计输入 {inp:,} tokens")
        if over_compact:
            reasons.append(f"已压缩 {compacts:,} 条消息(上下文反复压缩, 质量下降)")
        print(
            f"⚠️ 会话成本看门狗: 「{title}」达临界值\n"
            f"- {' / '.join(reasons)}\n"
            f"- 累计输出 {out:,} tokens, 预估费用 ${cost:.3f}\n"
            f"- 建议: 让 Hermes 落盘现场进度(00_现场进度.md)后开新窗口续接, 避免压缩循环烧token+掉质量"
        )
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # 静默 + 退出码恒为 0
