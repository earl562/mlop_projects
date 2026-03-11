Run the PlotLot test suite and report results.

## Steps

1. Run lint and format checks:
   ```bash
   cd plotlot && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
   ```

2. Run type checks:
   ```bash
   cd plotlot && uv run mypy src/plotlot/
   ```

3. Run unit tests with coverage:
   ```bash
   cd plotlot && uv run pytest tests/unit/ -v --tb=short
   ```

4. Optionally run eval tests (if `--eval` flag is passed or user requests it):
   ```bash
   cd plotlot && uv run pytest tests/eval/ -v --tb=short
   ```

Report a summary: how many tests passed/failed, any lint errors, any new mypy errors. If tests fail, diagnose the root cause and suggest fixes.
