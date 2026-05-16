# Contributing to Rangarr

Thank you for considering contributing to Rangarr! This document provides guidelines for contributing to the project and helps ensure a smooth collaboration process.

## Code of Conduct

This project follows the Contributor Covenant Code of Conduct. By participating, you are expected to uphold this code. Please report unacceptable behavior through GitHub issues or by contacting the maintainer.

## How to Report Bugs

### General Bugs

For general bugs and feature requests, please open a GitHub issue:
- Search existing issues first to avoid duplicates.
- Provide a clear and descriptive title.
- Include steps to reproduce the issue.
- Share your configuration (sanitize API keys and sensitive data).
- Include log output if applicable (use `LOG_LEVEL=DEBUG` for detailed logs).

### Security Vulnerabilities

**Do not open public GitHub issues for security vulnerabilities.**

Please report security issues responsibly:
- Use GitHub Security Advisories: https://github.com/JudoChinX/rangarr/security.
- Or email: rangarr@judochinx.com for non-GitHub users.

See [SECURITY.md](SECURITY.md) for our full security policy and coordinated disclosure timeline.

## Development Setup

For detailed setup instructions, see the [User Guide](docs/user-guide.md).

## Coding Standards

All contributions must meet the following standards:

### Automated Checks

All pushes automatically run pre-push hooks (see [pre-push.sh](utils/pre-push.sh)) that enforce:

- **Ruff** (linting and formatting).
- **Pylint** (code quality).
- **Mypy** (type checking).
- **Bandit** (security scanning).
- **Pytest** (test suite).

You can run these checks manually:

```bash
# Linting and formatting
ruff check .
ruff check --fix .
ruff format .

# Type checking
mypy rangarr/ tests/

# Security scanning
bandit -r rangarr/ -lll

# Code quality
pylint rangarr/ tests/

# Run tests
pytest
pytest tests/unit/clients/test_arr_base.py -v  # Run specific test file
pytest tests/unit/clients/test_arr_base.py::test_function_name -v  # Run specific test
```

### Code Style Requirements

All submissions must pass the automated checks listed above (Ruff, Pylint, Mypy, Bandit, Pytest).

For detailed coding conventions — naming, docstrings, type hints, testing patterns, and more — see the [Style Guide](docs/style-guide.md).

## Security-Conscious Contribution Guidelines

Rangarr handles API keys and communicates with self-hosted services. Security is paramount:

### Never Commit Sensitive Data

- **API keys**: Never commit real API keys. Use `YOUR_API_KEY` or similar placeholders.
- **Hostnames/IPs**: Use example addresses (e.g., `localhost`, `example.com`) in test data.
- **Personal information**: No real names, emails, or identifying information in test data.
- **Configuration files**: Always use example configuration files; never commit your personal `config.yaml`.

### Document API Interactions

If your contribution adds or changes API endpoint calls, update SECURITY.md accordingly.

### Add Tests for Security-Relevant Code

- Input validation functions must have comprehensive test coverage.
- API authentication and error handling must be tested.
- Configuration parsing must validate and reject malformed/malicious input.
- Test with both valid and invalid data.

### Input Validation and Error Handling

All user input and configuration must be validated:
- Validate URLs before making requests.
- Sanitize and validate configuration values.
- Handle API errors gracefully without exposing sensitive information.
- Log security-relevant events at appropriate levels.
- Never log API keys or authentication tokens.

## Pull Request Process

### Before Creating a Pull Request

1. **Test locally**: Run the full test suite and ensure all checks pass.
2. **Update tests**: Add tests for new functionality or bug fixes.
3. **Update documentation**: Update README.md or docs/user-guide.md if applicable.
4. **Review your changes**: Self-review for correctness, test coverage, and alignment with the coding standards in this file.
5. **Clean commit history**: Squash WIP commits; write clear commit messages (see [Commit Messages](#commit-messages) below).

### Creating a Pull Request

1. **Fork the repository** and create a feature branch.
2. **Push your changes** to your fork.
3. **Open a pull request** with:
   - Clear, descriptive title.
   - Summary of changes and motivation.
   - Reference to related issues (if applicable).
   - Screenshots or logs if helpful.
4. **Respond to feedback**: Address reviewer comments promptly.

### Pull Request Expectations

- PRs will be reviewed for code quality, security, and alignment with project goals.
- All automated checks must pass before merge.
- Maintainers may request changes or additional tests.
- Large PRs may take longer to review; consider breaking into smaller PRs.
- Security-related PRs receive priority review.

## Commit Messages

Every commit message starts with a type prefix followed by a colon and a space:

| Prefix | When to use |
|---|---|
| `new:` | A new feature, file, or capability that didn't exist before |
| `chg:` | A change or improvement to existing behavior, docs, or config |
| `fix:` | A bug fix |

The subject line is sentence case and must end with punctuation (a period in most cases).

```
new: Add tag-based filtering for *arr instances.
chg: Update retry interval default from 7 to 30 days.
fix: Enforce batch size limits in Sonarr season packs.
```

Keep the subject under 72 characters. If more context is needed, add a blank line followed by a body paragraph.

Squash WIP commits before opening a PR — the merged history should read as a clean sequence of meaningful changes.

## GitHub Actions

CI runs automatically on every push and pull request. The following checks must pass before a PR can be merged:

| Check | What it runs |
|---|---|
| Lint & format | `ruff check . && ruff format --check .` |
| Type checking | `mypy rangarr/ tests/` |
| Code quality | `pylint rangarr/ tests/` |
| Security scan | `bandit -r rangarr/ -lll` |
| Test suite | `pytest` (95% coverage required) |

These are the same checks run by the local pre-push hook in `utils/pre-push.sh`. If CI fails on your PR, run the failing check locally to reproduce it — the output is identical.

Security-related failures (Bandit) block merge regardless of other results.

Thank you for contributing to Rangarr!
