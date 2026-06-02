"""Tests for WorkMemory."""

import pytest
from nexusagent.execution.work_memory import WorkMemory, MemorySnapshot
from nexusagent.execution.tracker import TaskContext


class TestWorkMemory:
    def test_init(self):
        memory = WorkMemory()
        assert memory.max_snapshots == 10

    def test_save_snapshot(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        snapshot = memory.save_snapshot("t1", ctx, "output")
        assert snapshot.task_id == "t1"
        assert snapshot.output == "output"
        assert snapshot.snapshot_hash

    def test_get_snapshots(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output1")
        memory.save_snapshot("t1", ctx, "output2")
        snapshots = memory.get_snapshots("t1")
        assert len(snapshots) == 2
        assert snapshots[0].output == "output1"
        assert snapshots[1].output == "output2"

    def test_get_snapshots_empty(self):
        memory = WorkMemory()
        assert memory.get_snapshots("missing") == []

    def test_get_latest_snapshot(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output1")
        memory.save_snapshot("t1", ctx, "output2")
        latest = memory.get_latest_snapshot("t1")
        assert latest.output == "output2"

    def test_get_latest_snapshot_missing(self):
        memory = WorkMemory()
        assert memory.get_latest_snapshot("missing") is None

    def test_is_duplicate_true(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output", ["issue1"])
        assert memory.is_duplicate("t1", "output", ["issue1"]) is True

    def test_is_duplicate_false(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output1")
        assert memory.is_duplicate("t1", "output2") is False

    def test_detect_cycle_false(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output1")
        memory.save_snapshot("t1", ctx, "output2")
        assert memory.detect_cycle("t1", max_repeats=3) is False

    def test_detect_cycle_true(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        for _ in range(3):
            memory.save_snapshot("t1", ctx, "same_output")
        assert memory.detect_cycle("t1", max_repeats=3) is True

    def test_detect_cycle_different_tasks(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        for _ in range(3):
            memory.save_snapshot("t1", ctx, "same_output")
        # Different task should not detect cycle
        assert memory.detect_cycle("t2", max_repeats=3) is False

    def test_get_memory_for_retry(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output", ["missing code"], retry_count=0)
        prompt = memory.get_memory_for_retry("t1")
        assert "PREVIOUS ATTEMPTS" in prompt
        assert "missing code" in prompt
        assert "WHAT YOU MUST FIX" in prompt

    def test_get_memory_for_retry_empty(self):
        memory = WorkMemory()
        assert memory.get_memory_for_retry("t1") == ""

    def test_get_execution_trace(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output1", retry_count=0)
        memory.save_snapshot("t1", ctx, "output2", retry_count=1)
        trace = memory.get_execution_trace("t1")
        assert "Execution trace" in trace
        assert "Retry #0" in trace
        assert "Retry #1" in trace

    def test_clear(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output")
        assert memory.clear("t1") is True
        assert memory.get_snapshots("t1") == []

    def test_clear_missing(self):
        memory = WorkMemory()
        assert memory.clear("missing") is False

    def test_max_snapshots_pruning(self):
        memory = WorkMemory(max_snapshots_per_task=3)
        ctx = TaskContext(task_id="t1", user_message="test")
        for i in range(5):
            memory.save_snapshot("t1", ctx, f"output{i}")
        snapshots = memory.get_snapshots("t1")
        assert len(snapshots) == 3
        assert snapshots[0].output == "output2"
        assert snapshots[-1].output == "output4"

    def test_get_retry_count(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        memory.save_snapshot("t1", ctx, "output1", retry_count=0)
        memory.save_snapshot("t1", ctx, "output2", retry_count=1)
        assert memory.get_retry_count("t1") == 1

    def test_get_retry_count_empty(self):
        memory = WorkMemory()
        assert memory.get_retry_count("t1") == 0

    def test_snapshot_hash_consistency(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        s1 = memory.save_snapshot("t1", ctx, "output", ["issue"])
        s2 = memory.save_snapshot("t1", ctx, "output", ["issue"])
        assert s1.snapshot_hash == s2.snapshot_hash

    def test_snapshot_hash_different(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")
        s1 = memory.save_snapshot("t1", ctx, "output1")
        s2 = memory.save_snapshot("t1", ctx, "output2")
        assert s1.snapshot_hash != s2.snapshot_hash

    def test_multiple_tasks_isolated(self):
        memory = WorkMemory()
        ctx1 = TaskContext(task_id="t1", user_message="test1")
        ctx2 = TaskContext(task_id="t2", user_message="test2")
        memory.save_snapshot("t1", ctx1, "output1")
        memory.save_snapshot("t2", ctx2, "output2")
        assert len(memory.get_snapshots("t1")) == 1
        assert len(memory.get_snapshots("t2")) == 1
