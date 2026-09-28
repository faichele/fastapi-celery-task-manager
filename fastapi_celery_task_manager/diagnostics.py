"""Celery configuration diagnostic tool.

Generalized from a project-specific `check_celery_config.py` script: instead
of importing one hardcoded project's Celery app, the app is loaded from a
``module.path:attribute`` import string given via ``--app`` (same convention
as `fastapi_celery_task_manager.cli`).

Run:
    python -m fastapi_celery_task_manager.diagnostics --app myapp.celery_app:celery_app
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from .app_loader import load_celery_app

REQUIRED_ENV_VARS = {
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
}


def check_env_variables(required_env_vars: dict) -> bool:
    print("=" * 60)
    print("1. Checking Environment Variables")
    print("=" * 60)

    all_good = True
    for var, default in required_env_vars.items():
        value = os.getenv(var)
        if value:
            print(f"OK   {var}: {value}")
            if var == "CELERY_BROKER_URL" and not (
                value.startswith("redis://") or value.startswith("rediss://") or value.startswith("amqp://")
            ):
                print(f"     WARNING: unexpected protocol '{value.split('://')[0]}://' (expected redis/rediss/amqp)")
                all_good = False
        else:
            print(f"FAIL {var}: not set (example default: {default})")
            all_good = False

    print()
    return all_good


def check_redis_connection(broker_url: Optional[str]) -> bool:
    print("=" * 60)
    print("2. Checking Redis Connection")
    print("=" * 60)

    if not broker_url:
        print("SKIP no broker URL to check")
        print()
        return True

    if not (broker_url.startswith("redis://") or broker_url.startswith("rediss://")):
        print(f"SKIP non-redis broker ({broker_url.split('://')[0]}://)")
        print()
        return True

    try:
        import redis
    except ImportError:
        print("FAIL redis library not installed")
        print("     Install with: pip install 'fastapi-celery-task-manager[diagnostics]'")
        print()
        return False

    try:
        parts = broker_url.split("://", 1)[1].split("/")
        host_port = parts[0].split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 6379
        db = int(parts[1]) if len(parts) > 1 and parts[1] else 0

        print(f"Connecting to Redis at {host}:{port} (db={db})...")
        r = redis.Redis(host=host, port=port, db=db, socket_timeout=5)
        if r.ping():
            info = r.info()
            print("OK   Redis connection successful")
            print(f"     Redis version: {info.get('redis_version', 'unknown')}")
            print(f"     Connected clients: {info.get('connected_clients', 'unknown')}")
            print(f"     Used memory: {info.get('used_memory_human', 'unknown')}")
            return True
        print("FAIL Redis ping failed")
        return False
    except Exception as e:
        print(f"FAIL Redis connection failed: {e}")
        return False
    finally:
        print()


def check_celery_config(app_import_path: str) -> bool:
    print("=" * 60)
    print("3. Checking Celery Configuration")
    print("=" * 60)

    try:
        celery_app = load_celery_app(app_import_path)
        print("OK   Celery app loaded successfully")
        print(f"     App name: {celery_app.main}")
        print(f"     Broker: {celery_app.conf.broker_url}")
        print(f"     Backend: {celery_app.conf.result_backend}")

        tasks = list(celery_app.tasks.keys())
        user_tasks = [t for t in tasks if not t.startswith("celery.")]
        print(f"     Registered tasks: {len(user_tasks)}")
        for task in user_tasks[:5]:
            print(f"       - {task}")
        if len(user_tasks) > 5:
            print(f"       ... and {len(user_tasks) - 5} more")
        return True
    except SystemExit as e:
        print(f"FAIL {e}")
        return False
    except Exception as e:
        print(f"FAIL Failed to load Celery configuration: {e}")
        return False
    finally:
        print()


def check_dependencies() -> bool:
    print("=" * 60)
    print("4. Checking Dependencies")
    print("=" * 60)

    required_packages = {
        "celery": "Celery task queue",
        "kombu": "Celery messaging library",
    }
    optional_packages = {
        "redis": "Redis client (only needed for a redis:// broker)",
        "fastapi": "FastAPI framework (only needed if this admin router is mounted)",
        "watchdog": "File watching (only needed for `cli.py debug-watch`)",
    }

    all_required_installed = True
    for package, description in required_packages.items():
        try:
            module = __import__(package)
            version = getattr(module, "__version__", "unknown")
            print(f"OK   {package} ({description}): {version}")
        except ImportError:
            print(f"FAIL {package} ({description}): not installed")
            all_required_installed = False

    for package, description in optional_packages.items():
        try:
            module = __import__(package)
            version = getattr(module, "__version__", "unknown")
            print(f"OK   {package} ({description}): {version}")
        except ImportError:
            print(f"INFO {package} ({description}): not installed (optional)")

    print()
    return all_required_installed


def run_diagnostics(app_import_path: str, required_env_vars: Optional[dict] = None) -> bool:
    required_env_vars = required_env_vars if required_env_vars is not None else REQUIRED_ENV_VARS

    try:
        from dotenv import load_dotenv

        env_file = os.path.join(os.getcwd(), ".env")
        if os.path.exists(env_file):
            load_dotenv(env_file)
            print(f"Loaded environment from: {env_file}\n")
    except ImportError:
        pass

    results: List[tuple] = []
    results.append(("Environment Variables", check_env_variables(required_env_vars)))
    results.append(("Redis Connection", check_redis_connection(os.getenv("CELERY_BROKER_URL"))))
    results.append(("Dependencies", check_dependencies()))
    results.append(("Celery Configuration", check_celery_config(app_import_path)))

    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for name, success in results:
        print(f"{'PASS' if success else 'FAIL'}: {name}")

    all_passed = all(success for _, success in results)
    print()
    if all_passed:
        print("All checks passed.")
        print(f"Start a worker with: python -m fastapi_celery_task_manager.cli worker --app {app_import_path}")
    else:
        print("Some checks failed; see details above.")
    return all_passed


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fastapi_celery_task_manager.diagnostics")
    parser.add_argument(
        "--app",
        required=True,
        help="Celery app import path as 'module.path:attribute', e.g. 'myapp.celery_app:celery_app'.",
    )
    args = parser.parse_args(argv)
    ok = run_diagnostics(args.app)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
