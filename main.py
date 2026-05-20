from contextlib import asynccontextmanager
import os

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.database import init_db
from app.routers import annotations, export, images, projects, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Annotation Tool", lifespan=lifespan)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    with open("error.log", "a") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"ERROR: {str(exc)}\n")
        f.write(traceback.format_exc())
        f.write(f"{'='*50}\n")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)}
    )

secret_key = os.environ.get("SESSION_SECRET")
if not secret_key:
    print("WARNING: SESSION_SECRET is not set. Using a development secret key.")
    secret_key = "dev-secret"
app.add_middleware(SessionMiddleware, secret_key=secret_key)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(projects.router)
app.include_router(images.router)
app.include_router(annotations.router)
app.include_router(users.router)
app.include_router(export.router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

