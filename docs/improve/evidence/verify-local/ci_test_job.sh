# The CI "test" job's steps on one Python, in its scratch venv (made beforehand). Usage: ci_test_job.sh <repo> <3.12|3.13|3.14>
set +e
cd "$1"
P=".scratch/ci-py$2/bin/python"
echo "## Python $($P -c 'import sys; print(sys.version.split()[0])')  HEAD $(git rev-parse --short HEAD)  $(uptime | sed 's/.*load/load/')"
echo "## ruff";       $P -m ruff check . 2>&1 | tail -1
echo "## mypy";       $P -m mypy --strict src/variance_agent scripts deterministic_conditioning 2>&1 | tail -1
echo "## compileall"; $P -m compileall -q src tests scripts deterministic_conditioning; echo "exit $?"
echo "## pytest";     $P -m pytest -q -p no:cacheprovider 2>&1 | tail -1
echo "## pip check";  $P -m pip check 2>&1 | tail -1
