Dieses Verzeichnis enthält die Jinja2-Templates, die zur optionalen Admin-UI gehören.

- `celery_monitor.html`: UI, die die REST-Endpunkte aus `get_celery_admin_router()` aufruft.

Hinweis: Damit FastAPI/Jinja2 dieses Template rendern kann, muss das Template-Verzeichnis
in deiner App als `Jinja2Templates(directory=...)` verfügbar gemacht werden oder die Datei
in das App-Template-Verzeichnis kopiert werden.
