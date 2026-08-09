from pathlib import Path

import pytest

from app.services.resume_parser import ResumeParseError, parse_resume


def test_text_resume_extracts_profile_skills_and_experiences():
    path = Path(__file__).parents[1] / "fixtures" / "sample_resume.txt"
    parsed = parse_resume(path.name, path.read_bytes())
    assert parsed.profile_hints["email"] == "linze@example.com"
    assert {"Python", "SQL", "Excel", "Power BI"}.issubset(set(parsed.skills))
    assert len(parsed.experiences) >= 1


def test_rejects_unsupported_or_empty_file():
    with pytest.raises(ResumeParseError):
        parse_resume("resume.exe", b"content")
    with pytest.raises(ResumeParseError):
        parse_resume("resume.txt", b"")


def test_rejects_excessive_extracted_text(monkeypatch):
    import app.services.resume_parser as parser

    monkeypatch.setattr(parser, "MAX_EXTRACTED_CHARACTERS", 100)
    with pytest.raises(ResumeParseError, match="安全处理上限"):
        parse_resume("resume.txt", ("A" * 120).encode("utf-8"))


def test_rejects_docx_archive_with_too_many_entries(monkeypatch):
    import io
    import zipfile
    import app.services.resume_parser as parser

    monkeypatch.setattr(parser, "MAX_DOCX_ARCHIVE_ENTRIES", 1)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("[Content_Types].xml", "x")
        archive.writestr("word/document.xml", "y")
    with pytest.raises(ResumeParseError, match="内部文件数量异常"):
        parse_resume("resume.docx", payload.getvalue())


def test_rejects_pdf_with_excessive_page_count(monkeypatch):
    import app.services.resume_parser as parser

    class FakeReader:
        def __init__(self, stream):
            self.pages = [object(), object()]

    monkeypatch.setattr(parser, "PdfReader", FakeReader)
    monkeypatch.setattr(parser, "MAX_PDF_PAGES", 1)
    with pytest.raises(ResumeParseError, match="页数过多"):
        parser._parse_pdf(b"not-a-real-pdf")
