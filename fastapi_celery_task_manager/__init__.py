"""fastapi_celery_task_manager

Reusable FastAPI routers for basic Celery administration, plus a generic
CLI to run workers/beat and dispatch tasks.

Public API:
- get_celery_admin_router: REST endpoints under /api/celery
- get_celery_admin_ui_router: HTML page rendering celery_monitor.html
- get_celery_admin_ui_router_with_login_redirect: same, redirects to login on 401/403
- dispatch_task / resolve_queue / DispatchResult: enqueue a task from Python,
  without going through HTTP (see `dispatch.py`)
- load_celery_app: import a Celery instance from a "module.path:attribute" string,
  shared by the `cli` and `diagnostics` command-line entry points
  (`python -m fastapi_celery_task_manager.cli`, `python -m fastapi_celery_task_manager.diagnostics`)
"""

from .app_loader import load_celery_app
from .celery_admin import get_celery_admin_router
from .dispatch import DispatchResult, dispatch_task, resolve_queue
from .ui import get_celery_admin_ui_router, get_celery_admin_ui_router_with_login_redirect

__all__ = [
    "get_celery_admin_router",
    "get_celery_admin_ui_router",
    "get_celery_admin_ui_router_with_login_redirect",
    "dispatch_task",
    "resolve_queue",
    "DispatchResult",
    "load_celery_app",
]
