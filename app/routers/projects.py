from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Annotation, Image, Project

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def redirect_to_projects(request: Request):
    username = request.session.get("username", "")
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url="/projects", status_code=302)


@router.get("/projects", response_class=HTMLResponse)
async def list_projects(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(Project).options(selectinload(Project.images)))
    projects = result.scalars().all()

    project_stats = []
    for project in projects:
        total = len(project.images)
        image_ids = [img.id for img in project.images]
        if image_ids:
            # Count annotations by THIS user
            completed_result = await db.execute(
                select(func.count()).where(
                    Annotation.image_id.in_(image_ids),
                    Annotation.annotated_by == username,
                )
            )
            completed = completed_result.scalar() or 0
        else:
            completed = 0
        project_stats.append({"project": project, "total": total, "completed": completed})

    return templates.TemplateResponse(
        request,
        "projects/list.html",
        {"project_stats": project_stats, "username": username, "is_admin": is_admin == "1"},
    )


@router.get("/projects/create", response_class=HTMLResponse)
async def create_project_form(
    request: Request,
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username:
        return RedirectResponse(url="/login", status_code=302)
    if is_admin != "1":
        return RedirectResponse(url="/projects", status_code=302)
    return templates.TemplateResponse(request, "projects/create.html")


@router.post("/projects")
async def create_project(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    is_admin = request.session.get("is_admin", "0")
    if is_admin != "1":
        return RedirectResponse(url="/projects", status_code=302)
    form = await request.form()
    name = form.get("name", "").strip()
    if not name:
        return RedirectResponse(url="/projects/create", status_code=302)
    project = Project(name=name)
    db.add(project)
    await db.commit()
    return RedirectResponse(url="/projects", status_code=302)


@router.post("/projects/{project_id}/delete")
async def delete_project(
    project_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username or is_admin != "1":
        return RedirectResponse(url="/projects", status_code=302)

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        return RedirectResponse(url="/projects", status_code=302)

    await db.delete(project)
    await db.commit()
    return RedirectResponse(url="/projects", status_code=302)
