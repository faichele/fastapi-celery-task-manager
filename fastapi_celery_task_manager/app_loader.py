"""Shared helper to import a Celery app from a dotted import path.

Split out from `cli.py` so it can be imported (including from this
package's own `__init__.py`) without pulling in `cli.py`'s argparse/`main()`
module. Importing `cli.py` eagerly from `__init__.py` would make
`python -m fastapi_celery_task_manager.cli` re-import it as `__main__`,
triggering a `RuntimeWarning` about duplicate module execution.
"""

from __future__ import annotations

import importlib

from celery import Celery


def load_celery_app(import_path: str) -> Celery:
    """Import a `Celery` instance from a ``module.path:attribute`` string.

    Example: ``"backend.celery_tasks.celery_app:celery_app"``.
    """
    if ":" not in import_path:
        raise SystemExit(
            f"Invalid --app value '{import_path}'. Expected 'module.path:attribute', "
            "e.g. 'backend.celery_tasks.celery_app:celery_app'."
        )
    module_path, attr = import_path.split(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise SystemExit(f"Could not import module '{module_path}': {exc}") from exc
    try:
        celery_app = getattr(module, attr)
    except AttributeError as exc:
        raise SystemExit(f"Module '{module_path}' has no attribute '{attr}'.") from exc
    if not isinstance(celery_app, Celery):
        raise SystemExit(f"'{import_path}' does not resolve to a Celery instance (got {type(celery_app)!r}).")
    return celery_app
