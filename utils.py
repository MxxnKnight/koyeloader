# utils.py - shared helpers
import asyncio
import time


def format_size(n):
    if n < 0:
        return "0 B"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def format_eta(s):
    if s < 0 or s != s:
        return "~"
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"


def progress_bar(pct, w=20):
    pct = max(0.0, min(100.0, pct))
    f = int(w * pct / 100)
    return f"[{chr(9608) * f}{chr(9617) * (w - f)}] {pct:.1f}%"


async def safe_edit(msg, text):
    try:
        await msg.edit(text)
    except Exception:
        pass


def make_progress(label, status_msg, start_time):
    last_edit = [0.0]

    def _prog(cur, tot):
        now = time.monotonic()
        if now - last_edit[0] < 4.0:
            return
        last_edit[0] = now
        el = now - start_time or 0.001
        spd = cur / el
        rem = (tot - cur) / spd if spd > 0 else 0
        pct = (cur / tot * 100) if tot else 0
        txt = f"**{label}**" + chr(10) + progress_bar(pct) + chr(10) + format_size(cur) + " / " + format_size(tot) + chr(10) + format_size(int(spd)) + "/s  ETA " + format_eta(rem)
        if status_msg:
            asyncio.get_running_loop().create_task(safe_edit(status_msg, txt))

    return _prog