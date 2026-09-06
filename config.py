"""Configuration - all from Koyeb env vars."""
import os

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
API_ID: int = int(os.environ["API_ID"])
API_HASH: str = os.environ["API_HASH"]
USER_SESSION: str = os.environ.get("USER_SESSION", "")
DOWNLOAD_DIR: str = os.environ.get("DOWNLOAD_DIR", "/tmp/downloads")
MAX_FILE_SIZE: int = int(os.environ.get("MAX_FILE_SIZE", str(2 * 1024 * 1024 * 1024)))
