"""Upload wrappers - streaming only, zero disk."""
from __future__ import annotations
import asyncio
import logging
import time
from wzgram import Client
from downloader import AsyncStreamWrapper

log = logging.getLogger(__name__)


def format_size(n):
    if n < 0:
        return '0 B'
    for u in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024:
            return f'{n:.1f} {u}'
        n /= 1024
    return f'{n:.1f} PB'


def format_eta(s):
    if s < 0 or s != s:
        return '~'
    m, sec = divmod(int(s), 60)
    h, m = divmod(m, 60)
    if h:
        return f'{h}h{m:02d}m'
    if m:
        return f'{m}m{sec:02d}s'
    return f'{sec}s'


def progress_bar(pct, w=20):
    pct = max(0.0, min(100.0, pct))
    f = int(w * pct / 100)
    return f'[{chr(9608) * f}{chr(9617) * (w - f)}] {pct:.1f}%'


async def _safe_edit(msg, text):
    try:
        await msg.edit(text)
    except Exception:
        pass


def _make_progress(label, status_msg, start_time):
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
        NL = chr(10)
        txt = f'**{label}**{NL}{progress_bar(pct)}{NL}{format_size(cur)} / {format_size(tot)}{NL}{format_size(int(spd))}/s  ETA {format_eta(rem)}'
        if status_msg:
            asyncio.get_event_loop().create_task(_safe_edit(status_msg, txt))

    return _prog


async def upload_stream(client, chat_id, stream, file_name, *, status_msg=None, as_video=True):
    start = time.monotonic()
    _prog = _make_progress(file_name, status_msg, start)

    kw = dict(chat_id=chat_id, file_name=file_name, progress=_prog)
    if as_video:
        kw['video'] = stream
        kw['supports_streaming'] = True
        await client.send_video(**kw)
    else:
        kw['document'] = stream
        await client.send_document(**kw)

    if status_msg:
        await asyncio.sleep(1)
        await _safe_edit(status_msg, f'**{file_name}** - Done!')
        await asyncio.sleep(3)
        await _safe_edit(status_msg, ' ')


async def copy_media(user_client, bot_client, source_chat, message_id, destination_chat, *, status_msg=None):
    msgs = await user_client.get_messages(source_chat, ids=[message_id])
    if not msgs or msgs[0] is None:
        raise ValueError(f'Message {message_id} not found in {source_chat}')
    msg = msgs[0]
    if msg.media is None:
        raise ValueError(f'Message {message_id} has no media')

    media = msg.media
    is_vid = hasattr(media, 'duration') and media.duration is not None
    fn = getattr(media, 'file_name', None) or f'media_{msg.id}'
    fs = getattr(media, 'file_size', 0) or 0
    log.info('copy_media: %s (%s) from %s msg %s', fn, format_size(fs), source_chat, message_id)

    gen = user_client.stream_media(msg, limit=None)
    sf = AsyncStreamWrapper(name=fn, size=fs, stream_generator=gen)

    start = time.monotonic()
    _prog = _make_progress(fn, status_msg, start)

    kw = dict(chat_id=destination_chat, file_name=fn, progress=_prog)
    if is_vid:
        kw['video'] = sf
        kw['supports_streaming'] = True
        await bot_client.send_video(**kw)
    else:
        kw['document'] = sf
        await bot_client.send_document(**kw)

    if status_msg:
        await asyncio.sleep(1)
        await _safe_edit(status_msg, f'**{fn}** - Done!')
        await asyncio.sleep(3)
        await _safe_edit(status_msg, ' ')
