# Annotation Tool

A browser-based image annotation tool built with FastAPI, SQLAlchemy, and HTMX. Users annotate images with social identity, view point, and narrative role labels. Admins can export annotations as JSON.

## Features

- **Projects** — Organize images into named projects
- **Image import** — Upload images (jpg, png, gif, webp, bmp, tiff) into a project
- **Annotation** — Label each image with:
  - Social identity (selection or free text)
  - View point (binary selection)
  - Narrative roles (multi-select: hero, sage, charmer, winner, villain, fool, monster, loser, victim)
- **Multi-user** — Each user annotates independently; one annotation per user per image
- **Export** — Admins export annotations as JSON
- **Simple auth** — Cookie-based login by username; admin access via password

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (Python package/project manager)

## Installing uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via Homebrew
brew install uv
```

## Installation

```bash
git clone <repo-url>
cd annotation_tool
uv sync
```

## Running

```bash
uv run main.py
```

The app starts at [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ADMIN_PASSWORD` | `admin123` | Password required to log in as admin |

Set environment variables before running:

```bash
ADMIN_PASSWORD=secret uv run main.py
```

## Usage

1. **Log in** — Enter a username (provide the admin password for admin access)
2. **Create a project** — Give it a name
3. **Import images** — Upload files into the project
4. **Annotate** — Open an image and fill in the labels
5. **Export (admin)** — Select images and download annotations as JSON

## Project Structure

```
main.py              # App entrypoint (uvicorn)
app/
  database.py        # Async SQLite setup (SQLAlchemy + aiosqlite)
  models.py          # ORM models (Project, Image, Annotation, User)
  routers/           # FastAPI route handlers
  templates/         # Jinja2 HTML templates (Pico CSS + HTMX)
static/
  css/style.css      # Custom styles
  uploads/           # Uploaded images (per project)
data/
  exports/           # Exported JSON files
  annotation_tool.db # SQLite database (created on first run)
```
