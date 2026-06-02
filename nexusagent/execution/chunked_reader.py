"""
Forced Chunked Reader

Prevents "TL;DR" behavior by enforcing chunked reading of large content.
Ensures the agent processes all parts of a large file or long text,
rather than skipping or summarizing prematurely.

Design:
1. Content is split into fixed-size chunks
2. Each chunk must be explicitly processed
3. Missing chunks trigger a retry/reminder
4. Progress is tracked to ensure completeness
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Iterator
import time


@dataclass
class Chunk:
    """A single chunk of content."""
    index: int
    total: int
    content: str
    processed: bool = False
    processed_at: Optional[float] = None
    summary: str = ""  # Brief summary of what was found in this chunk


@dataclass
class ReadSession:
    """Tracks a complete chunked reading session."""
    session_id: str
    source: str  # file path, URL, or description
    chunks: List[Chunk] = field(default_factory=list)
    completed: bool = False
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None

    def get_unprocessed_chunks(self) -> List[Chunk]:
        return [c for c in self.chunks if not c.processed]

    def get_progress(self) -> float:
        if not self.chunks:
            return 0.0
        processed = sum(1 for c in self.chunks if c.processed)
        return processed / len(self.chunks)

    def mark_chunk_processed(self, index: int, summary: str = "") -> bool:
        for chunk in self.chunks:
            if chunk.index == index:
                chunk.processed = True
                chunk.processed_at = time.time()
                chunk.summary = summary
                # Check if all chunks are now processed
                if not self.get_unprocessed_chunks():
                    self.completed = True
                    self.completed_at = time.time()
                return True
        return False


class ForcedChunkedReader:
    """
    Enforces chunked reading to prevent skipping large content.
    """

    DEFAULT_CHUNK_SIZE = 4000  # characters per chunk
    MAX_CHUNK_SIZE = 8000

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE):
        if chunk_size > self.MAX_CHUNK_SIZE:
            chunk_size = self.MAX_CHUNK_SIZE
        self.chunk_size = chunk_size
        self._sessions: dict = {}

    def create_session(self, session_id: str, source: str, content: str) -> ReadSession:
        """Create a new reading session by splitting content into chunks."""
        chunks = self._split_content(content)
        session = ReadSession(
            session_id=session_id,
            source=source,
            chunks=chunks
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ReadSession]:
        return self._sessions.get(session_id)

    def _split_content(self, content: str) -> List[Chunk]:
        """Split content into chunks, trying to break at natural boundaries."""
        chunks = []
        total = max(1, (len(content) + self.chunk_size - 1) // self.chunk_size)

        start = 0
        index = 0
        while start < len(content):
            end = min(start + self.chunk_size, len(content))

            # Try to find a natural break point
            if end < len(content):
                # Look for paragraph break
                para_break = content.rfind("\n\n", start, end)
                if para_break > start + self.chunk_size // 2:
                    end = para_break + 2
                else:
                    # Look for single newline
                    line_break = content.rfind("\n", start, end)
                    if line_break > start + self.chunk_size // 2:
                        end = line_break + 1
                    else:
                        # Look for sentence end
                        sentence_end = max(
                            content.rfind(". ", start, end),
                            content.rfind("? ", start, end),
                            content.rfind("! ", start, end),
                        )
                        if sentence_end > start + self.chunk_size // 2:
                            end = sentence_end + 2

            chunk_content = content[start:end]
            chunks.append(Chunk(
                index=index,
                total=total,
                content=chunk_content
            ))
            start = end
            index += 1

        # Update total counts after final split
        for chunk in chunks:
            chunk.total = len(chunks)

        return chunks

    def get_next_chunk(self, session_id: str) -> Optional[Chunk]:
        """Get the next unprocessed chunk."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        unprocessed = session.get_unprocessed_chunks()
        return unprocessed[0] if unprocessed else None

    def mark_processed(self, session_id: str, chunk_index: int, summary: str = "") -> bool:
        """Mark a chunk as processed."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        return session.mark_chunk_processed(chunk_index, summary)

    def is_complete(self, session_id: str) -> bool:
        """Check if all chunks have been processed."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        return session.completed

    def get_progress(self, session_id: str) -> float:
        """Get reading progress (0.0 to 1.0)."""
        session = self._sessions.get(session_id)
        if not session:
            return 0.0
        return session.get_progress()

    def get_missing_chunks_report(self, session_id: str) -> Optional[str]:
        """Generate a report of unprocessed chunks for retry prompts."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        unprocessed = session.get_unprocessed_chunks()
        if not unprocessed:
            return None

        indices = [c.index for c in unprocessed]
        report = (
            f"WARNING: Reading incomplete for '{session.source}'. "
            f"{len(unprocessed)}/{len(session.chunks)} chunks unprocessed. "
            f"Missing chunk indices: {indices}. "
            f"You MUST process all chunks before proceeding."
        )
        return report

    def get_full_summary(self, session_id: str) -> str:
        """Get combined summary from all processed chunks."""
        session = self._sessions.get(session_id)
        if not session:
            return ""
        summaries = []
        for chunk in sorted(session.chunks, key=lambda c: c.index):
            if chunk.summary:
                summaries.append(f"[Chunk {chunk.index + 1}/{chunk.total}] {chunk.summary}")
        return "\n".join(summaries)

    def requires_chunked_reading(self, content: str) -> bool:
        """Check if content is large enough to require chunked reading."""
        return len(content) > self.chunk_size

    def to_tool_spec(self) -> Dict[str, Any]:
        """工具规格 — 供 ToolRegistry 扫描注册"""
        return {
            "name": "chunked_read",
            "description": (
                "强制分块读取大文件或长文本，确保不跳过任何内容。 "
                "适用于超过 4000 字符的文件读取场景，优先于普通文件读取工具。"
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "要分块读取的文本内容"},
                    "source": {"type": "string", "description": "内容来源标识（如文件路径）"},
                },
                "required": ["content", "source"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "chunks_count": {"type": "integer"},
                    "chunk_size": {"type": "integer"},
                },
            },
        }

    async def invoke(self, content: str, source: str = "unknown") -> Dict[str, Any]:
        """工具调用入口 — 创建分块读取会话"""
        import uuid
        session_id = f"chunk_{uuid.uuid4().hex[:8]}"
        session = self.create_session(session_id, source, content)
        return {
            "session_id": session_id,
            "chunks_count": len(session.chunks),
            "chunk_size": self.chunk_size,
            "first_chunk": session.chunks[0].content if session.chunks else "",
            "requires_chunked_reading": self.requires_chunked_reading(content),
        }

    def iter_chunks(self, session_id: str) -> Iterator[Chunk]:
        """Iterate over all chunks in a session."""
        session = self._sessions.get(session_id)
        if session:
            yield from session.chunks
