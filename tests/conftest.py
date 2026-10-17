from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PDF = FIXTURES / "20261014084620.pdf"


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        super().__init__()
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """全テストでデータ用フォルダを tmp に向ける（本物のキャッシュ・設定を汚さない）。"""
    d = tmp_path / "appdata"
    monkeypatch.setenv("MILLSHEET_DATA_DIR", str(d))
    return d


@pytest.fixture(autouse=True)
def memory_keyring():
    """本物のキーチェーンを呼ばない。"""
    original = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(original)


@pytest.fixture
def sample_pdf():
    if not SAMPLE_PDF.exists():
        pytest.skip("サンプル PDF がありません（社外秘のためリポジトリに含めていない）")
    return SAMPLE_PDF


def _load_raw_pages(path):
    # Task 7 で rawfile.read_raw に置き換える
    import json
    from millsheet.schema import PageEntry, PageResult
    data = json.loads(Path(path).read_text("utf-8"))
    out = []
    for file in sorted(data["pages"]):
        for e in data["pages"][file]:
            r = e["result"]
            out.append(PageEntry(file, e["page"], PageResult.model_validate(r) if r else None, e.get("error")))
    return out


@pytest.fixture
def sample_pages():
    return _load_raw_pages(FIXTURES / "sample_raw.json")


@pytest.fixture
def fixture_master():
    from millsheet.master import load_master_file
    return load_master_file(FIXTURES / "unit_weights.json")


@pytest.fixture
def sample_records(sample_pages, fixture_master):
    from millsheet.normalize import build_records
    return build_records(sample_pages, fixture_master)
