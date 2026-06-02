# Contributing to NexusAgent

Thank you for your interest in contributing to NexusAgent! This document provides guidelines and instructions for contributing.

## Development Environment Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_ORG/nexus-agent.git
cd nexus-agent

# 2. Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install in editable mode with dev dependencies
pip install -e ".[dev]"

# 4. Verify tests pass
pytest
```

## Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

| Type | Description |
|------|-------------|
| `feat:` | A new feature |
| `fix:` | A bug fix |
| `docs:` | Documentation only changes |
| `style:` | Code style changes (formatting, semicolons, etc) |
| `refactor:` | Code changes that neither fix a bug nor add a feature |
| `perf:` | Performance improvements |
| `test:` | Adding or correcting tests |
| `chore:` | Changes to build process or auxiliary tools |

Example:
```bash
git commit -m "feat: add support for Azure OpenAI backend"
git commit -m "fix: correct token budget calculation in ReActEngine"
git commit -m "docs: update README with new quickstart guide"
```

## Testing Requirements

- All new code must include unit tests.
- All tests must pass before merging: `pytest`
- Aim for >80% code coverage for new modules.
- Run specific test batches:
  ```bash
  pytest tests/test_core.py -v
  pytest tests/test_swarm.py tests/test_mirofish.py -v
  ```

## Issue Labels

| Label | Description |
|-------|-------------|
| `bug` | Something isn't working |
| `enhancement` | New feature or request |
| `documentation` | Improvements or additions to docs |
| `good first issue` | Good for newcomers |
| `help wanted` | Extra attention is needed |
| `duplicate` | This issue or PR already exists |

## Pull Request Process

1. **Fork** the repository and create your branch from `main`.
2. **Write** clear, concise commit messages following our convention.
3. **Add** tests for any new functionality.
4. **Ensure** the test suite passes: `pytest`
5. **Update** documentation if applicable (README, docstrings, examples).
6. **Fill out** the PR template completely.
7. **Request review** from at least one maintainer.

## PR Template

When opening a Pull Request, please include:

- **Summary**: What does this PR do?
- **Changes**: List of files changed and why.
- **Testing**: How did you test these changes?
- **Breaking Changes**: Are there any API changes or breaking modifications?
- **Screenshots/Logs**: If applicable, add output or screenshots.

## Code Style

- Follow PEP 8 for Python code.
- Use type hints for public functions and classes.
- Write bilingual docstrings (English first, Chinese optional):
  ```python
  def process_message(user_id: str, message: str) -> str:
      """
      Process a user message and return a response.
      
      处理用户消息并返回回复。
      """
  ```

## Questions?

- Open a [Discussion](https://github.com/YOUR_ORG/nexus-agent/discussions) for general questions.
- Open an [Issue](https://github.com/YOUR_ORG/nexus-agent/issues) for bug reports or feature requests.

Thank you for contributing! 🎉
