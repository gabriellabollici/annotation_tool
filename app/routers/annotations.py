import json
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Annotation, Image

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

NARRATIVE_ROLES_OPTIONS = {
    "positive_superior": ["hero", "sage", "charmer", "winner"],
    "negative_inferior": ["villain", "fool", "monster", "loser"],
    "positive_inferior": ["victim"],
}


@router.get("/projects/{project_id}/images/annotate-all", response_class=HTMLResponse)
async def annotate_all(
    request: Request,
    project_id: int,
    index: int = 0,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin_session = request.session.get("is_admin", "0")
    if not username:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(Image)
        .where(Image.project_id == project_id)
        .options(selectinload(Image.annotations), selectinload(Image.project))
        .order_by(Image.imported_at.asc())
    )
    images = result.scalars().all()
    if not images:
        return RedirectResponse(url=f"/projects/{project_id}/images", status_code=302)

    if index < 0:
        index = 0
    if index >= len(images):
        index = len(images) - 1

    image = images[index]

    user_annotations = [ann for ann in image.annotations if ann.annotated_by == username]
    for ann in user_annotations:
        try:
            ann.parsed_roles = json.loads(ann.narrative_roles)
        except (json.JSONDecodeError, TypeError):
            ann.parsed_roles = []

    return templates.TemplateResponse(
        request,
        "annotations/label.html",
        {
            "image": image,
            "project": image.project,
            "user_annotations": user_annotations,
            "narrative_roles_options": NARRATIVE_ROLES_OPTIONS,
            "username": username,
            "is_admin": is_admin_session == "1",
            "annotate_all_mode": True,
            "current_index": index,
            "total_images": len(images),
            "prev_index": index - 1 if index > 0 else None,
            "next_index": index + 1 if index < len(images) - 1 else None,
        },
    )


@router.get("/images/{image_id}/annotate", response_class=HTMLResponse)
async def annotate_form(
    request: Request,
    image_id: str,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin_session = request.session.get("is_admin", "0")
    if not username:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(Image).where(Image.id == image_id).options(selectinload(Image.annotations), selectinload(Image.project))
    )
    image = result.scalar_one_or_none()
    if not image:
        return RedirectResponse(url="/projects", status_code=302)

    # Load ALL existing annotations for THIS user
    user_annotations = [ann for ann in image.annotations if ann.annotated_by == username]
    
    # Parse narrative roles for each annotation
    for ann in user_annotations:
        try:
            ann.parsed_roles = json.loads(ann.narrative_roles)
        except (json.JSONDecodeError, TypeError):
            ann.parsed_roles = []

    return templates.TemplateResponse(
        request,
        "annotations/label.html",
        {
            "image": image,
            "project": image.project,
            "user_annotations": user_annotations,
            "narrative_roles_options": NARRATIVE_ROLES_OPTIONS,
            "username": username,
            "is_admin": is_admin_session == "1",
        },
    )


@router.post("/images/{image_id}/num-identities")
async def update_num_identities(
    request: Request,
    image_id: str,
    db: AsyncSession = Depends(get_db),
):
    is_admin = request.session.get("is_admin", "0")
    if is_admin != "1":
        return HTMLResponse(content="Unauthorized", status_code=403)
    
    form = await request.form()
    num = form.get("num_identities", "0")
    try:
        num = int(num)
    except ValueError:
        num = 0
    
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if image:
        image.num_identities = num
        await db.commit()
    
    return HTMLResponse(content=str(num))


