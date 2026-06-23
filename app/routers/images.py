from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Annotation, Image, Project

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "uploads"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}


@router.get("/projects/{project_id}/images", response_class=HTMLResponse)
async def list_images(
    request: Request,
    project_id: int,
    sort_by: str = "imported_at",
    order: str = "desc",
    filter_text: str = "",
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(Project).where(Project.id == project_id).options(selectinload(Project.images))
    )
    project = result.scalar_one_or_none()
    if not project:
        return RedirectResponse(url="/projects", status_code=302)

    # Get images with their annotations
    query = select(Image).where(Image.project_id == project_id).options(selectinload(Image.annotations))

    if filter_text:
        query = query.where(Image.filename.ilike(f"%{filter_text}%"))

    # Sorting
    sort_column = getattr(Image, sort_by, Image.imported_at)
    if order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    result = await db.execute(query)
    images = result.scalars().all()

    # Build per-image annotation info for the template
    image_data = []
    for image in images:
        user_annotation = None
        for ann in image.annotations:
            if ann.annotated_by == username:
                user_annotation = ann
                break
        image_data.append({
            "image": image,
            "user_annotation": user_annotation,
            "all_annotations": image.annotations if is_admin == "1" else [],
        })

    return templates.TemplateResponse(
        request,
        "images/table.html",
        {
            "project": project,
            "image_data": image_data,
            "sort_by": sort_by,
            "order": order,
            "filter_text": filter_text,
            "username": username,
            "is_admin": is_admin == "1",
        },
    )


@router.post("/projects/{project_id}/images/import")
async def import_images(
    project_id: int,
    files: list[UploadFile],
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username or is_admin != "1":
        return RedirectResponse(url=f"/projects/{project_id}/images", status_code=302)

    # Verify project exists
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        return RedirectResponse(url="/projects", status_code=302)

    # Create upload directory for this project
    project_upload_dir = UPLOADS_DIR / str(project_id)
    project_upload_dir.mkdir(parents=True, exist_ok=True)

    # Get already-imported filenames to avoid duplicates
    result = await db.execute(select(Image.filename).where(Image.project_id == project_id))
    existing_filenames = {row[0] for row in result.all()}

    for file in files:
        if not file.filename:
            continue
        
        # Use only the basename to prevent path traversal
        filename = Path(file.filename).name
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        if filename in existing_filenames:
            continue

        # Save file to uploads
        dest = project_upload_dir / filename
        contents = await file.read()
        dest.write_bytes(contents)

        # Create DB record
        image = Image(project_id=project_id, filename=filename)
        db.add(image)
        existing_filenames.add(file.filename)

    await db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/images", status_code=302)


@router.post("/images/{image_id}/delete")
async def delete_image(
    image_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username or is_admin != "1":
        return RedirectResponse(url="/projects", status_code=302)

    result = await db.execute(
        select(Image).where(Image.id == image_id).options(selectinload(Image.project))
    )
    image = result.scalar_one_or_none()
    if not image:
        return RedirectResponse(url="/projects", status_code=302)

    project_id = image.project_id

    # Delete the file from disk
    file_path = UPLOADS_DIR / str(project_id) / image.filename
    if file_path.exists():
        file_path.unlink()

    # Delete from DB (cascades to annotations)
    await db.delete(image)
    await db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/images", status_code=302)
