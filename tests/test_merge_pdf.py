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
