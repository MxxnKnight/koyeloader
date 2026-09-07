# downloader.py
from __future__ import annotations
import asyncio
import io
import logging
import os
import queue
import re
import threading
from dataclasses import dataclass
from typing import Callable, Optional
import aiohttp
import config

log = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


@dataclass
class FileInfo:
    name: str
    size: int


class AsyncStreamWrapper(io.BufferedIOBase):
    """Bridges async chunk source into a file-like object for wzgram."""

    def __init__(self, name, size, *, url=None, stream_generator=None, on_progress=None):
        self.name = name
        self.size = size
        self.mode = "rb"
        self._on_progress = on_progress
        self._queue = queue.Queue(maxsize=4)
        self._done = False
        self._error = None
        self._downloaded = 0
        self._remainder = b""
        self._pos = 0
        if url:
            self._thread = threading.Thread(target=self._aiohttp_thread, args=(url,), daemon=True)
        elif stream_generator is not None:
            self._thread = threading.Thread(target=self._stream_gen_thread, args=(stream_generator,), daemon=True)
        else:
            raise ValueError("Provide url or stream_generator")
        self._thread.start()

    def _aiohttp_thread(self, url):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._aiohttp_download(url))
        except Exception as e:
            self._error = e
        finally:
            self._done = True
            loop.close()

    async def _aiohttp_download(self, url):
        timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    raise RuntimeError("HTTP " + str(r.status))
                async for chunk in r.content.iter_chunked(CHUNK_SIZE):
                    self._queue.put(chunk)
                    self._downloaded += len(chunk)
                    self._emit()

    def _stream_gen_thread(self, gen):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_stream(gen))
        except Exception as e:
            self._error = e
        finally:
            self._done = True
            loop.close()

    async def _run_stream(self, gen):
        async for chunk in gen:
            self._queue.put(chunk)
            self._downloaded += len(chunk)
            self._emit()

    def _emit(self):
        if self._on_progress:
            try:
                self._on_progress(self._downloaded, self.size)
            except Exception:
                pass

    def read(self, size=-1):
        if self._error:
            raise self._error
        if self._remainder and size != -1:
            chunk = self._remainder[:size]
            self._remainder = self._remainder[size:]
            return chunk
        try:
            chunk = self._queue.get(timeout=60)
        except queue.Empty:
            if self._done:
                return b""
            raise TimeoutError("Stream timeout: no data for 60s")
        if size != -1 and size < len(chunk):
            self._remainder = chunk[size:]
            return chunk[:size]
        return chunk

    def seek(self, offset, whence=0):
        # Pyrogram calls seek(0, SEEK_END) then tell() then seek(0)
        # before any reads - this is just to get file_size
        if whence == os.SEEK_END:
            self._pos = self.size
        else:
            self._pos = offset
        return self._pos

    def tell(self):
        return self._pos

    def flush(self):
        pass

    def seekable(self):
        return True

    def readable(self):
        return True

    def writable(self):
        return False

    def __len__(self):
        return self.size


async def get_file_info(url):
    async with aiohttp.ClientSession() as s:
        async with s.head(url, allow_redirects=True) as r:
            cd = r.headers.get("Content-Disposition", "")
            name = "download"
            pat = r"filename\*?\s*=\x22?(?:utf-8'')?([^\x22;\s=]+)"
            m = re.search(pat, cd, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
            size = int(r.headers.get("Content-Length", 0))
    if name == "download":
        from urllib.parse import urlparse
        name = os.path.basename(urlparse(url).path) or "download"
        name = name.split("?")[0]
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return FileInfo(name=name, size=size)