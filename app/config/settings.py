# app/config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Central place for every configurable value the automation uses.

    Anything that used to be a hardcoded literal scattered across
    browser_manager.py / bdjobs_auth.py / main.py (the login URL, viewport
    size, timeouts, user agent, output folders) lives here instead, so it
    can be overridden via .env without touching code.
    """

    # --- Credentials ---------------------------------------------------
    BDJOBS_USER = os.getenv("BDJOBS_USER")
    BDJOBS_PASS = os.getenv("BDJOBS_PASS")

    # --- Site ------------------------------------------------------------
    BDJOBS_LOGIN_URL = os.getenv("BDJOBS_LOGIN_URL", "https://recruiter.bdjobs.com/")

    # --- Browser ---------------------------------------------------------
    HEADLESS = os.getenv("HEADLESS", "false").strip().lower() == "true"
    DEFAULT_TIMEOUT_MS = int(os.getenv("DEFAULT_TIMEOUT_MS", "60000"))
    VIEWPORT_WIDTH = int(os.getenv("VIEWPORT_WIDTH", "1366"))
    VIEWPORT_HEIGHT = int(os.getenv("VIEWPORT_HEIGHT", "768"))
    USER_AGENT = os.getenv(
        "USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    )

    # --- Output directories -----------------------------------------------
    # Kept as the same bare relative names logger.py already used ("logs"),
    # so behavior is unchanged by default - but now overridable via .env
    # instead of hardcoded, in case "downloads"/"logs"/"screenshots" end up
    # living at the project root vs. inside app/ (both appear in the repo
    # tree; adjust these three if the log file doesn't land where expected).
    LOGS_DIR = os.getenv("LOGS_DIR", "logs")
    SCREENSHOTS_DIR = os.getenv("SCREENSHOTS_DIR", "screenshots")
    DOWNLOADS_DIR = os.getenv("DOWNLOADS_DIR", "downloads")


settings = Settings()