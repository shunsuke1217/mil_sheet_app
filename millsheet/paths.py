"""データ用フォルダの場所（SPEC 10章）。"""
import os
from pathlib import Path

import platformdirs

APP_NAME = "ミルシート読み取り"


def data_dir() -> Path:
    override = os.environ.get("MILLSHEET_DATA_DIR")
    d = Path(override) if override else Path(platformdirs.user_data_dir(APP_NAME, appauthor=False, roaming=True))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _subdir(name: str) -> Path:
    d = data_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    return _subdir("cache")


def logs_dir() -> Path:
    return _subdir("logs")


def settings_path() -> Path:
    return data_dir() / "settings.json"

