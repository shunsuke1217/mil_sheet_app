import shutil
from pathlib import Path
from unittest.mock import Mock

from gui.main_window import MainWindow
from gui.master_dialog import MasterDialog
from gui.settings_dialog import SettingsDialog
from millsheet.master import load_master_file
from millsheet.settings import get_secret, load_settings


def test_main_window_opens(qtbot):
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    assert w.run_button.isEnabled() is False          # フォルダと出力先が決まるまで押せない


def test_main_window_enables_run(qtbot, tmp_path):
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    (tmp_path / "現場A").mkdir()
    w.set_source_dir(tmp_path / "現場A")
    assert w.run_button.isEnabled()
    # 設定の出力先が空欄なら PDF のフォルダの隣。同じ名前にならないよう「_出力」を付ける
    assert w.output_name_edit.text() == "現場A_出力" and w.output_dir() == tmp_path / "現場A_出力"


def test_output_folder_uses_settings_base(qtbot, tmp_path):
    from millsheet.settings import Settings, save_settings
    save_settings(Settings(output_path=str(tmp_path / "出力")))
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    (tmp_path / "現場A").mkdir()
    w.set_source_dir(tmp_path / "現場A")
    assert w.output_name_edit.text() == "現場A"
    w.output_name_edit.setText("2026-10 現場A")
    assert w.output_dir() == tmp_path / "出力/2026-10 現場A"


def test_invalid_folder_name_disables_run(qtbot, tmp_path):
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_source_dir(tmp_path)
    for bad in ("", "a/b", "a:b", "..", "  "):
        w.output_name_edit.setText(bad)
        assert not w.run_button.isEnabled(), bad


def test_output_inside_source_folder_is_refused(qtbot, tmp_path):
    from millsheet.settings import Settings, save_settings
    (tmp_path / "A").mkdir()
    save_settings(Settings(output_path=str(tmp_path / "A")))
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_source_dir(tmp_path / "A")
    assert not w.run_button.isEnabled() and "PDF のフォルダの中" in w.output_path_label.text()


def test_settings_dialog_saves_without_writing_keys_to_file(qtbot, data_dir):
    d = SettingsDialog(); qtbot.addWidget(d)
    d.gemini_key_edit.setText("GKEY123"); d.sheet_url_edit.setText("https://docs.google.com/spreadsheets/d/x/edit")
    d.accept()
    assert get_secret("gemini_api_key") == "GKEY123"
    assert load_settings().sheet_url == "https://docs.google.com/spreadsheets/d/x/edit"
    assert "GKEY123" not in (data_dir / "settings.json").read_text("utf-8")


def test_settings_dialog_blank_key_keeps_existing(qtbot):
    from millsheet.settings import set_secret
    set_secret("gemini_api_key", "OLD")
    d = SettingsDialog(); qtbot.addWidget(d)
    d.accept()
    assert get_secret("gemini_api_key") == "OLD"


def test_settings_dialog_needs_only_gemini_key_and_sheet_url(qtbot):
    d = SettingsDialog(); qtbot.addWidget(d)
    assert not hasattr(d, "google_key_edit") and not hasattr(d, "sheet_name_edit")


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
    (tmp_path / "o/作業データ").mkdir(parents=True)
    shutil.copy("tests/fixtures/sample_raw.json", tmp_path / "o/作業データ/o_raw.json")
    w = RunWorker("rebuild", out_dir=tmp_path / "o", settings=Settings(), master_loader=_fixture_master_loader)
    with qtbot.waitSignal(w.finished_ok, timeout=10000) as sig:
        w.start()
    assert len(sig.args[0].records) == 13 and (tmp_path / "o/o.xlsx").exists()


def test_run_worker_reports_friendly_error(qtbot, tmp_path):
    from gui.worker import RunWorker
    from millsheet.settings import Settings
    w = RunWorker("run", source_dir=tmp_path, out_dir=tmp_path / "o", settings=Settings(),
                  gemini_key="")
    with qtbot.waitSignal(w.failed, timeout=10000) as sig:
        w.start()
    assert "Gemini の API キー" in sig.args[0]


def test_review_list_copy(qtbot):
    from PySide6.QtGui import QGuiApplication
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    w.review_list.addItems(["a.pdf の 1 ページ目", "b.pdf の 2 ページ目"])
    w.review_list.selectAll()
    w.copy_selected_reviews()
    assert QGuiApplication.clipboard().text() == "a.pdf の 1 ページ目\nb.pdf の 2 ページ目"


# I3
def test_refresh_master_twice_keeps_running_worker(qtbot, monkeypatch, data_dir):
    import time as _t
    from gui import worker as wmod
    from millsheet.settings import Settings, save_settings
    save_settings(Settings(sheet_url="https://docs.google.com/spreadsheets/d/x/edit"))
    monkeypatch.setattr(wmod.MasterWorker, "run", lambda self: _t.sleep(0.3))
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    w.refresh_master(); first = w.master_worker
    w.refresh_master()
    assert first in w._master_workers or first is w.master_worker
    qtbot.waitUntil(lambda: not first.isRunning(), timeout=3000)


# I4
def test_new_folder_updates_auto_output(qtbot, tmp_path):
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    (tmp_path / "A").mkdir(); (tmp_path / "B").mkdir()
    w.set_source_dir(tmp_path / "A"); w.set_source_dir(tmp_path / "B")
    assert w.output_name_edit.text() == "B_出力"


def test_user_chosen_output_is_kept(qtbot, tmp_path):
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    (tmp_path / "A").mkdir(); (tmp_path / "B").mkdir()
    w.set_source_dir(tmp_path / "A"); w.output_name_edit.setText("自分で付けた名前")
    w.set_source_dir(tmp_path / "B")
    assert w.output_name_edit.text() == "自分で付けた名前"


def test_existing_output_asks_before_overwrite(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    (tmp_path / "A").mkdir(); (tmp_path / "A_出力").mkdir(); (tmp_path / "A_出力/A_出力.xlsx").write_text("x")
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_source_dir(tmp_path / "A")
    asked = Mock(return_value=QMessageBox.StandardButton.No)
    monkeypatch.setattr(QMessageBox, "question", asked)
    w._start_run()
    assert asked.called and w.worker is None


def test_output_base_chosen_on_main_window_is_remembered(qtbot, tmp_path):
    from millsheet.settings import load_settings
    (tmp_path / "現場A").mkdir()
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    w.set_source_dir(tmp_path / "現場A")
    w.set_output_base(tmp_path / "出力")
    assert w.output_dir() == tmp_path / "出力/現場A"     # PDF の隣ではなくなったので「_出力」は付けない
    assert load_settings().output_path == str(tmp_path / "出力")
    assert str(tmp_path / "出力") in w.output_base_label.text()
    w2 = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w2)
    assert str(tmp_path / "出力") in w2.output_base_label.text()


def test_output_base_label_when_unset(qtbot):
    w = MainWindow(fetch_on_start=False, open_folder_on_finish=False); qtbot.addWidget(w)
    assert "PDF のフォルダの隣" in w.output_base_label.text()


def test_master_dialog_uses_material_type_wording(qtbot):
    d = MasterDialog(load_master_file(Path("tests/fixtures/unit_weights.json"))); qtbot.addWidget(d)
    assert d.table.horizontalHeaderItem(0).text() == "材種" and d.category_combo.itemText(0) == "すべての材種"
