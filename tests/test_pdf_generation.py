"""Tests for PDF generation utilities (merge_pdfs from pdf_templates)."""

import os
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _create_simple_pdf(path, text="Test page"):
    """Create a minimal one-page PDF using reportlab."""
    c = canvas.Canvas(str(path), pagesize=letter)
    c.drawString(72, 720, text)
    c.save()


class TestMergePdfs:
    def test_merge_pdfs_combines_files(self, tmp_path):
        from pdf_templates import merge_pdfs

        pdf1 = tmp_path / "a.pdf"
        pdf2 = tmp_path / "b.pdf"
        _create_simple_pdf(pdf1, "Page A")
        _create_simple_pdf(pdf2, "Page B")

        output = str(tmp_path / "merged.pdf")
        result = merge_pdfs([str(pdf1), str(pdf2)], output)

        assert result == output
        assert os.path.exists(output)
        # Verify it is a valid PDF (starts with %PDF)
        with open(output, "rb") as f:
            header = f.read(5)
        assert header == b"%PDF-"

    def test_merge_pdfs_cleans_up_temps(self, tmp_path):
        from pdf_templates import merge_pdfs

        pdf1 = tmp_path / "temp1.pdf"
        pdf2 = tmp_path / "temp2.pdf"
        _create_simple_pdf(pdf1, "Temp 1")
        _create_simple_pdf(pdf2, "Temp 2")

        output = str(tmp_path / "merged.pdf")
        merge_pdfs([str(pdf1), str(pdf2)], output)

        # Source PDFs should be deleted after merge
        assert not os.path.exists(str(pdf1))
        assert not os.path.exists(str(pdf2))

    def test_merge_pdfs_empty_list(self, tmp_path):
        from pdf_templates import merge_pdfs

        output = str(tmp_path / "merged.pdf")
        result = merge_pdfs([], output)

        assert result is None
        assert not os.path.exists(output)
