"""fastapi_celery_task_manager

Reusable FastAPI routers for basic Celery administration.

Public API:
- get_celery_admin_router: REST endpoints under /api/celery
- get_celery_admin_ui_router: HTML page rendering celery_monitor.html
"""

from .celery_admin import get_celery_admin_router
from .ui import get_celery_admin_ui_router
from .ui import get_celery_admin_ui_router_with_login_redirect

__all__ = [
    "get_celery_admin_router",
    "get_celery_admin_ui_router",
    "get_celery_admin_ui_router_with_login_redirect"
]
