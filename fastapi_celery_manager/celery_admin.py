"""FastAPI router for basic Celery administration.

This module is extracted from the EvalCenter backend to be reusable from an external package.

Design goals:
- No subprocess calls; use Celery Python API.
- Let the embedding application provide:
  - the Celery app instance
  - the admin auth dependency (e.g. `get_current_active_admin`)
- Keep an API compatible with the original endpoints in `routes/celery_admin.py`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional

from celery import Celery
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class TaskInfoResponse(BaseModel):
    id: str
    name: str
    worker: str
    args: List[Any] = Field(default_factory=list)
    kwargs: Dict[str, Any] = Field(default_factory=dict)
    time_start: Optional[str] = None
    eta: Optional[str] = None
    queue: Optional[str] = None


class WorkerInfoResponse(BaseModel):
    name: str
    pool_implementation: str
    max_concurrency: int
    total_tasks: int
    broker_transport: str


class TaskStatsResponse(BaseModel):
    active_workers: int
    active_tasks: int
    reserved_tasks: int
    scheduled_tasks: int


class EnqueueTaskRequest(BaseModel):
    task_name: str = Field(..., examples=["celery_tasks.celery_report_processor.process_inspection_report_task"])
    args: List[Any] = Field(default_factory=list)
    kwargs: Dict[str, Any] = Field(default_factory=dict)

    # routing
    queue: Optional[str] = None
    routing_key: Optional[str] = None

    # scheduling
    countdown: Optional[int] = Field(default=None, ge=0)
    eta: Optional[datetime] = None
    expires: Optional[int] = Field(default=None, ge=0)


class EnqueueTaskResponse(BaseModel):
    task_id: str
    task_name: str
    queue: Optional[str] = None
    routing_key: Optional[str] = None


class RevokeTaskRequest(BaseModel):
    terminate: bool = False
    signal: str = "TERM"


class RevokeTaskResponse(BaseModel):
    task_id: str
    revoked: bool


class ShutdownWorkerRequest(BaseModel):
    warm: bool = True


class ShutdownWorkerResponse(BaseModel):
    worker_name: str
    shutdown_sent: bool


class PurgeResponse(BaseModel):
    purged: Dict[str, int] = Field(default_factory=dict)


class TaskResultResponse(BaseModel):
    """Fetch task state/result from the Celery result backend."""

    task_id: str
    state: str
    ready: bool
    successful: Optional[bool] = None
    result: Optional[Any] = None
    traceback: Optional[str] = None


CeleryTaskState = Literal["active", "reserved", "scheduled"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TASK_QUEUE_MAPPING: Dict[str, Dict[str, str]] = {
    "celery_tasks.celery_file_system_monitor.*": {"queue": "file_system_monitors", "routing_key": "file_system_monitors"},
    "celery_tasks.celery_report_processor.*": {"queue": "report_processing", "routing_key": "report_processing.default"},
    "celery_tasks.celery_image_processor.*": {"queue": "image_processing", "routing_key": "image_processing.default"},
    "celery_tasks.celery_volume_processor.*": {"queue": "volume_processing", "routing_key": "volume_processing.default"},
}


def _get_queue_for_task(task_name: str) -> Optional[Dict[str, str]]:
    import re

    for pattern, queue_info in TASK_QUEUE_MAPPING.items():
        regex_pattern = pattern.replace("*", ".*")
        if re.match(regex_pattern, task_name):
            return queue_info
    return None


class _Inspector:
    def __init__(self, app: Celery):
        self.inspect = app.control.inspect()

    def active(self) -> Dict[str, Any]:
        return self.inspect.active() or {}

    def reserved(self) -> Dict[str, Any]:
        return self.inspect.reserved() or {}

    def scheduled(self) -> Dict[str, Any]:
        return self.inspect.scheduled() or {}

    def stats(self) -> Dict[str, Any]:
        return self.inspect.stats() or {}

    def registered(self) -> Dict[str, Any]:
        return self.inspect.registered() or {}


AdminDependency = Callable[..., Any]


def get_celery_admin_router(
    *,
    celery_app: Celery,
    admin_dependency: AdminDependency,
    prefix: str = "/api/celery",
) -> APIRouter:
    """Create an APIRouter with admin-protected Celery endpoints."""

    router = APIRouter(prefix=prefix, tags=["celery"], dependencies=[Depends(admin_dependency)])

    @router.get("/workers", response_model=List[WorkerInfoResponse])
    def list_workers(worker: Optional[str] = None) -> List[WorkerInfoResponse]:
        insp = _Inspector(celery_app)
        stats = insp.stats()

        workers: List[WorkerInfoResponse] = []
        for worker_name, stat in stats.items():
            if worker and worker not in worker_name:
                continue

            total_tasks = stat.get("total", {})
            if isinstance(total_tasks, dict):
                total_count = sum(total_tasks.values()) if total_tasks else 0
            else:
                try:
                    total_count = int(total_tasks)
                except Exception:
                    total_count = 0

            workers.append(
                WorkerInfoResponse(
                    name=worker_name,
                    pool_implementation=stat.get("pool", {}).get("implementation", "unknown"),
                    max_concurrency=stat.get("pool", {}).get("max-concurrency", 0),
                    total_tasks=total_count,
                    broker_transport=stat.get("broker", {}).get("transport", "unknown"),
                )
            )

        return workers

    @router.get("/tasks", response_model=List[TaskInfoResponse])
    def list_tasks(
        states: List[CeleryTaskState] = Query(default=["active", "reserved", "scheduled"]),
        worker: Optional[str] = None,
    ) -> List[TaskInfoResponse]:
        insp = _Inspector(celery_app)

        out: List[TaskInfoResponse] = []

        if "active" in states:
            active = insp.active()
            for worker_name, tasks in active.items():
                if worker and worker not in worker_name:
                    continue
                for task in tasks or []:
                    out.append(
                        TaskInfoResponse(
                            id=task.get("id", ""),
                            name=task.get("name", ""),
                            worker=worker_name,
                            args=task.get("args", []) or [],
                            kwargs=task.get("kwargs", {}) or {},
                            time_start=str(task.get("time_start", "")),
                            queue="active",
                        )
                    )

        if "reserved" in states:
            reserved = insp.reserved()
            for worker_name, tasks in reserved.items():
                if worker and worker not in worker_name:
                    continue
                for task in tasks or []:
                    out.append(
                        TaskInfoResponse(
                            id=task.get("id", ""),
                            name=task.get("name", ""),
                            worker=worker_name,
                            args=task.get("args", []) or [],
                            kwargs=task.get("kwargs", {}) or {},
                            queue="reserved",
                        )
                    )

        if "scheduled" in states:
            scheduled = insp.scheduled()
            for worker_name, tasks in scheduled.items():
                if worker and worker not in worker_name:
                    continue
                for task in tasks or []:
                    task_request = task.get("request", {}) if isinstance(task, dict) else {}
                    out.append(
                        TaskInfoResponse(
                            id=task_request.get("id", task.get("task", "")),
                            name=task_request.get("task", task.get("task", "")),
                            worker=worker_name,
                            args=task_request.get("args", []) or [],
                            kwargs=task_request.get("kwargs", {}) or {},
                            eta=str(task.get("eta", "")),
                            queue="scheduled",
                        )
                    )

        return out

    @router.get("/tasks/stats", response_model=TaskStatsResponse)
    def get_task_stats(worker: Optional[str] = None) -> TaskStatsResponse:
        workers = list_workers(worker=worker)
        tasks = list_tasks(worker=worker)

        return TaskStatsResponse(
            active_workers=len(workers),
            active_tasks=sum(1 for t in tasks if t.queue == "active"),
            reserved_tasks=sum(1 for t in tasks if t.queue == "reserved"),
            scheduled_tasks=sum(1 for t in tasks if t.queue == "scheduled"),
        )

    @router.get("/tasks/registered", response_model=List[str])
    def list_registered_tasks() -> List[str]:
        insp = _Inspector(celery_app)
        registered = insp.registered() or {}
        all_tasks = set()
        for _worker, tasks in registered.items():
            for t in tasks or []:
                all_tasks.add(t)
        return sorted(all_tasks)

    @router.post("/tasks/enqueue", response_model=EnqueueTaskResponse, status_code=201)
    def enqueue_task(req: EnqueueTaskRequest) -> EnqueueTaskResponse:
        queue = req.queue
        routing_key = req.routing_key

        if not queue or not routing_key:
            queue_info = _get_queue_for_task(req.task_name)
            if queue_info:
                queue = queue or queue_info.get("queue")
                routing_key = routing_key or queue_info.get("routing_key")

        task_options: Dict[str, Any] = {}
        if queue:
            task_options["queue"] = queue
        if routing_key:
            task_options["routing_key"] = routing_key
        if req.countdown is not None:
            task_options["countdown"] = req.countdown
        if req.eta is not None:
            task_options["eta"] = req.eta
        if req.expires is not None:
            task_options["expires"] = req.expires

        try:
            result = celery_app.send_task(req.task_name, args=req.args, kwargs=req.kwargs, **task_options)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to enqueue task: {e}") from e

        return EnqueueTaskResponse(task_id=result.id, task_name=req.task_name, queue=queue, routing_key=routing_key)

    @router.post("/tasks/{task_id}/revoke", response_model=RevokeTaskResponse)
    def revoke_task(task_id: str, req: RevokeTaskRequest) -> RevokeTaskResponse:
        try:
            res = celery_app.control.revoke(task_id, terminate=req.terminate, signal=req.signal)
            ok = bool(res)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to revoke task: {e}") from e
        return RevokeTaskResponse(task_id=task_id, revoked=ok)

    @router.post("/workers/{worker_name}/shutdown", response_model=ShutdownWorkerResponse)
    def shutdown_worker(worker_name: str, req: ShutdownWorkerRequest) -> ShutdownWorkerResponse:
        try:
            # Celery supports shutdown broadcast as best-effort.
            res = celery_app.control.broadcast("shutdown", destination=[worker_name])
            ok = bool(res)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to shutdown worker: {e}") from e
        return ShutdownWorkerResponse(worker_name=worker_name, shutdown_sent=ok)

    @router.post("/queues/purge", response_model=PurgeResponse)
    def purge_queues() -> PurgeResponse:
        try:
            purged = celery_app.control.purge() or {}
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to purge queues: {e}") from e
        if isinstance(purged, int):
            purged = {"default": purged}
        return PurgeResponse(purged=purged)

    @router.get("/tasks/{task_id}", response_model=TaskResultResponse)
    def get_task_result(task_id: str) -> TaskResultResponse:
        try:
            r = AsyncResult(task_id, app=celery_app)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create AsyncResult: {e}") from e

        result_value: Optional[Any] = None
        if r.ready():
            try:
                result_value = r.get(propagate=False)
            except Exception:
                result_value = None

        try:
            successful = r.successful() if r.ready() else None
        except Exception:
            successful = None

        try:
            tb = r.traceback
        except Exception:
            tb = None

        return TaskResultResponse(
            task_id=task_id,
            state=str(getattr(r, "state", "UNKNOWN")),
            ready=bool(r.ready()),
            successful=successful,
            result=result_value,
            traceback=tb,
        )

    return router
