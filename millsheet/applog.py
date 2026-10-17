"""ログの設定。API キーはログに書かない。"""
import logging
from logging.handlers import RotatingFileHandler

from millsheet import paths


def mask(text: str, secrets: list[str | None]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def setup_logging() -> None:
    handler = RotatingFileHandler(paths.logs_dir() / "app.log", maxBytes=5 * 1024 * 1024,
                                  backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # URL に API キーが入るため
