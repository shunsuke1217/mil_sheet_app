import os
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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



@pytest.fixture
def sample_pages():
    from millsheet.rawfile import read_raw
    return read_raw(FIXTURES / "sample_raw.json")[1]


@pytest.fixture
def fixture_master():
    from millsheet.master import load_master_file
    return load_master_file(FIXTURES / "unit_weights.json")


@pytest.fixture
def sample_records(sample_pages, fixture_master):
    from millsheet.normalize import build_records
    return build_records(sample_pages, fixture_master)


@pytest.fixture
def ordered_sample_dicts(sample_records):
    """例外サンプルも含めて全部を 1 回で並べたもの。"""
    from millsheet.ordering import order_records
    return [r.to_dict() for r in order_records(sample_records)[0]]


@pytest.fixture
def two_pdfs(tmp_path):
    from tests.helpers import make_pdf
    make_pdf(tmp_path / "A.pdf", 2)
    make_pdf(tmp_path / "sub/B.pdf", 1)
    return tmp_path


@pytest.fixture
def sample_folder(sample_pdf, tmp_path):
    import shutil
    d = tmp_path / "src"
    d.mkdir()
    shutil.copy(sample_pdf, d / sample_pdf.name)
    return d


@pytest.fixture
def fake_reader(sample_pdf, sample_pages):
    """サンプル PDF の各ページの PNG → sample_raw.json の結果。並列で呼ばれてもページとずれない。"""
    from tests.helpers import FakeReader, png_hash
    results = {png_hash(sample_pdf, e.page_no): e.result for e in sample_pages if e.file == sample_pdf.name}
    return FakeReader(results=results)


def _fixture_master_loader():
    from millsheet.master import load_master_file
    return load_master_file(FIXTURES / "unit_weights.json"), []


@pytest.fixture
def fixture_master_loader():
    return _fixture_master_loader
