"""Freebuff Bot - send a link, bot handles the rest."""
from __future__ import annotations
import asyncio
import logging
import re
import sys
import time
from wzgram import Client, filters
import config
from downloader import get_file_info, AsyncStreamWrapper
from uploader import upload_stream, copy_media, format_size, progress_bar, format_eta
from user_client import get_user_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", stream=sys.stdout)
log = logging.getLogger("freebuff")

bot = Client("bot", bot_token=config.BOT_TOKEN, in_memory=True)
_user = get_user_client()
_sem = asyncio.Semaphore(1)


def _parse_tg(text):
    pat = r'(?:t\\.me|telegram\\.me)/(?:c/)?([a-zA-Z0-9_]+)(?:/(\\d+))?'
    m = re.search(pat, text)
    if not m:
        return None, None
    chat = m.group(1)
    mid = int(m.group(2)) if m.group(2) else None
    chat = "-100" + chat if chat.isdigit() else "@" + chat
    return chat, mid


def _find_urls(text):
    pat = r'https?://[^\\s<>" ]+'
    return re.findall(pat, text or "")


async def _edit(msg, text):
    try:
        await msg.edit(text)
    except Exception:
        pass


@bot.on_message(filters.private & (filters.text | filters.caption))
async def handle(client, message):
    text = message.text or message.caption or ""
    tg_chat, tg_mid = _parse_tg(text)
    urls = _find_urls(text)

    NL = chr(10)
    if tg_mid is None and not urls:
        await message.reply("Send me a link:" + NL + NL + "- https://example.com/video.mp4" + NL + "- https://t.me/channel/123" + NL + "- https://t.me/c/1234567890/123")
        return

    async with _sem:
        if tg_mid is not None:
            if _user is None:
                await message.reply("User session not configured." + NL + "Set the USER_SESSION env var.")
                return
            status = await message.reply("Fetching from Telegram...")
            try:
                await copy_media(user_client=_user, bot_client=client, source_chat=tg_chat, message_id=tg_mid, destination_chat=message.chat.id, status_msg=status)
            except Exception as e:
                log.exception("copy_media failed")
                await status.edit("Failed: " + str(e))
            return

        url = urls[0]
        status = await message.reply("Probing URL...")
        try:
            info = await get_file_info(url)
        except Exception as e:
            await status.edit("Could not probe URL: " + str(e))
            return

        if info.size > config.MAX_FILE_SIZE:
            await status.edit("File too large: " + format_size(info.size) + " (limit " + format_size(config.MAX_FILE_SIZE) + ")")
            return
        if info.size == 0:
            await status.edit("Could not determine file size. Trying anyway...")

        loop = asyncio.get_running_loop()
        ds = time.monotonic()
        last = [0.0]

        def _prog(dl, tot):
            now = time.monotonic()
            if now - last[0] < 4.0:
                return
            last[0] = now
            el = now - ds or 0.001
            spd = dl / el
            rem = (tot - dl) / spd if spd > 0 else 0
            pct = (dl / tot * 100) if tot else 0
            NL2 = chr(10)
            txt = "**" + info.name + "**" + NL2 + progress_bar(pct) + NL2 + format_size(dl) + " / " + format_size(info.size) + NL2 + format_size(int(spd)) + "/s  ETA " + format_eta(rem)
            asyncio.run_coroutine_threadsafe(_edit(status, txt), loop)

        stream = AsyncStreamWrapper(name=info.name, size=info.size, url=url, on_progress=_prog)
        try:
            vid_exts = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v")
            as_video = info.name.lower().endswith(vid_exts) if info.name else True
            await upload_stream(client, message.chat.id, stream, info.name, status_msg=status, as_video=as_video)
        except Exception as e:
            log.exception("upload failed")
            await status.edit("Upload failed: " + str(e))


@bot.on_message(filters.command("start") & filters.private)
async def start(client, message):
    s = "configured" if config.USER_SESSION else "not configured"
    NL = chr(10)
    await message.reply("**Freebuff Bot**" + NL + NL + "Send me a link:" + NL + "- https://example.com/video.mp4" + NL + "- https://t.me/channel/123" + NL + "- https://t.me/c/1234567890/123" + NL + NL + "Session: " + s + NL + "Max: " + format_size(config.MAX_FILE_SIZE))


async def _run():
    await bot.start()
    log.info("Bot @%s started", (await bot.get_me()).username)
    if _user:
        await _user.start()
        me = await _user.get_me()
        log.info("User session: %s", me.first_name)
    log.info("Running. Send a link to start.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass