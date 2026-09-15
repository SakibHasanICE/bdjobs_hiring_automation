# app/common/logger.py
import logging
import os
from datetime import datetime

from config.settings import settings

os.makedirs(settings.LOGS_DIR, exist_ok=True)

LOG_FILE = os.path.join(settings.LOGS_DIR, f"log_{datetime.now().strftime('%Y-%m-%d')}.log")

logging.basicConfig(
    filename=LOG_FILE,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    level=logging.INFO,
)

# The old print()-based debugging was console-only. Keep that real-time
# visibility (useful since the browser normally runs headed) while also
# persisting everything to the daily log file via the root handler above.
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter("%(levelname)s - %(name)s - %(message)s"))
_console_handler.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        logger.addHandler(_console_handler)
    return logger