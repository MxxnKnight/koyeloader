# config.py
import os
import sys

def _require(key):
    val = os.environ.get(key)
    if not val:
        print(f"[FATAL] Missing required env var: {key}", file=sys.stderr)
        sys.exit(1)
    return val

BOT_TOKEN = _require("BOT_TOKEN")
API_ID = int(_require("API_ID"))
API_HASH = _require("API_HASH")
USER_SESSION = os.environ.get("USER_SESSION", "")
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", str(2 * 1024 * 1024 * 1024)))