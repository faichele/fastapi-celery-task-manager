# fastapi-celery-task-manager

Kleines, eigenständiges Paket mit einem FastAPI-`APIRouter` für grundlegende Celery-Administration (Inspect/Enqueue/Control), einem Jinja2-Template für eine simple Admin-UI, sowie einer projektunabhängigen CLI zum Starten von Worker/Beat und zum Dispatchen von Tasks.

## Enthalten
- `get_celery_admin_router(...)` → REST-Endpunkte unter `/api/celery`
- `get_celery_admin_ui_router(...)` → HTML-Route (Default: `/admin/celery`), rendert das Template `celery_monitor.html`
- `templates/celery_monitor.html`
- `dispatch_task(...)` / `resolve_queue(...)` → Task-Dispatching als reine Python-API, ohne HTTP (siehe [Job Dispatching](#job-dispatching))
- `python -m fastapi_celery_task_manager.cli` (bzw. `fctm-worker`) → generischer Worker-/Beat-/Debug-Runner (siehe [CLI: Worker, Beat, Debug](#cli-worker-beat-debug))
- `python -m fastapi_celery_task_manager.diagnostics` (bzw. `fctm-doctor`) → Konfigurations-Diagnose (Broker, Redis, Dependencies, registrierte Tasks)

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

### `task_queue_mapping` (Routing für `/tasks/enqueue`)
`get_celery_admin_router` akzeptiert optional `task_queue_mapping`, um Task-Namen (Glob-Pattern, z.B. `"myapp.tasks.*"`) auf `{"queue": ..., "routing_key": ...}` abzubilden, wenn ein Enqueue-Request Queue/Routing-Key nicht explizit angibt. Der Default ist aus Kompatibilitätsgründen das historische EvalCenter-Mapping; jedes andere Projekt sollte sein eigenes Mapping übergeben (oder `None`, um die automatische Zuordnung abzuschalten):

```python
app.include_router(
    get_celery_admin_router(
        celery_app=celery_app,
        admin_dependency=get_current_active_admin,
        task_queue_mapping={
            "myapp.tasks.image.*": {"queue": "images", "routing_key": "images.default"},
        },
    )
)
```

## Job Dispatching

Zusätzlich zum HTTP-Endpoint `POST /api/celery/tasks/enqueue` lässt sich ein Task auch direkt aus Python dispatchen (CLI-Skripte, andere Background-Jobs, Tests) – ohne laufenden FastAPI-Request:

```python
from fastapi_celery_task_manager import dispatch_task

result = dispatch_task(
    celery_app,
    "myapp.tasks.image.resize",
    kwargs={"image_id": 42},
    task_queue_mapping={"myapp.tasks.image.*": {"queue": "images", "routing_key": "images.default"}},
)
print(result.task_id, result.queue)
```

`dispatch_task` ist genau die Logik, die der Router intern für `/tasks/enqueue` verwendet – beide Wege teilen sich dieselbe Queue-Auflösung (`resolve_queue`).

## CLI: Worker, Beat, Debug

`fastapi_celery_task_manager.cli` ist ein projektunabhängiger Ersatz für einen händisch gepflegten `celery_worker.py`-Skript pro Projekt. Statt fest einprogrammierter App-Aliase wird die Celery-App über einen Importpfad (`module.pfad:attribut`) geladen, sodass sich dieselbe CLI in jedem Projekt unverändert verwenden lässt.

```bash
# Worker starten
python -m fastapi_celery_task_manager.cli worker --app myapp.celery_app:celery_app --queues default --loglevel INFO

# Beat starten
python -m fastapi_celery_task_manager.cli beat --app myapp.celery_app:celery_app

# Task synchron ohne Broker ausführen (Debugging)
python -m fastapi_celery_task_manager.cli debug --app myapp.celery_app:celery_app --task myapp.tasks.ping

# Wie debug, aber automatischer Neustart bei Codeänderungen (braucht das "cli"-Extra)
python -m fastapi_celery_task_manager.cli debug-watch --app myapp.celery_app:celery_app --task myapp.tasks.ping --watch ./myapp
```

Nach der Installation steht dieselbe CLI auch als Kommando `fctm-worker` zur Verfügung (siehe `[project.scripts]` in `pyproject.toml`).

`debug-watch` benötigt die optionale Abhängigkeit `watchdog`, installierbar über das Extra `cli`:

```bash
pip install "fastapi-celery-task-manager[cli]"
```

## Diagnose

`fastapi_celery_task_manager.diagnostics` prüft Broker-/Backend-Umgebungsvariablen, die Redis-Verbindung (falls der Broker `redis://`/`rediss://` ist), installierte Abhängigkeiten und ob sich die Celery-App laden lässt inkl. registrierter Tasks:

```bash
python -m fastapi_celery_task_manager.diagnostics --app myapp.celery_app:celery_app
# oder nach Installation:
fctm-doctor --app myapp.celery_app:celery_app
```

Die Redis-Prüfung und das optionale `.env`-Laden benötigen die Extras `redis` bzw. `python-dotenv`, installierbar über:

```bash
pip install "fastapi-celery-task-manager[diagnostics]"
```
