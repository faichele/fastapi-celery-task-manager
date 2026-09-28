"""Reusable CLI to start/debug a Celery worker or beat scheduler.

Generalized from a project-specific `celery_worker.py` script: instead of a
hardcoded map of app aliases, the Celery app is loaded from a
``module.path:attribute`` import string given via ``--app``, so any project
using this package can reuse the same CLI as-is.

Run (examples):
    python -m fastapi_celery_task_manager.cli worker --app myapp.celery_app:celery_app --queues default --loglevel INFO
    python -m fastapi_celery_task_manager.cli beat --app myapp.celery_app:celery_app --loglevel INFO

Debug without a broker (run a task synchronously, in-process):
    python -m fastapi_celery_task_manager.cli debug --app myapp.celery_app:celery_app --task myapp.tasks.ping

Debug with auto-restart on file changes (requires the optional `watchdog`
dependency; install via the `cli` extra):
    python -m fastapi_celery_task_manager.cli debug-watch --app myapp.celery_app:celery_app --task myapp.tasks.ping --watch ./myapp

If no `--hostname` is given for `worker`, one is generated from the local
hostname plus a random suffix (e.g. ``myhost-3f2a9c1b``), so multiple workers
can run on the same host without colliding.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import secrets
import socket
import sys
import time
from fnmatch import fnmatch
from typing import Any, List, Sequence

from celery import Celery

from .app_loader import load_celery_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


_HOSTNAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _sanitize_worker_hostname(value: str) -> str:
    """Sanitizes a Celery worker hostname to a safe subset.

    Celery hostnames may contain ``@`` (workername@hostname). We pass the
    value via ``--hostname=...`` and keep it conservative to avoid surprises.
    """
    v = (value or "").strip()
    if not v:
        return "unknown-host"
    v = _HOSTNAME_SAFE_RE.sub("-", v)
    return v.strip("-.") or "unknown-host"


def _generate_default_worker_hostname() -> str:
    """Generates a unique worker hostname: ``<system-hostname>-<random-suffix>``."""
    base = _sanitize_worker_hostname(socket.gethostname())
    suffix = secrets.token_hex(4)
    return f"{base}-{suffix}"


def _resolve_worker_hostname(args: Any) -> str:
    explicit = getattr(args, "hostname", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit
    return _generate_default_worker_hostname()


def _build_worker_argv(args: Any) -> List[str]:
    """Builds argv for `celery_app.worker_main`.

    Accepts `Any` deliberately, so tests can pass a dummy args object.
    """
    argv: List[str] = [
        "worker",
        f"--loglevel={getattr(args, 'loglevel', 'INFO')}",
    ]

    if getattr(args, "beat", False):
        argv.append("--beat")

    queues = getattr(args, "queues", None)
    if queues:
        argv.append(f"--queues={queues}")
    concurrency = getattr(args, "concurrency", None)
    if concurrency is not None:
        argv.append(f"--concurrency={concurrency}")
    pool = getattr(args, "pool", None)
    if pool:
        argv.append(f"--pool={pool}")

    hostname = _resolve_worker_hostname(args)
    argv.append(f"--hostname={hostname}")

    if getattr(args, "autoreload", False):
        argv.append("--autoreload")
    if getattr(args, "without_gossip", False):
        argv.append("--without-gossip")
    if getattr(args, "without_mingle", False):
        argv.append("--without-mingle")
    if getattr(args, "without_heartbeat", False):
        argv.append("--without-heartbeat")

    return argv


def _build_beat_argv(args: Any) -> List[str]:
    argv: List[str] = [
        "beat",
        f"--loglevel={getattr(args, 'loglevel', 'INFO')}",
    ]
    scheduler = getattr(args, "scheduler", None)
    if scheduler:
        argv.append(f"--scheduler={scheduler}")
    pidfile = getattr(args, "pidfile", None)
    if pidfile:
        argv.append(f"--pidfile={pidfile}")
    return argv


def _parse_arg_value(raw: str) -> Any:
    """Parses a debug arg/kwarg value: JSON if it looks like JSON, else a plain string."""
    s = raw.strip()
    if not s:
        return s
    if s[0] in "[{\"" or s in {"true", "false", "null"} or s[0].isdigit() or (s[0] == "-" and len(s) > 1 and s[1].isdigit()):
        try:
            return json.loads(s)
        except Exception:
            return raw
    return raw


def _run_debug_task(celery_app: Celery, task_name: str, raw_args: List[str], raw_kwargs: List[str]) -> Any:
    """Runs a task synchronously in-process (no broker needed).

    - task_name: task name as registered via `@celery_app.task(name=...)`
    - raw_args: list of strings, parsed loosely as JSON
    - raw_kwargs: list of `key=value` strings (values also parsed as JSON)
    """
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    task = celery_app.tasks.get(task_name)
    if task is None:
        available = ", ".join(sorted(celery_app.tasks.keys()))
        raise SystemExit(f"Task '{task_name}' not found. Available: {available}")

    args = [_parse_arg_value(a) for a in raw_args]
    kwargs = {}
    for kv in raw_kwargs:
        if "=" not in kv:
            raise SystemExit(f"Invalid --kwarg '{kv}', expected key=value")
        k, v = kv.split("=", 1)
        kwargs[k] = _parse_arg_value(v)

    result = task.apply(args=args, kwargs=kwargs)
    # apply() returns an EagerResult; .get() raises (task_eager_propagates=True)
    return result.get()


def _default_ignore_patterns() -> List[str]:
    return [
        "*/__pycache__/*",
        "*/.pytest_cache/*",
        "*/.mypy_cache/*",
        "*/.ruff_cache/*",
        "*/.tox/*",
        "*/.venv/*",
        "*/venv/*",
        "*/env/*",
        "*/.env/*",
        "*/site-packages/*",
        "*/dist/*",
        "*/build/*",
        "*/.eggs/*",
        "*/node_modules/*",
        "*/.git/*",
        "*/.idea/*",
        "*/.vscode/*",
    ]


def _is_ignored_path(path: str, ignore_patterns: Sequence[str]) -> bool:
    p = os.path.normpath(path).replace(os.sep, "/")
    for pat in ignore_patterns:
        if fnmatch(p, pat):
            return True
        if "*" not in pat and "?" not in pat and pat.strip("/") and pat.strip("/") in p:
            return True
    return False


def _should_restart_for_path(path: str) -> bool:
    p = path.lower()
    if p.endswith(".py"):
        return True
    if os.path.basename(p) in {".env"}:
        return True
    return False


def _require_watchdog():
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError as exc:
        raise SystemExit(
            "The 'debug-watch' command needs the optional 'watchdog' dependency. "
            "Install it with: pip install 'fastapi-celery-task-manager[cli]'"
        ) from exc
    return FileSystemEventHandler, Observer


def _run_debug_watch(
    celery_app: Celery,
    task_name: str,
    raw_args: List[str],
    raw_kwargs: List[str],
    watch_paths: List[str],
    debounce_s: float = 0.25,
    ignore_patterns: Sequence[str] | None = None,
) -> int:
    """Runs the debug task, then reruns it whenever a watched file changes.

    Implementation note: a restart happens via `execv`, so module-level
    state is genuinely fresh on every run.
    """
    FileSystemEventHandler, Observer = _require_watchdog()
    ignore_patterns = list(ignore_patterns or _default_ignore_patterns())

    class _RestartOnChangeHandler(FileSystemEventHandler):
        def __init__(self) -> None:
            super().__init__()
            self.restart_requested = False

        def on_any_event(self, event):  # type: ignore[override]
            src_path = getattr(event, "src_path", "") or ""
            if not src_path:
                return
            if _is_ignored_path(src_path, ignore_patterns):
                return
            if _should_restart_for_path(src_path):
                self.restart_requested = True

    handler = _RestartOnChangeHandler()
    observer = Observer()
    for p in watch_paths:
        observer.schedule(handler, p, recursive=True)

    observer.start()
    try:
        while True:
            handler.restart_requested = False
            out = _run_debug_task(celery_app, task_name, raw_args, raw_kwargs)
            try:
                print(json.dumps(out, ensure_ascii=False, indent=2))
            except Exception:
                print(out)

            while not handler.restart_requested:
                time.sleep(0.1)
            time.sleep(max(0.0, float(debounce_s)))

            os.execv(sys.executable, [sys.executable, "-m", "fastapi_celery_task_manager.cli", "debug-watch", *sys.argv[2:]])
    except KeyboardInterrupt:
        observer.stop()
        observer.join(timeout=2)
    finally:
        if observer.is_alive():
            observer.stop()
            observer.join(timeout=2)
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fastapi_celery_task_manager.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--app",
            required=True,
            help="Celery app import path as 'module.path:attribute', e.g. 'myapp.celery_app:celery_app'.",
        )
        p.add_argument("--loglevel", default="INFO", help="Celery loglevel (e.g. DEBUG, INFO, WARNING)")

    p_worker = sub.add_parser("worker", help="Start a Celery worker")
    add_common(p_worker)
    p_worker.add_argument("--queues", default=None, help="Queue(s), comma-separated")
    p_worker.add_argument("--concurrency", type=int, default=None)
    p_worker.add_argument("--pool", default=None, help="pool: prefork, solo, threads, gevent")
    p_worker.add_argument(
        "--hostname",
        default=None,
        help=(
            "Worker hostname/name. If unset, '<hostname>-<random>' is generated automatically, "
            "so multiple workers can run on the same host in parallel."
        ),
    )
    p_worker.add_argument("--beat", action="store_true", help="Start beat alongside the worker (handy for development)")
    p_worker.add_argument("--autoreload", action="store_true")
    p_worker.add_argument("--without-gossip", action="store_true")
    p_worker.add_argument("--without-mingle", action="store_true")
    p_worker.add_argument("--without-heartbeat", action="store_true")

    p_beat = sub.add_parser("beat", help="Start Celery beat (scheduler)")
    add_common(p_beat)
    p_beat.add_argument("--scheduler", default=None)
    p_beat.add_argument("--pidfile", default=None)

    p_debug = sub.add_parser("debug", help="Run exactly one task synchronously (no broker)")
    add_common(p_debug)
    p_debug.add_argument("--task", required=True, help="Task name (e.g. myapp.tasks.ping)")
    p_debug.add_argument("--args", nargs="*", default=[], help="Positional args (optional; JSON is attempted)")
    p_debug.add_argument("--kwargs", nargs="*", default=[], help="Keyword args as key=value (values: JSON is attempted)")

    p_debug_watch = sub.add_parser("debug-watch", help="Run a task synchronously, rerunning it on code changes")
    add_common(p_debug_watch)
    p_debug_watch.add_argument("--task", required=True, help="Task name (e.g. myapp.tasks.ping)")
    p_debug_watch.add_argument("--args", nargs="*", default=[], help="Positional args (optional; JSON is attempted)")
    p_debug_watch.add_argument("--kwargs", nargs="*", default=[], help="Keyword args as key=value (values: JSON is attempted)")
    p_debug_watch.add_argument("--watch", nargs="*", default=None, help="Paths to watch (default: current directory)")
    p_debug_watch.add_argument("--debounce", type=float, default=0.25, help="Debounce seconds before restarting (default: 0.25)")
    p_debug_watch.add_argument(
        "--ignore",
        nargs="*",
        default=None,
        help=(
            "Ignore patterns (glob). Defaults include __pycache__, .venv, build, dist, "
            "node_modules, .git, .idea, etc. Example: --ignore '*/__pycache__/*' '*/build/*'"
        ),
    )

    args = parser.parse_args(argv)
    celery_app = load_celery_app(args.app)

    if args.command == "worker":
        worker_argv = _build_worker_argv(args)
        return celery_app.worker_main(worker_argv)

    if args.command == "beat":
        beat_argv = _build_beat_argv(args)
        celery_app.start(beat_argv)
        return 0

    if args.command == "debug":
        out = _run_debug_task(celery_app, args.task, args.args, args.kwargs)
        try:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        except Exception:
            print(out)
        return 0

    if args.command == "debug-watch":
        watch_paths = args.watch or [os.getcwd()]
        watch_paths = [os.path.abspath(p) for p in watch_paths]
        for p in watch_paths:
            if not os.path.exists(p):
                raise SystemExit(f"Watch path does not exist: {p}")
        return _run_debug_watch(
            celery_app,
            args.task,
            args.args,
            args.kwargs,
            watch_paths,
            debounce_s=args.debounce,
            ignore_patterns=args.ignore,
        )

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
