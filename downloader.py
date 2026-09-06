"""In-memory streaming bridge - zero disk."""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import re
import threading
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Optional

import aiohttp
import config

log = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


@dataclass
class FileInfo:
    name: str
    size: int


class AsyncStreamWrapper:
    """Bridges async chunk source into file-like object for wzgram."""

    def __init__(self, name, size, *, url=None, stream_generator=None, on_progress=None):
        self.name = name
        self.size = size
        self._on_progress = on_progress
        self._queue = queue.Queue(maxsize=4)
        self._done = False
        self._error = None
        self._downloaded = 0
        self._remainder = b''
        if url:
            self._thread = threading.Thread(target=self._aiohttp_thread, args=(url,), daemon=True)
        elif stream_generator is not None:
            self._thread = threading.Thread(target=self._stream_gen_thread, args=(stream_generator,), daemon=True)
        else:
            raise ValueError('Provide url or stream_generator')
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
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                if r.status != 200:
                    raise RuntimeError(f'HTTP {r.status}')
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
            chunk = self._queue.get(timeout=30)
        except queue.Empty:
            if self._done:
                return b''
            raise TimeoutError('Stream timeout')
        if size != -1 and size < len(chunk):
            self._remainder = chunk[size:]
            return chunk[:size]
        return chunk

    def __aiter__(self):
        return self._async_iter()

    async def _async_iter(self):
        while True:
            try:
                yield self._queue.get_nowait()
            except queue.Empty:
                if self._done:
                    if self._error:
                        raise self._error
                    break
                await asyncio.sleep(0.05)

    def __len__(self):
        return self.size
    def seekable(self):
        return False
    def readable(self):
        return True


async def get_file_info(url):
    async with aiohttp.ClientSession() as s:
        async with s.head(url, allow_redirects=True) as r:
            cd = r.headers.get('Content-Disposition', '')
            name = 'download'
            m = re.search(r'filename[*]?=["']?([^"';\s]+)', cd, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
            size = int(r.headers.get('Content-Length', 0))
    if name == 'download':
        from urllib.parse import urlparse
        name = os.path.basename(urlparse(url).path) or 'download'
        name = name.split('?')[0]
    return FileInfo(name=name, size=size)
