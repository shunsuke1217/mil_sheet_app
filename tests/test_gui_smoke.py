from pathlib import Path
from unittest.mock import Mock

from gui.main_window import MainWindow
from gui.master_dialog import MasterDialog
from gui.settings_dialog import SettingsDialog
from millsheet.master import load_master_file
from millsheet.settings import get_secret, load_settings


def test_main_window_opens(qtbot):
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    assert w.run_button.isEnabled() is False          # フォルダと出力先が決まるまで押せない


def test_main_window_enables_run(qtbot, tmp_path):
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    w.set_source_dir(tmp_path); w.set_output_path(tmp_path / "o.xlsx")
    assert w.run_button.isEnabled()


def test_main_window_output_gets_xlsx_suffix(qtbot, tmp_path):
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    w.set_output_path(tmp_path / "結果")
    assert w.output_edit.text().endswith("結果.xlsx")


def test_settings_dialog_saves_without_writing_keys_to_file(qtbot, data_dir):
    d = SettingsDialog(); qtbot.addWidget(d)
    d.gemini_key_edit.setText("GKEY123"); d.sheet_url_edit.setText("https://docs.google.com/spreadsheets/d/x/edit")
    d.accept()
    assert get_secret("gemini_api_key") == "GKEY123"
    assert load_settings().sheet_url == "https://docs.google.com/spreadsheets/d/x/edit"
    assert "GKEY123" not in (data_dir / "settings.json").read_text("utf-8")


def test_settings_dialog_blank_key_keeps_existing(qtbot):
    from millsheet.settings import set_secret
    set_secret("google_api_key", "OLD")
    d = SettingsDialog(); qtbot.addWidget(d)
    d.accept()
    assert get_secret("google_api_key") == "OLD"


def test_master_dialog_filters(qtbot):
    d = MasterDialog(load_master_file(Path("tests/fixtures/unit_weights.json"))); qtbot.addWidget(d)
    assert d.visible_row_count() == 225
    d.category_combo.setCurrentText("FB")
    assert d.visible_row_count() == 36
    d.category_combo.setCurrentIndex(0); d.search_edit.setText("200×200")
    assert 0 < d.visible_row_count() < 225


def test_run_worker_rebuild_emits_result(qtbot, tmp_path):
    import shutil
    from gui.worker import RunWorker
    from millsheet.settings import Settings
    from tests.conftest import _fixture_master_loader
    shutil.copy("tests/fixtures/sample_raw.json", tmp_path / "o_raw.json")
    w = RunWorker("rebuild", raw=tmp_path / "o_raw.json", xlsx=tmp_path / "o.xlsx", settings=Settings(),
                  google_key="", master_loader=_fixture_master_loader)
    with qtbot.waitSignal(w.finished_ok, timeout=10000) as sig:
        w.start()
    assert len(sig.args[0].records) == 13 and (tmp_path / "o.xlsx").exists()


def test_run_worker_reports_friendly_error(qtbot, tmp_path):
    from gui.worker import RunWorker
    from millsheet.settings import Settings
    w = RunWorker("run", source_dir=tmp_path, xlsx=tmp_path / "o.xlsx", settings=Settings(),
                  gemini_key="", google_key="")
    with qtbot.waitSignal(w.failed, timeout=10000) as sig:
        w.start()
    assert "Gemini の API キー" in sig.args[0]


def test_review_list_copy(qtbot):
    from PySide6.QtGui import QGuiApplication
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    w.review_list.addItems(["a.pdf の 1 ページ目", "b.pdf の 2 ページ目"])
    w.review_list.selectAll()
    w.copy_selected_reviews()
    assert QGuiApplication.clipboard().text() == "a.pdf の 1 ページ目\nb.pdf の 2 ページ目"


# I3
def test_refresh_master_twice_keeps_running_worker(qtbot, monkeypatch, data_dir):
    import time as _t
    from gui import worker as wmod
    from millsheet.settings import Settings, save_settings, set_secret
    save_settings(Settings(sheet_url="https://docs.google.com/spreadsheets/d/x/edit")); set_secret("google_api_key", "k")
    monkeypatch.setattr(wmod.MasterWorker, "run", lambda self: _t.sleep(0.3))
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    w.refresh_master(); first = w.master_worker
    w.refresh_master()
    assert first in w._master_workers or first is w.master_worker
    qtbot.waitUntil(lambda: not first.isRunning(), timeout=3000)


# I4
def test_new_folder_updates_auto_output(qtbot, tmp_path):
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    (tmp_path / "A").mkdir(); (tmp_path / "B").mkdir()
    w.set_source_dir(tmp_path / "A"); w.set_source_dir(tmp_path / "B")
    assert w.output_edit.text().endswith("B.xlsx")


def test_user_chosen_output_is_kept(qtbot, tmp_path):
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    (tmp_path / "A").mkdir(); (tmp_path / "B").mkdir()
    w.set_source_dir(tmp_path / "A"); w.output_edit.setText(str(tmp_path / "mine.xlsx"))
    w.set_source_dir(tmp_path / "B")
    assert w.output_edit.text().endswith("mine.xlsx")


def test_existing_output_asks_before_overwrite(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    (tmp_path / "A").mkdir(); (tmp_path / "A.xlsx").write_text("x")
    w = MainWindow(fetch_on_start=False); qtbot.addWidget(w)
    w.set_source_dir(tmp_path / "A")
    asked = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "question", asked)
    w._start_run()
    assert asked.called and w.worker is None
