"""
Anti-Laziness Devil Tests

End-to-end tests that simulate lazy agent behaviors and verify
the anti-laziness system detects and handles them correctly.
"""

import pytest
from nexusagent.execution.tracker import ExecutionTracker, TaskContext
from nexusagent.execution.anti_compression import AntiCompressionDetector
from nexusagent.execution.completeness import CompletenessValidator
from nexusagent.execution.work_memory import WorkMemory


class TestAntiCompressionDetection:
    """Test detection of various lazy compression patterns."""

    def test_detects_truncation_with_ellipsis(self):
        detector = AntiCompressionDetector()
        lazy_output = (
            "Here's the implementation of the sorting algorithm..."
        )
        assert detector.is_compressed(lazy_output) is True
        hits = detector.analyze(lazy_output)
        assert any(h.pattern.name == "TRUNCATION" for h in hits)

    def test_detects_skipping_claims(self):
        detector = AntiCompressionDetector()
        lazy_output = (
            "The remaining steps are similar to the above. "
            "No need to repeat the same pattern."
        )
        assert detector.is_compressed(lazy_output) is True
        hits = detector.analyze(lazy_output)
        patterns = {h.pattern.name for h in hits}
        assert "SKIPPING" in patterns or "SUMMARIZATION" in patterns

    def test_detects_placeholder_code(self):
        detector = AntiCompressionDetector()
        lazy_output = """
def complex_function():
    # TODO: implement this
    pass
"""
        assert detector.is_compressed(lazy_output) is True
        hits = detector.analyze(lazy_output)
        assert any(h.pattern.name == "INCOMPLETE_GENERATION" for h in hits)

    def test_detects_not_implemented(self):
        detector = AntiCompressionDetector()
        lazy_output = "raise NotImplementedError('Will do later')"
        assert detector.is_compressed(lazy_output) is True

    def test_clean_output_passes(self):
        detector = AntiCompressionDetector()
        good_output = (
            "Here is the complete implementation:\n\n"
            "def sort(items):\n"
            "    for i in range(len(items)):\n"
            "        for j in range(i + 1, len(items)):\n"
            "            if items[i] > items[j]:\n"
            "                items[i], items[j] = items[j], items[i]\n"
            "    return items\n\n"
            "This uses bubble sort with O(n²) complexity."
        )
        assert detector.is_compressed(good_output) is False
        assert detector.get_compression_score(good_output) == 0

    def test_multiple_lazy_patterns_combined(self):
        detector = AntiCompressionDetector()
        very_lazy = (
            "Implementation is straightforward... "
            "Similar to what we did above. "
            "The rest is omitted for brevity. "
            "TODO: add error handling."
        )
        summary = detector.get_summary(very_lazy)
        assert summary["total_hits"] >= 3
        assert summary["compression_score"] >= 6
        assert summary["high_severity_count"] >= 2


