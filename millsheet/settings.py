"""settings.json（API キーは入れない）と keyring に置く API キー。"""
import json
import logging
from dataclasses import asdict, dataclass, fields
from typing import Literal

import keyring

from millsheet import paths

log = logging.getLogger(__name__)

SecretName = Literal["gemini_api_key", "google_api_key"]


@dataclass
class Settings:
    sheet_url: str = ""
    sheet_name: str = ""
    output_path: str = ""
    exporter: str = "local_xlsx"


def load_settings() -> Settings:
    p = paths.settings_path()
    if not p.exists():
        return Settings()
    try:
        data = json.loads(p.read_text("utf-8"))
        known = {f.name for f in fields(Settings)}
        return Settings(**{k: v for k, v in data.items() if k in known})
    except (ValueError, TypeError) as e:
        log.warning("settings.json を読めなかったため既定の設定で起動します: %s", e)
        return Settings()


def save_settings(s: Settings) -> None:
    p = paths.settings_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s), ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(p)


def get_secret(name: SecretName) -> str | None:
    return keyring.get_password(paths.APP_NAME, name)


def set_secret(name: SecretName, value: str) -> None:
    keyring.set_password(paths.APP_NAME, name, value)
