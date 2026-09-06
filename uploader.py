"""Upload wrappers - streaming only, zero disk."""
from __future__ import annotations
import asyncio, logging, time
from wzgram import Client
from downloader import AsyncStreamWrapper

log = logging.getLogger(__name__)

def format_size(n):
    for u in ('B','KB','MB','GB','TB'):
        if abs(n) < 1024: return f'{n:.1f} {u}'
        n /= 1024
    return f'{n:.1f} PB'

def format_eta(s):
    if s < 0: return '~'
    m,sec = divmod(int(s),60); h,m = divmod(m,60)
    if h: return f'{h}h{m:02d}m'
    if m: return f'{m}m{sec:02d}s'
    return f'{sec}s'

def progress_bar(pct, w=20):
    f = int(w*pct/100)
    return f'[{chr(9608)*f}{chr(9617)*(w-f)}] {pct:.1f}%'

async def _safe_edit(msg, text):
    try: await msg.edit(text)
    except: pass

async def upload_stream(client, chat_id, stream, file_name, *, status_msg=None, as_video=True):
    start = time.monotonic()
    last = [0.0]
    def _prog(cur, tot):
        now = time.monotonic()
        if now - last[0] < 4.0: return
        last[0] = now
        el = now - start or 0.001; spd = cur/el; rem = (tot-cur)/spd if spd else 0
        pct = (cur/tot*100) if tot else 0
        txt = f'**{file_name}**
{progress_bar(pct)}
{format_size(cur)} / {format_size(tot)}
{format_size(int(spd))}/s  ETA {format_eta(rem)}'
        if status_msg: asyncio.get_event_loop().create_task(_safe_edit(status_msg, txt))
    kw = dict(chat_id=chat_id, file_name=file_name, progress=_prog)
    if as_video:
        kw['video'] = stream; kw['supports_streaming'] = True
        await client.send_video(**kw)
    else:
        kw['document'] = stream
        await client.send_document(**kw)
    if status_msg:
        await asyncio.sleep(1)
        await _safe_edit(status_msg, f'**{file_name}** - Done!')
        await asyncio.sleep(2)
        await _safe_edit(status_msg, ' ')

async def copy_media(user_client, bot_client, source_chat, message_id, destination_chat, *, status_msg=None):
    msgs = await user_client.get_messages(source_chat, ids=[message_id])
    if not msgs or msgs[0] is None: raise ValueError(f'Message {message_id} not found')
    msg = msgs[0]
    if msg.media is None: raise ValueError(f'Message {message_id} has no media')
    media = msg.media
    is_vid = hasattr(media, 'duration')
    fn = getattr(media, 'file_name', None) or f'media_{msg.id}'
    fs = getattr(media, 'file_size', 0) or 0
    log.info('copy_media: %s (%s) from %s msg %s', fn, format_size(fs), source_chat, message_id)
    gen = user_client.stream_media(msg, limit=None)
    ds = time.monotonic(); last = [0.0]
    def _prog(dl, tot):
        now = time.monotonic()
        if now - last[0] < 4.0: return
        last[0] = now
        el = now - ds or 0.001; spd = dl/el; rem = (tot-dl)/spd if spd else 0
        pct = (dl/tot*100) if tot else 0
        txt = f'**{fn}**
{progress_bar(pct)}
{format_size(dl)} / {format_size(tot)}
{format_size(int(spd))}/s  ETA {format_eta(rem)}'
        asyncio.get_event_loop().create_task(_safe_edit(status_msg, txt))
    sf = AsyncStreamWrapper(name=fn, size=fs, stream_generator=gen, on_progress=_prog)
    kw = dict(chat_id=destination_chat, file_name=fn)
    if is_vid: kw['video'] = sf; kw['supports_streaming'] = True; await bot_client.send_video(**kw)
    else: kw['document'] = sf; await bot_client.send_document(**kw)
    if status_msg:
        await asyncio.sleep(1)
        await _safe_edit(status_msg, f'**{fn}** - Done!')
        await asyncio.sleep(2)
        await _safe_edit(status_msg, ' ')
