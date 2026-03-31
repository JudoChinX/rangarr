#!/bin/bash

set -e

source "$(git rev-parse --show-toplevel)/.venv/bin/activate"

echo "Checking for subdirectories under docs/..."
if git diff --name-only --diff-filter=ACM "$(git rev-parse --abbrev-ref @{upstream} 2>/dev/null || echo HEAD~1)" HEAD 2>/dev/null | grep -q '^docs/[^/]*/'; then
  echo ""
  echo "ERROR: push contains files inside a docs/ subdirectory. Remove them from the commit before pushing."
  exit 1
fi

echo "Running ruff check..."
if ! ruff check .; then
  echo ""
  echo "ERROR: ruff check failed. To fix:"
  echo "   1. Run: ruff check --fix ."
  echo "   2. Review and fix any remaining issues manually"
  echo "   3. Commit your fixes and try pushing again"
  exit 1
fi

echo "Running ruff format..."
if ! ruff format --check .; then
  echo ""
  echo "ERROR: ruff format failed. To fix:"
  echo "   1. Run: ruff format ."
  echo "   2. Commit the formatting changes and try pushing again"
  exit 1
fi

echo "Running pylint..."
if ! pylint rangarr/ tests/; then
  echo ""
  echo "ERROR: pylint found issues. To fix:"
  echo "   1. Review the pylint output above"
  echo "   2. Fix the reported issues in your code"
  echo "   3. Commit your fixes and try pushing again"
  exit 1
fi

echo "Running mypy..."
if ! mypy rangarr/ tests/; then
  echo ""
  echo "ERROR: mypy type checking failed. To fix:"
  echo "   1. Review the mypy output above"
  echo "   2. Add type hints to untyped function definitions"
  echo "   3. Fix any type inconsistencies"
  echo "   4. Commit your fixes and try pushing again"
  exit 1
fi

echo "Running bandit security checks..."
if ! bandit -r rangarr/ -lll; then
  echo ""
  echo "ERROR: bandit found security issues. To fix:"
  echo "   1. Review the security warnings above"
  echo "   2. Fix the identified security vulnerabilities"
  echo "   3. Commit your fixes and try pushing again"
  exit 1
fi

echo "Running pip-audit..."
if ! pip-audit -r requirements.txt; then
  echo ""
  echo "ERROR: pip-audit found vulnerable dependencies. To fix:"
  echo "   1. Review the vulnerabilities above"
  echo "   2. Update the affected packages in requirements.txt"
  echo "   3. Commit your fixes and try pushing again"
  exit 1
fi

echo "Running pytest..."
if ! pytest tests/ -v; then
  echo ""
  echo "ERROR: pytest tests failed. To fix:"
  echo "   1. Review the test failures above"
  echo "   2. Fix the failing tests or the code causing failures"
  echo "   3. Run: pytest tests/ -v to verify locally"
  echo "   4. Commit your fixes and try pushing again"
  exit 1
fi

echo ""
echo "All checks passed!"
exit 0
