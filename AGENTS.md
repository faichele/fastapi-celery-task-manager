# Repository Guidelines

## Project Structure & Module Organization

`fastapi_celery_task_manager/` is the distributable Python package. Keep public
exports in `__init__.py`; implement focused concerns in modules such as
`celery_admin.py` (FastAPI routes), `ui.py` (Jinja integration), `dispatch.py`
(task routing), and `cli.py`/`diagnostics.py` (commands). Package HTML assets
live in `templates/`; they are included in distribution by `pyproject.toml`.
`README.md` is the user-facing integration guide and should track public API or
CLI changes. This project currently has no committed test directory.

## Build, Test, and Development Commands

Install an editable development copy with the extras needed for the feature you
are working on:

```bash
python -m pip install -e '.[cli,diagnostics]'
python -m ruff check fastapi_celery_task_manager
python -m ruff format --check fastapi_celery_task_manager
python -m build
```

The first command installs optional `watchdog`, Redis, and dotenv support;
Ruff linting checks imports and Python upgrades; the format check avoids
unintended formatting changes; `build` validates package assembly. Exercise
the supplied entry points against a real application, for example:
`fctm-doctor --app myapp.celery_app:celery_app`.

## Coding Style & Naming Conventions

Target Python 3.9+, use four-space indentation, type annotations, and
`from __future__ import annotations` in new modules where useful. Ruff uses a
120-character line limit and enforces `F`, `I`, and `UP` rules. Use
`snake_case` for functions, variables, and modules; `PascalCase` for classes
and dataclasses; and clear verb-led function names such as `dispatch_task`.
Keep router construction configurable rather than binding to an embedding
application's Celery instance or auth mechanism.

## Testing Guidelines

Add `pytest` tests under `tests/`, named `test_<behavior>.py`, with test
functions named `test_<expected_outcome>`. Unit-test pure routing and app-load
logic with fakes; isolate broker, Redis, and FastAPI integration behind mocks
or explicit integration tests. Run `python -m pytest` once test dependencies
and tests are present, plus both Ruff commands before submitting.

## Commit & Pull Request Guidelines

Recent history uses short, imperative subjects (for example, `Format
pyproject.toml for consistency`). Keep commits narrowly scoped and describe
the user-visible change. Pull requests should explain behavior and
configuration impact, link relevant issues, include verification commands,
and provide UI screenshots when modifying `templates/celery_monitor.html`.
