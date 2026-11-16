#!/usr/bin/env bash
# Executed only inside the disposable worker-tests container.
set -euo pipefail

python - <<'PY'
import os
from test_support.resource_safety import prepare_test_environment
prepare_test_environment(os.environ)
print("Disposable test targets validated; no URLs displayed.")
PY

python -m black --check app/ tests/ test_support/
python -m isort --check-only app/ tests/ test_support/
python -m flake8 app/ tests/ test_support/ --max-line-length=120 --exclude=__pycache__,migrations
python -m mypy app/ test_support/ --ignore-missing-imports

# Match CI's process isolation. Do not collect the repository's operational scripts
# or rerun the entire suite together merely to generate a coverage report.
failed=0
while IFS= read -r file; do
    printf 'Testing %s\n' "$file"
    if timeout -k 15 300 python -m pytest "$file" -q -o addopts= \
        --tb=short --timeout=60 --timeout-method=signal --cov=app --cov-append; then
        :
    else
        status=$?
        if [[ "$status" -ne 5 ]]; then
            printf 'Failed %s (exit %s)\n' "$file" "$status" >&2
            failed=1
        fi
    fi
done < <(find tests -name 'test_*.py' -type f | sort)

if [[ "$failed" -ne 0 ]]; then
    exit 1
fi
python -m coverage report
