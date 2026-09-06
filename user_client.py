"""User session - session string from env, no .session file."""
from __future__ import annotations
import logging
from typing import Optional
from wzgram import Client
import config

log = logging.getLogger(__name__)
_user_client = None

def get_user_client():
    global _user_client
    if _user_client is not None:
        return _user_client
    if not config.USER_SESSION:
        log.warning("USER_SESSION not set - restricted channel access disabled")
        return None
    _user_client = Client(
        "user_session",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        session_string=config.USER_SESSION,
        in_memory=True,
    )
    return _user_client
