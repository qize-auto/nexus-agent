"""
Completeness Validator

Validates that agent outputs fully address the original task requirements.
Detects:
1. Missing steps from the execution plan
2. Unaddressed parts of the user request
3. Outputs that are too short for the task complexity
4. Missing file/code generation when requested
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Set

from .tracker import TaskContext, Step, StepStatus, EvidenceType


@dataclass
class CompletenessIssue:
    issue_type: str
    description: str
    severity: str  # "low", "medium", "high"
    suggestion: str


class CompletenessValidator:
    """Validates output completeness against task requirements."""

    # Keywords that indicate multi-part or complex tasks
    COMPLEXITY_INDICATORS = [
        r"\band\b.*\band\b",  # Multiple "and" suggests multiple requirements
        r"\bsteps?\b",
        r"\bphases?\b",
        r"\bparts?\b",
        r"\bsections?\b",
        r"\bmodules?\b",
        r"\bcomponents?\b",
        r"\bfiles?\b",
        r"\bimplement\b",
        r"\bcreate\b",
        r"\bbuild\b",
        r"\bset up\b",
        r"\bconfigure\b",
        r"\btest\b",
        r"\bdocument\b",
    ]

    # Keywords suggesting code generation is expected
    CODE_INDICATORS = [
        r"```",
        r"class\s+\w+",
        r"def\s+\w+",
        r"function\s+\w+",
        r"import\s+\w+",
        r"from\s+\w+",
    ]

    def __init__(self, min_output_ratio: float = 0.3):
        """
        Args:
            min_output_ratio: Minimum ratio of output chars to input chars
                            for non-trivial tasks (0.0-1.0)
        """
        self.min_output_ratio = min_output_ratio

    def validate(self, task: TaskContext, output: str) -> List[CompletenessIssue]:
        """Validate output completeness against task context."""
        issues = []
        issues.extend(self._check_missing_steps(task, output))
        issues.extend(self._check_unaddressed_requirements(task, output))
        issues.extend(self._check_output_length(task, output))
        issues.extend(self._check_expected_code(task, output))
        issues.extend(self._check_file_references(task, output))
        return issues

    def is_complete(self, task: TaskContext, output: str) -> bool:
        """Quick check if output appears complete."""
        issues = self.validate(task, output)
        high_severity = [i for i in issues if i.severity == "high"]
        return len(high_severity) == 0

    def _check_missing_steps(self, task: TaskContext, output: str) -> List[CompletenessIssue]:
        """Check if any planned steps have no corresponding evidence."""
        issues = []
        output_lower = output.lower()

        for step in task.plan_steps:
            if step.status == StepStatus.PENDING:
                issues.append(CompletenessIssue(
                    issue_type="missing_step",
                    description=f"Step not executed: {step.description}",
                    severity="high",
                    suggestion=f"Execute step: {step.description}"
                ))
            elif step.status == StepStatus.RUNNING:
                issues.append(CompletenessIssue(
                    issue_type="incomplete_step",
                    description=f"Step incomplete: {step.description}",
                    severity="medium",
                    suggestion=f"Complete step: {step.description}"
                ))
            elif step.status == StepStatus.COMPLETED:
                # Check if step result is reflected in output
                step_words = set(step.description.lower().split())
                # Filter out common words
                step_words = {w for w in step_words if len(w) > 3}
                if step_words and not any(w in output_lower for w in step_words):
                    issues.append(CompletenessIssue(
                        issue_type="step_not_reflected",
                        description=f"Completed step not reflected in output: {step.description}",
                        severity="medium",
                        suggestion="Ensure all completed steps are mentioned in the final output"
                    ))
        return issues

    def _check_unaddressed_requirements(self, task: TaskContext, output: str) -> List[CompletenessIssue]:
        """Check for requirement keywords in user message that are missing from output."""
        issues = []
        user_msg = task.user_message.lower()
        output_lower = output.lower()

        # Extract action nouns from user message
        action_patterns = [
            r"(?:create|write|generate|build|implement|add|set up)\s+(?:a\s+)?(\w+)",
            r"(?:create|write|generate|build|implement|add|set up)\s+(\w+\s+\w+)",
        ]

        requested_items: Set[str] = set()
        for pattern in action_patterns:
            for match in re.finditer(pattern, user_msg):
                item = match.group(1).strip()
                if len(item) > 2:
                    requested_items.add(item)

        for item in requested_items:
            if item not in output_lower:
                issues.append(CompletenessIssue(
                    issue_type="missing_requirement",
                    description=f"Requested item '{item}' not found in output",
                    severity="medium",
                    suggestion=f"Include implementation or mention of '{item}'"
                ))

        return issues

    def _check_output_length(self, task: TaskContext, output: str) -> List[CompletenessIssue]:
        """Check if output is suspiciously short for a complex task."""
        issues = []
        user_msg = task.user_message

        # Check if task appears complex
        complexity_score = sum(
            1 for p in self.COMPLEXITY_INDICATORS
            if re.search(p, user_msg, re.IGNORECASE)
        )

        if complexity_score >= 3:
            # Complex task should have substantial output
            input_len = len(user_msg)
            output_len = len(output)
            ratio = output_len / input_len if input_len > 0 else 0

            if ratio < self.min_output_ratio:
                issues.append(CompletenessIssue(
                    issue_type="suspiciously_short",
                    description=(
                        f"Output ({output_len} chars) seems short compared to "
                        f"task complexity ({input_len} chars input, ratio: {ratio:.2f})"
                    ),
                    severity="medium",
                    suggestion="Expand output to fully address all aspects of the task"
                ))

            # Absolute minimum for complex tasks
            if output_len < 200:
                issues.append(CompletenessIssue(
                    issue_type="too_short",
                    description=f"Output is only {output_len} characters for a complex task",
                    severity="high",
                    suggestion="Provide a more detailed and complete response"
                ))

        return issues

    def _check_expected_code(self, task: TaskContext, output: str) -> List[CompletenessIssue]:
        """Check if code generation was requested but not provided."""
        issues = []
        user_msg = task.user_message.lower()

        code_request_indicators = [
            r"\bcode\b",
            r"\bscript\b",
            r"\bfunction\b",
            r"\bclass\b",
            r"\bmodule\b",
            r"\bimplement\b",
            r"\bwrite\b.*\bpython\b",
            r"\bwrite\b.*\bjava\b",
            r"\bwrite\b.*\bjs\b",
            r"\bwrite\b.*\bgo\b",
            r"\bgenerate\b.*\bcode\b",
        ]

        code_requested = any(
            re.search(p, user_msg) for p in code_request_indicators
        )

        code_provided = any(
            re.search(p, output) for p in self.CODE_INDICATORS
        )

        if code_requested and not code_provided:
            issues.append(CompletenessIssue(
                issue_type="missing_code",
                description="Code generation was requested but no code blocks found in output",
                severity="high",
                suggestion="Provide the requested code implementation with code blocks"
            ))

        return issues

    def _check_file_references(self, task: TaskContext, output: str) -> List[CompletenessIssue]:
        """Check if file creation was requested but not confirmed."""
        issues = []
        user_msg = task.user_message.lower()

        file_request_patterns = [
            r"\bfile\b",
            r"\bcreate\b.*\b\w+\.\w+",
            r"\bwrite\b.*\b\w+\.\w+",
            r"\bgenerate\b.*\b\w+\.\w+",
        ]

        file_requested = any(
            re.search(p, user_msg) for p in file_request_patterns
        )

        # Look for file creation confirmations in output
        file_confirmation_patterns = [
            r"\bcreated\b.*\b\w+\.\w+",
            r"\bwrote\b.*\b\w+\.\w+",
            r"\bgenerated\b.*\b\w+\.\w+",
            r"\bsaved\b.*\b\w+\.\w+",
        ]

        file_confirmed = any(
            re.search(p, output, re.IGNORECASE) for p in file_confirmation_patterns
        )

        # Also check if evidence contains file outputs
        has_file_evidence = any(
            e.evidence_type == EvidenceType.FILE_WRITE
            or e.evidence_type == EvidenceType.TOOL_CALL
            for e in task.evidence_log
        )

        if file_requested and not (file_confirmed or has_file_evidence):
            issues.append(CompletenessIssue(
                issue_type="missing_file_confirmation",
                description="File creation was requested but no confirmation found",
                severity="medium",
                suggestion="Confirm created files or provide file contents in output"
            ))

        return issues

    def get_summary(self, task: TaskContext, output: str) -> dict:
        """Get a summary of completeness validation."""
        issues = self.validate(task, output)
        by_type = {}
        for issue in issues:
            by_type.setdefault(issue.issue_type, []).append(issue)

        return {
            "is_complete": self.is_complete(task, output),
            "total_issues": len(issues),
            "high_severity": len([i for i in issues if i.severity == "high"]),
            "medium_severity": len([i for i in issues if i.severity == "medium"]),
            "low_severity": len([i for i in issues if i.severity == "low"]),
            "issues_by_type": {k: len(v) for k, v in by_type.items()},
            "recommendation": self._get_recommendation(issues),
        }

    def _get_recommendation(self, issues: List[CompletenessIssue]) -> str:
        """Generate a recommendation based on issues."""
        if not issues:
            return "Output appears complete."

        high = [i for i in issues if i.severity == "high"]
        if high:
            types = set(i.issue_type for i in high)
            if "missing_code" in types:
                return "CRITICAL: Requested code is missing. Must provide implementation."
            if "missing_step" in types:
                return "CRITICAL: Planned steps were not executed. Complete all steps."
            if "too_short" in types:
                return "CRITICAL: Output is too short. Expand significantly."
            return "CRITICAL: Multiple high-severity completeness issues detected."

        medium = [i for i in issues if i.severity == "medium"]
        if medium:
            return f"WARNING: {len(medium)} medium-severity issues. Review and expand."

        return "Minor completeness concerns. Consider expanding for clarity."
