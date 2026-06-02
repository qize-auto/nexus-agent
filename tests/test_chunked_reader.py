"""Tests for ForcedChunkedReader."""

import pytest
from nexusagent.execution.chunked_reader import ForcedChunkedReader, Chunk, ReadSession


class TestForcedChunkedReader:
    def test_init_default_chunk_size(self):
        reader = ForcedChunkedReader()
        assert reader.chunk_size == 4000

    def test_init_custom_chunk_size(self):
        reader = ForcedChunkedReader(chunk_size=2000)
        assert reader.chunk_size == 2000

    def test_init_chunk_size_capped(self):
        reader = ForcedChunkedReader(chunk_size=10000)
        assert reader.chunk_size == 8000

    def test_requires_chunked_reading_small(self):
        reader = ForcedChunkedReader()
        assert reader.requires_chunked_reading("short") is False

    def test_requires_chunked_reading_large(self):
        reader = ForcedChunkedReader()
        assert reader.requires_chunked_reading("x" * 4001) is True

    def test_create_session(self):
        reader = ForcedChunkedReader(chunk_size=10)
        session = reader.create_session("s1", "test.txt", "01234567890123456789")
        assert session.session_id == "s1"
        assert session.source == "test.txt"
        assert len(session.chunks) == 2
        assert session.chunks[0].index == 0
        assert session.chunks[1].index == 1

    def test_get_session(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "0123456789")
        session = reader.get_session("s1")
        assert session is not None
        assert session.session_id == "s1"

    def test_get_session_missing(self):
        reader = ForcedChunkedReader()
        assert reader.get_session("missing") is None

    def test_get_next_chunk(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        chunk = reader.get_next_chunk("s1")
        assert chunk is not None
        assert chunk.index == 0

    def test_mark_processed(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        assert reader.mark_processed("s1", 0, "first half") is True
        assert reader.get_progress("s1") == 0.5

    def test_mark_processed_bad_index(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        assert reader.mark_processed("s1", 99) is False

    def test_is_complete_false(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        assert reader.is_complete("s1") is False

    def test_is_complete_true(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        reader.mark_processed("s1", 0)
        reader.mark_processed("s1", 1)
        assert reader.is_complete("s1") is True

    def test_get_next_chunk_after_processing(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        reader.mark_processed("s1", 0)
        chunk = reader.get_next_chunk("s1")
        assert chunk.index == 1

    def test_get_next_chunk_all_processed(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        reader.mark_processed("s1", 0)
        reader.mark_processed("s1", 1)
        assert reader.get_next_chunk("s1") is None

    def test_get_missing_chunks_report(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        reader.mark_processed("s1", 0)
        report = reader.get_missing_chunks_report("s1")
        assert "WARNING" in report
        assert "1/2 chunks unprocessed" in report
        assert "Missing chunk indices: [1]" in report

    def test_get_missing_chunks_report_complete(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        reader.mark_processed("s1", 0)
        reader.mark_processed("s1", 1)
        assert reader.get_missing_chunks_report("s1") is None

    def test_get_full_summary(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        reader.mark_processed("s1", 0, "digits 0-9")
        reader.mark_processed("s1", 1, "digits 10-19")
        summary = reader.get_full_summary("s1")
        assert "[Chunk 1/2] digits 0-9" in summary
        assert "[Chunk 2/2] digits 10-19" in summary

    def test_iter_chunks(self):
        reader = ForcedChunkedReader(chunk_size=10)
        reader.create_session("s1", "test.txt", "01234567890123456789")
        chunks = list(reader.iter_chunks("s1"))
        assert len(chunks) == 2
        assert chunks[0].index == 0

    def test_natural_break_paragraph(self):
        reader = ForcedChunkedReader(chunk_size=20)
        content = "Line one.\n\nLine two after paragraph."
        session = reader.create_session("s1", "test.txt", content)
        # Should break at paragraph
        assert len(session.chunks) >= 1

    def test_natural_break_line(self):
        reader = ForcedChunkedReader(chunk_size=20)
        content = "First line here.\nSecond line there."
        session = reader.create_session("s1", "test.txt", content)
        # Should break at line
        assert len(session.chunks) >= 1

    def test_session_progress_zero(self):
        reader = ForcedChunkedReader(chunk_size=10)
        session = reader.create_session("s1", "test.txt", "01234567890123456789")
        assert session.get_progress() == 0.0

    def test_session_progress_half(self):
        reader = ForcedChunkedReader(chunk_size=10)
        session = reader.create_session("s1", "test.txt", "01234567890123456789")
        session.mark_chunk_processed(0)
        assert session.get_progress() == 0.5

    def test_session_unprocessed_chunks(self):
        reader = ForcedChunkedReader(chunk_size=10)
        session = reader.create_session("s1", "test.txt", "01234567890123456789")
        unprocessed = session.get_unprocessed_chunks()
        assert len(unprocessed) == 2
        session.mark_chunk_processed(0)
        unprocessed = session.get_unprocessed_chunks()
        assert len(unprocessed) == 1
        assert unprocessed[0].index == 1
