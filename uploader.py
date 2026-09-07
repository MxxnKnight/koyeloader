# uploader.py
from __future__ import annotations
import asyncio
from downloader import AsyncStreamWrapper
from utils import make_progress, safe_edit


async def upload_stream(client, chat_id, stream, file_name, *, status_msg=None, as_video=True):
    import time
    _prog = make_progress(file_name, status_msg, time.monotonic())
    kw = dict(chat_id=chat_id, file_name=file_name, progress=_prog)
    if as_video:
        kw["video"] = stream
        kw["supports_streaming"] = True
        await client.send_video(**kw)
    else:
        kw["document"] = stream
        await client.send_document(**kw)
    if status_msg:
        await asyncio.sleep(1)
        await safe_edit(status_msg, f"**{file_name}** - Done!")
        await asyncio.sleep(3)
        await safe_edit(status_msg, " ")


async def copy_media(user_client, bot_client, source_chat, message_id, destination_chat, *, status_msg=None):
    import time, logging
    from utils import format_size
    log = logging.getLogger(__name__)
    # Resolve peer so the session storage knows about this chat
    try:
        await user_client.get_chat(source_chat)
    except Exception:
        pass  # peer may already be cached, or get_chat fails for -100 IDs
    msgs = await user_client.get_messages(source_chat, message_ids=[message_id])
    if not msgs or msgs[0] is None:
        raise ValueError(f"Message {message_id} not found in {source_chat}")
    msg = msgs[0]
    if msg.media is None:
        raise ValueError(f"Message {message_id} has no media")
    media = msg.media
    # Extract the actual document/video from the media wrapper
    doc = getattr(media, "document", None) or getattr(media, "video", None) or media
    is_vid = hasattr(doc, "duration") and doc.duration is not None
    fn = getattr(doc, "file_name", None) or f"media_{msg.id}"
    fs = getattr(doc, "file_size", 0) or 0
    log.info("copy_media: %s (%s) from %s msg %s", fn, format_size(fs), source_chat, message_id)
    gen = user_client.stream_media(msg, limit=None)
    sf = AsyncStreamWrapper(name=fn, size=fs, stream_generator=gen)
    _prog = make_progress(fn, status_msg, time.monotonic())
    kw = dict(chat_id=destination_chat, file_name=fn, progress=_prog)
    if is_vid:
        kw["video"] = sf
        kw["supports_streaming"] = True
        await bot_client.send_video(**kw)
    else:
        kw["document"] = sf
        await bot_client.send_document(**kw)
    if status_msg:
        await asyncio.sleep(1)
        await safe_edit(status_msg, f"**{fn}** - Done!")
        await asyncio.sleep(3)
        await safe_edit(status_msg, " ")