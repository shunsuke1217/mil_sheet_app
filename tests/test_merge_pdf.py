import pymupdf
import pytest

from millsheet.merge_pdf import MergeError, merge_pages


def test_merge_pages_order(two_pdfs):
    merge_pages([("sub/B.pdf", 1), ("A.pdf", 2), ("A.pdf", 1)], two_pdfs, two_pdfs / "out.pdf")
    doc = pymupdf.open(two_pdfs / "out.pdf")
    assert [p.get_text().strip() for p in doc] == ["B-1", "A-2", "A-1"]


def test_merge_pages_missing_file(two_pdfs):
    with pytest.raises(MergeError) as e:
        merge_pages([("A.pdf", 1), ("none.pdf", 1)], two_pdfs, two_pdfs / "out.pdf")
    assert e.value.missing == ["none.pdf"] and not (two_pdfs / "out.pdf").exists()


def test_opened_sources_are_closed_when_a_file_is_missing(two_pdfs, monkeypatch):
    from millsheet import merge_pdf
    opened = []
    real_open = pymupdf.open

    def tracking_open(*a, **k):
        doc = real_open(*a, **k)
        opened.append(doc)
        return doc
    monkeypatch.setattr(merge_pdf.pymupdf, "open", tracking_open)
    with pytest.raises(MergeError):
        merge_pages([("A.pdf", 1), ("none.pdf", 1)], two_pdfs, two_pdfs / "out.pdf")
    assert opened and all(d.is_closed for d in opened)
