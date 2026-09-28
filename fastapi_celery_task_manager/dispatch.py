"""Generic Python API for dispatching Celery tasks.

Extracted from the admin router's `/tasks/enqueue` HTTP endpoint so an
embedding application (or a CLI script, a background job, a test) can
dispatch a task directly through `celery_app.send_task`, without going
through HTTP. `celery_admin.get_celery_admin_router` uses this module
internally so both call sites share one routing/enqueue implementation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from celery import Celery


@dataclass(frozen=True)
class DispatchResult:
    task_id: str
    task_name: str
    queue: Optional[str] = None
    routing_key: Optional[str] = None


def resolve_queue(
    task_name: str,
    task_queue_mapping: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> Optional[Dict[str, str]]:
    """Resolve `{"queue": ..., "routing_key": ...}` for a task name.

    `task_queue_mapping` maps a glob-style pattern (may contain `*`, e.g.
    ``"myapp.tasks.*"``) to that routing info. Patterns are matched in
    the mapping's iteration order; the first match wins. Returns `None`
    when no mapping is given or none of its patterns match.
    """
    if not task_queue_mapping:
        return None
    for pattern, queue_info in task_queue_mapping.items():
        regex_pattern = re.escape(pattern).replace(r"\*", ".*")
        if re.match(regex_pattern, task_name):
            return dict(queue_info)
    return None


def dispatch_task(
    celery_app: Celery,
    task_name: str,
    *,
    args: Optional[List[Any]] = None,
    kwargs: Optional[Dict[str, Any]] = None,
    queue: Optional[str] = None,
    routing_key: Optional[str] = None,
    countdown: Optional[int] = None,
    eta: Optional[datetime] = None,
    expires: Optional[int] = None,
    task_queue_mapping: Optional[Mapping[str, Mapping[str, str]]] = None,
) -> DispatchResult:
    """Enqueue a Celery task by name and return its dispatch result.

    If `queue`/`routing_key` are not given, they're looked up via
    `resolve_queue(task_name, task_queue_mapping)`. Raises whatever
    `celery_app.send_task` raises (e.g. a broker connection error) —
    callers that need an HTTP-friendly error should catch around this,
    as `celery_admin`'s endpoint does.
    """
    if not queue or not routing_key:
        queue_info = resolve_queue(task_name, task_queue_mapping)
        if queue_info:
            queue = queue or queue_info.get("queue")
            routing_key = routing_key or queue_info.get("routing_key")

    task_options: Dict[str, Any] = {}
    if queue:
        task_options["queue"] = queue
    if routing_key:
        task_options["routing_key"] = routing_key
    if countdown is not None:
        task_options["countdown"] = countdown
    if eta is not None:
        task_options["eta"] = eta
    if expires is not None:
        task_options["expires"] = expires

    result = celery_app.send_task(task_name, args=args or [], kwargs=kwargs or {}, **task_options)
    return DispatchResult(task_id=result.id, task_name=task_name, queue=queue, routing_key=routing_key)
