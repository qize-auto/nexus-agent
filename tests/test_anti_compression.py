"""Tests for AntiCompressionDetector."""

import pytest
from nexusagent.execution.anti_compression import (
    AntiCompressionDetector,
    CompressionHit,
    CompressionPattern,
)


class TestAntiCompressionDetector:
    def test_init_default_threshold(self):
        detector = AntiCompressionDetector()
        assert detector.threshold == 1

    def test_init_custom_threshold(self):
        detector = AntiCompressionDetector(threshold=3)
        assert detector.threshold == 3

    def test_detect_truncation_ellipsis(self):
        detector = AntiCompressionDetector()
        text = "Here is the code..."
        hits = detector.analyze(text)
        assert len(hits) == 1
        assert hits[0].pattern == CompressionPattern.TRUNCATION
        assert hits[0].severity == "high"

    def test_detect_omitted_bracket(self):
        detector = AntiCompressionDetector()
        text = "Details [omitted] for brevity"
        hits = detector.analyze(text)
        assert len(hits) == 1
        assert hits[0].matched_text == "[omitted]"

    def test_detect_skip(self):
        detector = AntiCompressionDetector()
        text = "We can skip this step for now"
        hits = detector.analyze(text)
        assert any(h.pattern == CompressionPattern.SKIPPING for h in hits)

    def test_detect_not_implemented(self):
        detector = AntiCompressionDetector()
        text = "def func():\n    raise NotImplementedError"
        hits = detector.analyze(text)
        assert any(h.pattern == CompressionPattern.INCOMPLETE_GENERATION for h in hits)

    def test_detect_todo(self):
        detector = AntiCompressionDetector()
        text = "# TODO: implement this later"
        hits = detector.analyze(text)
        assert any(h.pattern == CompressionPattern.INCOMPLETE_GENERATION for h in hits)

    def test_no_hits_on_clean_text(self):
        detector = AntiCompressionDetector()
        text = "This is a complete and thorough implementation."
        hits = detector.analyze(text)
        assert len(hits) == 0

    def test_is_compressed_true(self):
        detector = AntiCompressionDetector()
        assert detector.is_compressed("Some code...") is True

    def test_is_compressed_false(self):
        detector = AntiCompressionDetector()
        assert detector.is_compressed("Complete implementation here") is False

    def test_compression_score(self):
        detector = AntiCompressionDetector()
        # One high + one medium = 3 + 2 = 5
        text = "Code... and similar to above"
        score = detector.get_compression_score(text)
        assert score == 5

    def test_get_summary(self):
        detector = AntiCompressionDetector()
        text = "Code... [omitted] and skip this"
        summary = detector.get_summary(text)
        assert summary["total_hits"] == 3
        assert summary["is_compressed"] is True
        assert summary["compression_score"] >= 5  # 2 high + 1 medium

    def test_multiple_patterns_in_one_text(self):
        detector = AntiCompressionDetector()
        text = (
            "Implementation... "
            "Similar to above. "
            "TODO: add tests. "
            "Skip validation."
        )
        hits = detector.analyze(text)
        patterns = {h.pattern for h in hits}
        assert len(patterns) >= 3

    def test_case_insensitive(self):
        detector = AntiCompressionDetector()
        text = "CODE... and SKIP this"
        hits = detector.analyze(text)
        assert len(hits) == 2

    def test_position_tracking(self):
        detector = AntiCompressionDetector()
        text = "Start here... end"
        hits = detector.analyze(text)
        assert hits[0].position == 10

    def test_threshold_requires_multiple_hits(self):
        detector = AntiCompressionDetector(threshold=5)
        text = "Just..."  # Only 1 hit
        assert detector.is_compressed(text) is False

    def test_etc_not_at_end_of_line_is_low(self):
        detector = AntiCompressionDetector()
        text = "Items: a, b, etc. and more"
        hits = detector.analyze(text)
        # etc. not at end of line, shouldn't match
        assert len(hits) == 0

    def test_etc_at_end_of_line(self):
        detector = AntiCompressionDetector()
        text = "Items: a, b, etc."
        hits = detector.analyze(text)
        assert len(hits) == 1
        assert hits[0].severity == "low"
