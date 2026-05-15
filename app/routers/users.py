import hashlib
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "users/login.html", {"error": None})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username or is_admin != "1":
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "users/register.html", {"error": None})


@router.post("/register")
async def register(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username or is_admin != "1":
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    new_username = form.get("username", "").strip()
    new_password = form.get("password", "").strip()
    new_is_admin = form.get("is_admin") == "on"

    if not new_username or not new_password:
        return templates.TemplateResponse(
            request,
            "users/register.html",
            {"error": "Username and password are required."},
        )

    result = await db.execute(select(User).where(User.username == new_username))
    if result.scalar_one_or_none():
        return templates.TemplateResponse(
            request,
            "users/register.html",
            {"error": "That username is already taken."},
        )

    user = User(
        username=new_username,
        password_hash=hash_password(new_password),
        is_admin=new_is_admin,
    )
    db.add(user)
    await db.commit()

    return RedirectResponse(url="/user", status_code=302)


@router.post("/login/user")
async def login_user(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    username = form.get("username", "").strip()
    password = form.get("password", "").strip()

    if not username or not password:
        return templates.TemplateResponse(
            request,
            "users/login.html",
            {"error": "Username and password are required for user login."},
        )

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "users/login.html",
            {"error": "Invalid username or password."},
        )

    request.session["username"] = username
    request.session["is_admin"] = "1" if user.is_admin else "0"
    return RedirectResponse(url="/projects", status_code=302)


@router.post("/login/admin")
async def login_admin(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    username = form.get("username", "").strip()
    admin_password = form.get("admin_password", "").strip()

    if not username or not admin_password:
        return templates.TemplateResponse(
            request,
            "users/login.html",
            {"error": "Username and admin password are required for admin login."},
        )

    if admin_password != ADMIN_PASSWORD:
        return templates.TemplateResponse(
            request,
            "users/login.html",
            {"error": "Invalid admin password."},
        )

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        user = User(username=username, password_hash="", is_admin=True)
        db.add(user)
    else:
        user.is_admin = True
    await db.commit()

    request.session["username"] = username
    request.session["is_admin"] = "1"
    return RedirectResponse(url="/projects", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@router.get("/user", response_class=HTMLResponse)
async def user_settings(
    request: Request,
    message: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username:
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(
        select(User).where(User.username != username).order_by(User.username)
    )
    users = result.scalars().all()

    return templates.TemplateResponse(
        request,
        "users/settings.html",
        {
            "username": username,
            "is_admin": is_admin == "1",
            "users": users,
            "message": message,
            "error": error,
        },
    )


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username or is_admin != "1":
        return RedirectResponse(url="/login", status_code=302)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.username == username:
        return RedirectResponse(url="/user", status_code=302)

    await db.delete(user)
    await db.commit()

    return RedirectResponse(url="/user?message=User+deleted+successfully", status_code=302)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    username = request.session.get("username", "")
    is_admin = request.session.get("is_admin", "0")
    if not username or is_admin != "1":
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    new_password = form.get("new_password", "").strip()
    if not new_password:
        result = await db.execute(select(User).order_by(User.username))
        users = result.scalars().all()
        return templates.TemplateResponse(
            request,
            "users/settings.html",
            {
                "username": username,
                "is_admin": True,
                "users": users,
                "error": "New password is required.",
            },
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return RedirectResponse(url="/user", status_code=302)

    user.password_hash = hash_password(new_password)
    await db.commit()

    return RedirectResponse(url="/user?message=Password+reset+successfully", status_code=302)
