"""
Work Memory — Persistent Execution Context

Prevents "pretend amnesia" by persisting full execution context.
When REVER self-reflection triggers a retry, WorkMemory ensures
all previous steps, evidence, and outputs are retained and accessible.

Design:
1. Snapshot-based persistence of execution state
2. Indexed retrieval by task, step, or evidence type
3. Deduplication to prevent identical retries
4. Cycle detection to prevent infinite loops
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .tracker import TaskContext


@dataclass
class MemorySnapshot:
    """A snapshot of execution state at a point in time."""
    snapshot_id: str
    task_id: str
    timestamp: float
    task_context: TaskContext
    output: str
    validation_issues: List[str] = field(default_factory=list)
    retry_count: int = 0
    snapshot_hash: str = ""  # For deduplication

    def __post_init__(self):
        if not self.snapshot_hash:
            self.snapshot_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        content = f"{self.task_id}:{self.output}:{','.join(self.validation_issues)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class WorkMemory:
    """
    Persistent work memory for execution context.
    """

    def __init__(self, max_snapshots_per_task: int = 10):
        self.max_snapshots = max_snapshots_per_task
        self._snapshots: Dict[str, List[MemorySnapshot]] = {}  # task_id -> snapshots
        self._snapshot_hashes: Dict[str, Set[str]] = {}  # task_id -> hashes

    def save_snapshot(
        self,
        task_id: str,
        task_context: TaskContext,
        output: str,
        validation_issues: Optional[List[str]] = None,
        retry_count: int = 0
    ) -> MemorySnapshot:
        """Save a snapshot of current execution state."""
        snapshot = MemorySnapshot(
            snapshot_id=f"{task_id}_{int(time.time() * 1000)}",
            task_id=task_id,
            timestamp=time.time(),
            task_context=task_context,
            output=output,
            validation_issues=validation_issues or [],
            retry_count=retry_count
        )

        if task_id not in self._snapshots:
            self._snapshots[task_id] = []
            self._snapshot_hashes[task_id] = set()

        self._snapshots[task_id].append(snapshot)
        self._snapshot_hashes[task_id].add(snapshot.snapshot_hash)

        # Prune old snapshots
        if len(self._snapshots[task_id]) > self.max_snapshots:
            removed = self._snapshots[task_id].pop(0)
            # Only remove hash if no other snapshot has it
            if not any(s.snapshot_hash == removed.snapshot_hash
                       for s in self._snapshots[task_id]):
                self._snapshot_hashes[task_id].discard(removed.snapshot_hash)

        return snapshot

    def get_snapshots(self, task_id: str) -> List[MemorySnapshot]:
        """Get all snapshots for a task, oldest first."""
        return list(self._snapshots.get(task_id, []))

    def get_latest_snapshot(self, task_id: str) -> Optional[MemorySnapshot]:
        """Get the most recent snapshot for a task."""
        snapshots = self._snapshots.get(task_id)
        return snapshots[-1] if snapshots else None

    def is_duplicate(self, task_id: str, output: str, issues: Optional[List[str]] = None) -> bool:
        """Check if this output+issues combination was already saved."""
        test_snapshot = MemorySnapshot(
            snapshot_id="test",
            task_id=task_id,
            timestamp=0,
            task_context=TaskContext(task_id=task_id, user_message=""),
            output=output,
            validation_issues=issues or []
        )
        hashes = self._snapshot_hashes.get(task_id, set())
        return test_snapshot.snapshot_hash in hashes

    def detect_cycle(self, task_id: str, max_repeats: int = 3) -> bool:
        """Detect if the same hash has appeared too many times (cycle)."""
        snapshots = self._snapshots.get(task_id, [])
        if not snapshots:
            return False

        from collections import Counter
        hash_counts = Counter(s.snapshot_hash for s in snapshots)
        most_common = hash_counts.most_common(1)[0]
        return most_common[1] >= max_repeats

    def get_memory_for_retry(self, task_id: str) -> str:
        """
        Generate a memory prompt for retry scenarios.
        Summarizes what was done before and what failed.
        """
        snapshots = self._snapshots.get(task_id, [])
        if not snapshots:
            return ""

        lines = [
            f"=== PREVIOUS ATTEMPTS ({len(snapshots)}) ===",
            "",
        ]

        for i, snap in enumerate(snapshots, 1):
            lines.append(f"Attempt #{i} (retry #{snap.retry_count}):")
            if snap.validation_issues:
                lines.append(f"  Issues found: {', '.join(snap.validation_issues)}")
            else:
                lines.append("  No validation issues recorded.")
            lines.append(f"  Output length: {len(snap.output)} chars")
            lines.append("")

        latest = snapshots[-1]
        lines.extend([
            "=== WHAT YOU MUST FIX ===",
            "",
        ])

        if latest.validation_issues:
            lines.append("The following issues were detected in your last attempt:")
            for issue in latest.validation_issues:
                lines.append(f"  - {issue}")
        else:
            lines.append("Your previous attempt was rejected for completeness concerns.")

        lines.extend([
            "",
            "IMPORTANT: Do NOT repeat the same mistakes. "
            "Address ALL listed issues in this attempt. "
            "The previous outputs are preserved in memory — "
            "you cannot claim ignorance of prior work.",
        ])

        return "\n".join(lines)

    def get_execution_trace(self, task_id: str) -> str:
        """Get a full execution trace for debugging."""
        snapshots = self._snapshots.get(task_id, [])
        if not snapshots:
            return "No execution history."

        lines = [f"Execution trace for task '{task_id}':"]
        for snap in snapshots:
            lines.append(
                f"  [{snap.timestamp:.0f}] Retry #{snap.retry_count}, "
                f"{len(snap.task_context.plan_steps)} steps, "
                f"{len(snap.validation_issues)} issues"
            )
        return "\n".join(lines)

    def clear(self, task_id: str) -> bool:
        """Clear all snapshots for a task."""
        if task_id in self._snapshots:
            del self._snapshots[task_id]
            del self._snapshot_hashes[task_id]
            return True
        return False

    def get_retry_count(self, task_id: str) -> int:
        """Get the number of retries for a task."""
        snapshots = self._snapshots.get(task_id, [])
        if not snapshots:
            return 0
        return max(s.retry_count for s in snapshots)