@router.post("/images/{image_id}/annotate")
async def save_annotation(
    request: Request,
    image_id: str,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    if not username:
        return RedirectResponse(url="/login", status_code=302)

    image = None
    try:
        form = await request.form()
        
        # Get image
        result = await db.execute(
            select(Image).where(Image.id == image_id).options(selectinload(Image.annotations))
        )
        image = result.scalar_one_or_none()
        if not image:
            return RedirectResponse(url="/projects", status_code=302)

        # Get all user's existing annotations for this image
        user_annotations = [ann for ann in image.annotations if ann.annotated_by == username]
        
        # Delete existing annotations first
        for ann in user_annotations:
            await db.delete(ann)
        
        # Parse form data: social_identity_N[], view_point_N, narrative_roles_N[], other_label_N
        # Determine annotation count from ANY field that is part of an annotation set
        annotation_indices = set()
        for key in form.keys():
            if any(key.startswith(prefix) for prefix in ["view_point_", "social_identity_", "narrative_roles_", "other_label_", "unclear_case_", "si_comments_", "vp_comments_", "nr_comments_"]):
                try:
                    index = key.split("_")[-1]
                    if index.isdigit():
                        annotation_indices.add(int(index))
                except (ValueError, IndexError):
                    continue
        
        general_comments = form.get("general_comments", "").strip()
        annotation_count = max(annotation_indices) + 1 if annotation_indices else 1
        
        # Create new annotations from form data
        for i in range(annotation_count):
            if i not in annotation_indices and annotation_count > 1:
                continue

            # Get all selected social identity checkboxes for this annotation
            social_identity_key = f"social_identity_{i}"
            selected_identities = form.getlist(social_identity_key)
            
            # Get the "other label" field for this annotation
            other_label = form.get(f"other_label_{i}", "").strip()
            
            # Combine selected identities with other label
            all_identities = selected_identities + ([other_label] if other_label else [])
            social_identity = ", ".join(all_identities) if all_identities else ""
            
            # New specific comments
            si_comment = form.get(f"si_comments_{i}", "").strip()
            vp_comment = form.get(f"vp_comments_{i}", "").strip()
            nr_comment = form.get(f"nr_comments_{i}", "").strip()
            
            # Each viewpoint has indexed name: view_point_0, view_point_1, etc.
            view_point = form.get(f"view_point_{i}", "")
            
            # Get narrative roles for this annotation
            narrative_roles_key = f"narrative_roles_{i}"
            narrative_roles = form.getlist(narrative_roles_key)
            
            # Flag unclear case if selected
            unclear_case = form.get(f"unclear_case_{i}") in ("on", "1", "true", "True")

            # Create annotation
            annotation = Annotation(
                image_id=image_id,
                social_identity=social_identity,
                social_identity_comments=si_comment,
                view_point=view_point,
                view_point_comments=vp_comment,
                narrative_roles=json.dumps(narrative_roles),
                narrative_roles_comments=nr_comment,
                comments=general_comments,
                unclear_case=unclear_case,
                completed_at=datetime.utcnow(),
                annotated_by=username,
            )
            db.add(annotation)
        
        annotate_all = form.get("annotate_all") == "1"
        if annotate_all:
            project_id = form.get("project_id") or image.project_id
            try:
                current_index = int(form.get("current_index", 0))
            except ValueError:
                current_index = 0
            redirect_url = f"/projects/{project_id}/images/annotate-all?index={current_index}"
        else:
            redirect_url = f"/projects/{image.project_id}/images"

        await db.commit()
        return RedirectResponse(url=redirect_url, status_code=302)
    except Exception as e:
        await db.rollback()
        print(f"Error saving annotation: {str(e)}")
        import traceback
        traceback.print_exc()
        if image:
            return RedirectResponse(url=f"/projects/{image.project_id}/images", status_code=302)
        else:
            return RedirectResponse(url="/projects", status_code=302)


@router.post("/annotations/{annotation_id}/delete")
async def delete_annotation(
    annotation_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(Annotation).where(Annotation.id == annotation_id).options(selectinload(Annotation.image))
    )
    annotation = result.scalar_one_or_none()
    if not annotation:
        return RedirectResponse(url="/projects", status_code=302)

    # Only the annotation owner or admin can delete
    if annotation.annotated_by != username and is_admin != "1":
        return RedirectResponse(url="/projects", status_code=302)

    project_id = annotation.image.project_id
    await db.delete(annotation)
    await db.commit()
    return RedirectResponse(url=f"/projects/{project_id}/images", status_code=302)
