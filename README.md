# fastapi-celery-task-manager

Kleines, eigenständiges Paket mit einem FastAPI-`APIRouter` für grundlegende Celery-Administration (Inspect/Enqueue/Control) sowie einem Jinja2-Template für eine simple Admin-UI.

## Enthalten
- `get_celery_admin_router(...)` → REST-Endpunkte unter `/api/celery`
- `get_celery_admin_ui_router(...)` → HTML-Route (Default: `/admin/celery`), rendert das Template `celery_monitor.html`
- `templates/celery_monitor.html`

## Verwendung

```python
from fastapi import FastAPI
from celery_tasks.celery_config import app as celery_app
from utils.deps import get_current_active_admin

from fastapi_celery_task_manager import (
    get_celery_admin_router,
    get_celery_admin_ui_router,
)

app = FastAPI()

app.include_router(
    get_celery_admin_router(
        celery_app=celery_app,
        admin_dependency=get_current_active_admin,
        prefix="/api/celery",
    )
)

# UI: nutzt standardmäßig Templates aus dem Paket selbst (PackageLoader)
app.include_router(
    get_celery_admin_ui_router(
        admin_dependency=get_current_active_admin,
        path="/admin/celery",
        include_package_templates=True,
        templates_dir=None,
    )
)

# Optional: zusätzlich App-Templates priorisieren (z.B. für Overrides/Branding)
# app.include_router(
#     get_celery_admin_ui_router(
#         admin_dependency=get_current_active_admin,
#         path="/admin/celery",
#         include_package_templates=True,
#         templates_dir="templates",
#     )
# )
```

### Hinweis Auth
Die API ist (wie im EvalCenter-Backend) typischerweise per `OAuth2PasswordBearer`/Bearer-Token geschützt. Das Template sendet einen `Authorization`-Header, falls im Browser ein Token in `localStorage`/`sessionStorage` liegt.

## Template-Integration
Ab jetzt ist **kein Kopieren** des Templates mehr notwendig: standardmäßig kann die UI-Route das Template direkt aus dem installierten Paket laden.
Wenn du trotzdem ein eigenes Template in deiner App bereitstellen willst, kannst du `templates_dir="templates"` setzen – dieses Verzeichnis wird dann vor den Paket-Templates durchsucht.
