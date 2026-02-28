"""Unit tests for PDF splitting behavior."""

from pathlib import Path

from pdf_splitter.models import Chapter
from pdf_splitter.splitter import PDFSplitter


class _FakeSourceDoc:
    metadata = {"author": "A. Writer", "producer": "tool"}

    def close(self):
        pass


class _FakeNewDoc:
    def __init__(self):
        self.metadata_calls = []

    def insert_pdf(self, *_args, **_kwargs):
        pass

    def set_metadata(self, data):
        self.metadata_calls.append(data)

    def save(self, _path):
        pass

    def close(self):
        pass


class _FakeFitz:
    def __init__(self):
        self.source_doc = _FakeSourceDoc()
        self.new_docs = []

    def open(self, path=None):
        if path is None:
            doc = _FakeNewDoc()
            self.new_docs.append(doc)
            return doc
        return self.source_doc


def test_split_preserves_existing_metadata_when_setting_chapter_title(tmp_path, monkeypatch):
    fake_fitz = _FakeFitz()
    monkeypatch.setattr("pdf_splitter.splitter.fitz", fake_fitz)

    splitter = PDFSplitter(output_dir=tmp_path)
    chapters = [Chapter(title="Chapter 1", start_page=1, end_page=3)]

    splitter.split(pdf_path=Path("book.pdf"), chapters=chapters, preserve_metadata=True)

    saved_doc = fake_fitz.new_docs[0]
    assert len(saved_doc.metadata_calls) == 1
    assert saved_doc.metadata_calls[0]["title"] == "Chapter 1"
    assert saved_doc.metadata_calls[0]["author"] == "A. Writer"
    assert saved_doc.metadata_calls[0]["producer"] == "tool"
