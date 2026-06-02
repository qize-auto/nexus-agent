"""Tests for CompletenessValidator."""

import pytest
from nexusagent.execution.completeness import CompletenessValidator, CompletenessIssue
from nexusagent.execution.tracker import ExecutionTracker, Step, StepStatus


class TestCompletenessValidator:
    def test_init_default(self):
        validator = CompletenessValidator()
        assert validator.min_output_ratio == 0.3

    def test_init_custom_ratio(self):
        validator = CompletenessValidator(min_output_ratio=0.5)
        assert validator.min_output_ratio == 0.5

    def test_simple_task_short_output_ok(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Say hello")
        issues = validator.validate(task, "Hello!")
        assert len(issues) == 0

    def test_complex_task_too_short(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task(
            "t1",
            "Create a Python module with classes A and B and implement methods "
            "for each and write tests and documentation"
        )
        issues = validator.validate(task, "Done.")
        types = [i.issue_type for i in issues]
        assert "too_short" in types
        assert "suspiciously_short" in types

    def test_missing_code_detection(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Write a Python function to sort a list")
        issues = validator.validate(task, "Here's the algorithm: use quicksort.")
        types = [i.issue_type for i in issues]
        assert "missing_code" in types
        assert any(i.severity == "high" for i in issues)

    def test_code_provided_no_issue(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Write a Python function to sort a list")
        output = "```python\ndef sort_list(items):\n    return sorted(items)\n```"
        issues = validator.validate(task, output)
        types = [i.issue_type for i in issues]
        assert "missing_code" not in types

    def test_missing_step_detection(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Build a web app")
        tracker.add_step("t1", Step(
            step_id="s1",
            description="Set up database",
            status=StepStatus.PENDING,
        ))
        issues = validator.validate(task, "Web app is ready.")
        types = [i.issue_type for i in issues]
        assert "missing_step" in types

    def test_completed_step_not_reflected(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Build something")
        tracker.add_step("t1", Step(
            step_id="s1",
            description="Configure authentication",
            status=StepStatus.COMPLETED,
        ))
        issues = validator.validate(task, "Done building.")
        types = [i.issue_type for i in issues]
        assert "step_not_reflected" in types

    def test_completed_step_reflected(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Build something")
        tracker.add_step("t1", Step(
            step_id="s1",
            description="Configure authentication",
            status=StepStatus.COMPLETED,
        ))
        issues = validator.validate(task, "Authentication has been configured.")
        types = [i.issue_type for i in issues]
        assert "step_not_reflected" not in types

    def test_missing_file_confirmation(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Create a file called config.py")
        issues = validator.validate(task, "Created the file.")
        types = [i.issue_type for i in issues]
        assert "missing_file_confirmation" in types

    def test_file_confirmed(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Create a file called config.py")
        issues = validator.validate(task, "Created config.py with settings.")
        types = [i.issue_type for i in issues]
        assert "missing_file_confirmation" not in types

    def test_is_complete_true(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Say hello")
        assert validator.is_complete(task, "Hello!") is True

    def test_is_complete_false(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Write a Python function")
        assert validator.is_complete(task, "Here's the idea.") is False

    def test_get_summary_no_issues(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Say hello")
        summary = validator.get_summary(task, "Hello!")
        assert summary["is_complete"] is True
        assert summary["total_issues"] == 0
        assert summary["recommendation"] == "Output appears complete."

    def test_get_summary_with_issues(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Write a Python function to sort a list")
        summary = validator.get_summary(task, "Here's the idea.")
        assert summary["is_complete"] is False
        assert summary["high_severity"] >= 1
        assert "CRITICAL" in summary["recommendation"]

    def test_missing_requirement_detection(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task("t1", "Create a database and write a handler")
        issues = validator.validate(task, "Database created.")
        types = [i.issue_type for i in issues]
        assert "missing_requirement" in types

    def test_sufficient_output_for_complex_task(self):
        validator = CompletenessValidator()
        tracker = ExecutionTracker()
        task = tracker.create_task(
            "t1",
            "Create a Python module with classes A and B and implement methods"
        )
        long_output = "A" * 500  # Sufficiently long
        issues = validator.validate(task, long_output)
        types = [i.issue_type for i in issues]
        assert "too_short" not in types
        assert "suspiciously_short" not in types
