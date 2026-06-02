"""
Anti-Compression Detector

Detects agent laziness behaviors:
1. Output truncation (e.g., "...", "etc.", "omitted")
2. Excessive summarization without key details
3. Skipping implementation steps ("already done", "similar to above")
4. Premature task termination claims
5. Incomplete file generation
"""

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


class CompressionPattern(Enum):
    TRUNCATION = auto()
    SUMMARIZATION = auto()
    SKIPPING = auto()
    PREMATURE_TERMINATION = auto()
    INCOMPLETE_GENERATION = auto()


@dataclass
class CompressionHit:
    pattern: CompressionPattern
    matched_text: str
    severity: str  # "low", "medium", "high"
    description: str
    position: Optional[int] = None


class AntiCompressionDetector:
    """Detects compression/laziness patterns in agent outputs."""

    PATTERNS = {
        CompressionPattern.TRUNCATION: [
            (r"\.\.\.(?![a-zA-Z])", "high", "Ellipsis indicating truncation"),
            (r"\[\.\.\.\]", "high", "Bracketed ellipsis"),
            (r"\(omitted\)", "high", "Explicit omission marker"),
            (r"\[omitted\]", "high", "Explicit omission marker"),
            (r"truncated", "high", "Explicit truncation claim"),
            (r"cut off", "medium", "Truncation indicator"),
        ],
        CompressionPattern.SUMMARIZATION: [
            (r"similar (?:to|with) (?:the )?(?:above|previous)", "medium", "Avoiding repetition by reference"),
            (r"same as (?:the )?(?:above|before)", "medium", "Avoiding repetition by reference"),
            (r"etc\.\s*$", "low", "Etc. at end of line"),
            (r"and (?:so on|so forth)", "low", "Vague continuation"),
            (r"remaining (?:parts|steps|sections)", "medium", "Vague reference to remaining work"),
        ],
        CompressionPattern.SKIPPING: [
            (r"(?:already |previously )?(?:done|implemented|handled)", "medium", "Claiming work was already done"),
            (r"skip(?:ping|ped)?", "high", "Explicit skip instruction"),
            (r"(?:not |no )?(?:need|necessary) to", "medium", "Claiming step is unnecessary"),
            (r"(?:^|\s)(?:can be |could be )?(?:left|omitted|skipped)(?=$|\s|[.,;:!])", "high", "Suggesting omission"),
        ],
        CompressionPattern.PREMATURE_TERMINATION: [
            (r"task complete[d]?", "low", "Task completion claim"),
            (r"(?:that's|that is) (?:it|all)", "medium", "Premature ending indicator"),
            (r"(?:done|finished) (?:here|now)", "low", "Premature ending indicator"),
        ],
        CompressionPattern.INCOMPLETE_GENERATION: [
            (r"(?:TODO|FIXME|HACK|XXX):", "high", "Incomplete marker in generated content"),
            (r"placeholder", "medium", "Placeholder in generated content"),
            (r"stub", "medium", "Stub implementation"),
            (r"not implemented", "high", "Explicit unimplemented marker"),
            (r"raise NotImplementedError", "high", "Not implemented error"),
        ],
    }

    def __init__(self, threshold: int = 1):
        self.threshold = threshold

    def analyze(self, text: str) -> List[CompressionHit]:
        hits = []
        for pattern_type, patterns in self.PATTERNS.items():
            for regex, severity, description in patterns:
                for match in re.finditer(regex, text, re.IGNORECASE):
                    hits.append(CompressionHit(
                        pattern=pattern_type,
                        matched_text=match.group(),
                        severity=severity,
                        description=description,
                        position=match.start()
                    ))
        return hits

    def is_compressed(self, text: str) -> bool:
        hits = self.analyze(text)
        return len(hits) >= self.threshold

    def get_compression_score(self, text: str) -> int:
        hits = self.analyze(text)
        score = 0
        for hit in hits:
            if hit.severity == "high":
                score += 3
            elif hit.severity == "medium":
                score += 2
            else:
                score += 1
        return score

    def get_summary(self, text: str) -> dict:
        hits = self.analyze(text)
        by_pattern = {}
        for hit in hits:
            by_pattern.setdefault(hit.pattern.name, []).append(hit)
        return {
            "total_hits": len(hits),
            "compression_score": self.get_compression_score(text),
            "is_compressed": self.is_compressed(text),
            "by_pattern": {k: len(v) for k, v in by_pattern.items()},
            "high_severity_count": sum(1 for h in hits if h.severity == "high"),
        }
