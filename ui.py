"""FastAPI HTML route (Jinja2 template) for the Celery admin router.

The UI talks to the REST endpoints under `/api/celery` via fetch().

Template sourcing:
- By default, we can load templates directly from this package (package resources).
- Optionally, an application can provide an additional templates directory.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.routing import APIRoute

from jinja2 import ChoiceLoader, FileSystemLoader, PackageLoader


AdminDependency = Callable[..., Any]


class _RedirectOnAuthErrorRoute(APIRoute):
    """APIRoute that converts auth errors (401/403) into a redirect to the login page.

    This keeps auth evaluation inside FastAPI's dependency system (no manual dependency calls)
    and still provides a smooth browser navigation UX.
    """

    def __init__(self, *args: Any, login_path: str = "/login", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._login_path = login_path

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def custom_handler(request: Request):
            try:
                return await original_handler(request)
            except Exception as e:
                status_code = getattr(e, "status_code", None)
                if status_code in (401, 403):
                    next_url = request.url.path
                    return RedirectResponse(url=f"{self._login_path}?next={next_url}")
                raise

        return custom_handler


def get_celery_admin_ui_router(
    *,
    admin_dependency: AdminDependency,
    # If set, templates are loaded from this directory in addition to the package templates.
    templates_dir: Optional[str] = None,
    prefix: str = "",
    path: str = "/admin/celery",
    template_name: str = "celery_monitor.html",
    extra_context: Optional[Dict[str, Any]] = None,
    # When true (default), also search templates shipped with this package.
    include_package_templates: bool = True,
) -> APIRouter:
    """Create a small router providing an admin-protected HTML page.

    If `include_package_templates=True`, the function will also load templates from
    `fastapi_celery_manager/templates` inside the installed package.
    """

    router = APIRouter(prefix=prefix, include_in_schema=False)

    # Build a loader chain: app templates first (if provided), then package templates.
    loaders = []
    if templates_dir:
        loaders.append(FileSystemLoader(templates_dir))
    if include_package_templates:
        loaders.append(PackageLoader("fastapi_celery_manager", "../templates"))

    templates = Jinja2Templates(directory=".")
    templates.env.loader = ChoiceLoader(loaders) if len(loaders) > 1 else loaders[0]

    @router.get(path, response_class=HTMLResponse)
    async def celery_admin_page(
        request: Request,
        _admin: object = Depends(admin_dependency),
    ):
        ctx: Dict[str, Any] = {"request": request, "title": "Celery Admin"}
        if extra_context:
            ctx.update(extra_context)
        return templates.TemplateResponse(template_name, ctx)

    return router


def get_celery_admin_ui_router_with_login_redirect(
    *,
    admin_dependency: AdminDependency,
    templates_dir: Optional[str] = None,
    prefix: str = "",
    path: str = "/admin/celery",
    template_name: str = "celery_monitor.html",
    extra_context: Optional[Dict[str, Any]] = None,
    include_package_templates: bool = True,
    login_path: str = "/login",
) -> APIRouter:
    """Like `get_celery_admin_ui_router`, but redirects to login on 401/403.

    Implementation detail:
    - The endpoint still uses FastAPI dependencies (`Depends(admin_dependency)`).
    - We register the route using a custom `APIRoute` implementation that wraps the handler.
    """

    router = APIRouter(prefix=prefix, include_in_schema=False)

    loaders = []
    if templates_dir:
        loaders.append(FileSystemLoader(templates_dir))
    if include_package_templates:
        loaders.append(PackageLoader("fastapi_celery_manager", "../templates"))

    templates = Jinja2Templates(directory=".")
    templates.env.loader = ChoiceLoader(loaders) if len(loaders) > 1 else loaders[0]

    async def endpoint(
        request: Request,
        _admin: object = Depends(admin_dependency),
    ):
        ctx: Dict[str, Any] = {"request": request, "title": "Celery Admin"}
        if extra_context:
            ctx.update(extra_context)
        return templates.TemplateResponse(template_name, ctx)

    # Register route with redirect-on-auth-error behaviour.
    route = _RedirectOnAuthErrorRoute(
        path=path,
        endpoint=endpoint,
        methods=["GET"],
        response_class=HTMLResponse,
        name="celery_admin_page",
        login_path=login_path,
    )
    router.routes.append(route)

    return router
