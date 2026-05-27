import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Annotation, Image, Project

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

EXPORT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "exports"


def safe_filename(name: str) -> str:
    return "_".join(
        part for part in "".join(c if c.isalnum() or c in " _-" else " " for c in name).split()
    ).strip("_-")


@router.get("/projects/{project_id}/export", response_class=HTMLResponse)
async def export_form(
    request: Request,
    project_id: int,
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

    # Fetch all images for this project
    result = await db.execute(
        select(Image)
        .where(Image.project_id == project_id)
        .options(selectinload(Image.annotations))
        .order_by(Image.imported_at.desc())
    )
    images = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "export/select.html",
        {"project": project, "images": images, "username": username, "is_admin": True},
    )


@router.post("/projects/{project_id}/export")
async def export_project(
    request: Request,
    project_id: int,
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

    form = await request.form()
    selected_image_ids = form.getlist("image_ids")

    # Fetch selected images with annotations
    if selected_image_ids:
        result = await db.execute(
            select(Image)
            .where(Image.id.in_(selected_image_ids), Image.project_id == project_id)
            .options(selectinload(Image.annotations))
        )
    else:
        # If nothing selected, export nothing
        result = await db.execute(
            select(Image)
            .where(Image.project_id == project_id)
            .options(selectinload(Image.annotations))
        )

    images = result.scalars().all()

    export_data = []
    for image in images:
        for annotation in image.annotations:
            try:
                narrative_roles_list = json.loads(annotation.narrative_roles)
            except (json.JSONDecodeError, TypeError):
                narrative_roles_list = []

            entry = {
                "id": image.id,
                "image_filename": image.filename,
                "comments": {
                    "social_identity": annotation.social_identity_comments,
                    "view_point": annotation.view_point_comments,
                    "narrative_roles": annotation.narrative_roles_comments
                },
                "unclear_case": bool(annotation.unclear_case),
                "annotator_name": annotation.annotated_by,
                "labels": {
                    "social_identity": annotation.social_identity,
                    "view_point": annotation.view_point,
                    "narrative_roles": narrative_roles_list,
                },
                "date_time": annotation.completed_at.isoformat(),
            }
            export_data.append(entry)

    # Save to file
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(project.name) or f"project_{project_id}"
    export_path = EXPORT_DIR / f"{filename}.json"
    export_path.write_text(json.dumps(export_data, indent=4, ensure_ascii=False))

    # Return as downloadable JSON
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.json"'
        },
    )