class TestCompletenessValidation:
    """Test validation of output completeness."""

    def test_missing_code_reported(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Write a Python function to calculate fibonacci")

        incomplete_output = "The fibonacci sequence is defined recursively."
        issues = validator.validate(task, incomplete_output)

        types = [i.issue_type for i in issues]
        assert "missing_code" in types
        assert any(i.severity == "high" for i in issues)

    def test_short_complex_task_reported(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task(
            "t1",
            "Create and build a full web application with authentication, database, "
            "and API endpoints. Implement tests and configure documentation."
        )

        too_short = "Done."
        issues = validator.validate(task, too_short)
        types = [i.issue_type for i in issues]
        assert "too_short" in types
        assert "suspiciously_short" in types

    def test_complete_task_passes(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Say hello")

        output = "Hello! How can I help you today?"
        assert validator.is_complete(task, output) is True
        assert len(validator.validate(task, output)) == 0

    def test_missing_steps_detected(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Build a web app")
        from nexusagent.execution.tracker import Step, StepStatus
        tracker.add_step("t1", Step(
            step_id="s1",
            description="Set up database schema",
            status=StepStatus.PENDING,
        ))
        tracker.add_step("t1", Step(
            step_id="s2",
            description="Implement API layer",
            status=StepStatus.PENDING,
        ))

        issues = validator.validate(task, "Web app is ready.")
        types = [i.issue_type for i in issues]
        assert "missing_step" in types
        assert len([i for i in issues if i.issue_type == "missing_step"]) == 2

    def test_file_creation_missing_confirmation(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Create a file called settings.py with Django settings")

        issues = validator.validate(task, "Here are the settings.")
        types = [i.issue_type for i in issues]
        assert "missing_file_confirmation" in types

    def test_summary_recommendation_critical(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Create and implement a Python class with 10 methods and tests")
        summary = validator.get_summary(task, "class MyClass: pass")
        assert summary["is_complete"] is False
        assert "CRITICAL" in summary["recommendation"]


class TestWorkMemoryPersistence:
    """Test that execution history is properly persisted."""

    def test_saves_and_retrieves_snapshots(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test task")

        memory.save_snapshot("t1", ctx, "output1", ["issue1"], retry_count=0)
        memory.save_snapshot("t1", ctx, "output2", ["issue2"], retry_count=1)

        snapshots = memory.get_snapshots("t1")
        assert len(snapshots) == 2
        assert snapshots[0].retry_count == 0
        assert snapshots[1].retry_count == 1

    def test_detects_duplicate_outputs(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")

        memory.save_snapshot("t1", ctx, "same output", ["missing code"])
        assert memory.is_duplicate("t1", "same output", ["missing code"]) is True
        assert memory.is_duplicate("t1", "different output") is False

    def test_detects_retry_cycles(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test")

        for _ in range(3):
            memory.save_snapshot("t1", ctx, "identical bad output")

        assert memory.detect_cycle("t1", max_repeats=3) is True

    def test_retry_prompt_generation(self):
        memory = WorkMemory()
        ctx = TaskContext(task_id="t1", user_message="test task")

        memory.save_snapshot("t1", ctx, "bad output", ["missing code", "too short"], retry_count=0)
        prompt = memory.get_memory_for_retry("t1")

        assert "PREVIOUS ATTEMPTS" in prompt
        assert "missing code" in prompt
        assert "WHAT YOU MUST FIX" in prompt
        assert "Do NOT repeat the same mistakes" in prompt

    def test_multiple_tasks_isolated(self):
        memory = WorkMemory()
        ctx1 = TaskContext(task_id="t1", user_message="task1")
        ctx2 = TaskContext(task_id="t2", user_message="task2")

        memory.save_snapshot("t1", ctx1, "output1")
        memory.save_snapshot("t2", ctx2, "output2")

        assert len(memory.get_snapshots("t1")) == 1
        assert len(memory.get_snapshots("t2")) == 1
        assert memory.get_latest_snapshot("t1").output == "output1"
        assert memory.get_latest_snapshot("t2").output == "output2"

    def test_max_snapshots_pruning(self):
        memory = WorkMemory(max_snapshots_per_task=2)
        ctx = TaskContext(task_id="t1", user_message="test")

        for i in range(5):
            memory.save_snapshot("t1", ctx, f"output{i}")

        assert len(memory.get_snapshots("t1")) == 2


class TestEndToEndAntiLaziness:
    """End-to-end scenarios combining all anti-laziness components."""

    def test_full_detection_pipeline(self):
        """Simulate a lazy agent output and verify full detection."""
        tracker = ExecutionTracker()
        detector = AntiCompressionDetector()
        validator = CompletenessValidator()
        memory = WorkMemory()

        # Simulate task
        task_id = "devil_test_1"
        user_msg = (
            "Create a complete Python web framework with routing, middleware, "
            "request handling, and response formatting. Include example usage."
        )
        task = tracker.create_task(task_id, user_msg)
        tracker.auto_plan_from_message(task_id)

        # Simulate lazy agent output
        lazy_output = (
            "Here's the basic structure...\n\n"
            "class App:\n"
            "    # TODO: implement routing\n"
            "    pass\n\n"
            "The rest is similar to Flask."
        )

        # Step 1: AntiCompression detection
        ac_summary = detector.get_summary(lazy_output)
        assert ac_summary["is_compressed"] is True
        assert ac_summary["high_severity_count"] >= 2

        # Step 2: Completeness validation
        comp_issues = validator.validate(task, lazy_output)
        comp_summary = validator.get_summary(task, lazy_output)
        assert comp_summary["is_complete"] is False
        assert comp_summary["high_severity"] >= 1

        # Step 3: Save to WorkMemory
        memory.save_snapshot(
            task_id=task_id,
            task_context=task,
            output=lazy_output,
            validation_issues=[
                f"Compression: {ac_summary['by_pattern']}",
                f"Completeness: {comp_summary['issues_by_type']}",
            ],
            retry_count=0,
        )

        # Step 4: Generate retry prompt
        retry_prompt = memory.get_memory_for_retry(task_id)
        assert "PREVIOUS ATTEMPTS" in retry_prompt
        assert "WHAT YOU MUST FIX" in retry_prompt

        # Step 5: Verify retry prompt would help
        assert len(retry_prompt) > 100
        assert "Do NOT repeat" in retry_prompt

    def test_progressive_improvement_tracking(self):
        """Track how outputs improve across retries."""
        tracker = ExecutionTracker()
        detector = AntiCompressionDetector()
        validator = CompletenessValidator()
        memory = WorkMemory()

        task_id = "progressive_test"
        user_msg = "Write a complete Python class for a BankAccount with 5 methods"
        task = tracker.create_task(task_id, user_msg)

        # Attempt 1: Very lazy
        output1 = "class BankAccount: ... # TODO"
        issues1 = validator.validate(task, output1)
        memory.save_snapshot(task_id, task, output1, [i.description for i in issues1], 0)

        # Attempt 2: Better but still incomplete
        output2 = (
            "class BankAccount:\n"
            "    def __init__(self):\n"
            "        self.balance = 0\n"
            "    # Other methods similar to above\n"
        )
        issues2 = validator.validate(task, output2)
        memory.save_snapshot(task_id, task, output2, [i.description for i in issues2], 1)

        # Verify WorkMemory tracks both
        snapshots = memory.get_snapshots(task_id)
        assert len(snapshots) == 2
        assert snapshots[0].retry_count == 0
        assert snapshots[1].retry_count == 1

        # Second attempt should have fewer issues
        assert len(issues2) <= len(issues1)

    def test_orchestrator_integration_params(self):
        """Verify Orchestrator accepts all anti-laziness components."""
        from nexusagent.orchestration.orchestrator import Orchestrator

        # Create with all anti-laziness params
        orch = Orchestrator(
            guardrails=None,
            react_engine=None,
            trust_scores={},
            memory_store=None,
            execution_tracker=ExecutionTracker(),
            anti_compression=AntiCompressionDetector(),
            completeness_validator=CompletenessValidator(),
            work_memory=WorkMemory(),
        )

        assert orch._tracker is not None
        assert orch._anti_compression is not None
        assert orch._completeness is not None
        assert orch._work_memory is not None
