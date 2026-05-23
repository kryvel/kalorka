"""Constants discovered while reverse-engineering the public web app."""
from __future__ import annotations

BASE_URL = "https://www.kaloricketabulky.cz"

# Stock-database guid for "voda čistá" (plain water). Used as the default
# foodstuff when logging a drink without a custom name.
WATER_FOODSTUFF_GUID = "73a02350d55a3f8f"

# User-Agent that doesn't immediately scream "bot". Override via Client(user_agent=…)
# if you need to.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0 Safari/537.36"
)

# How long to trust a cached session cookie before forcing a re-login.
SESSION_TTL_SECONDS = 3 * 24 * 3600

# HTTP timeouts (connect, read).
DEFAULT_TIMEOUT = (5.0, 15.0)
