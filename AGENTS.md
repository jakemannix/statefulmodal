# Agent Instructions for StatefulModal

This document provides guidance for AI coding agents working on this codebase.

## Project Overview

StatefulModal is a pedagogical template demonstrating how to build modern, stateful web applications using:

- **Modal.com** - Serverless cloud platform for Python
- **FastHTML** - Python web framework with HTMX integration
- **SQLite** - Lightweight relational database with Modal Volume persistence
- **Google OAuth** - Secure authentication

## Architecture

The main application code lives in `statefulmodal/app.py`, organized into clearly-marked sections:

1. **Modal App Configuration** (lines ~54-115) - Container image, volumes, secrets
2. **Database Layer** (lines ~117-418) - SQLite abstraction with `User` dataclass and `Database` class
3. **FastHTML Web Application** (lines ~420-1114) - Routes, components, OAuth handling
4. **Modal Function Definition** (lines ~1117-1171) - ASGI app deployment
5. **CLI Utilities** (lines ~1174-1240) - Admin commands like `init_admin`, `list_users`, `make_admin`

## Development Setup

```bash
# Install dependencies with uv
uv sync

# Or with pip
pip install -e .

# Create Modal volume (first time only)
modal volume create statefulmodal-data

# Set up secrets in .env for local dev
cp .env.example .env  # if it exists, otherwise create manually
# Add: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

# Development server (hot reload)
modal serve statefulmodal/app.py

# Production deployment
modal deploy statefulmodal/app.py
```

## Environment Variables

For **local development**, copy the example file and fill in your values:
```bash
cp .env.example .env
# Edit .env with your credentials
```

The `.env` file is gitignored and should contain:
- `GOOGLE_CLIENT_ID` - From Google Cloud Console
- `GOOGLE_CLIENT_SECRET` - From Google Cloud Console
- `SESSION_SECRET` - Random key for cookie encryption
- `INITIAL_ADMIN_EMAIL` - (Optional) Auto-added to allowed list on startup

See `.env.example` for detailed instructions on obtaining each value.

For **production**, use Modal Secrets:
```bash
modal secret create google-oauth \
    GOOGLE_CLIENT_ID="..." \
    GOOGLE_CLIENT_SECRET="..."
```

## Key Patterns

### Database Operations
```python
# Always use the context manager for connections
with self._get_connection() as conn:
    result = conn.execute("SELECT ...", (params,)).fetchone()
    # volume.commit() is called automatically
```

### Adding Routes
```python
@rt("/new-route")
def new_route(session):
    redirect = require_auth(session)  # Optional auth check
    if redirect:
        return redirect
    user = get_current_user(session)
    return page_layout("Title", content, user=user)
```

### HTMX Interactions
- Use `hx_post`, `hx_delete`, `hx_get` for AJAX requests
- Use `hx_target` and `hx_swap` to specify where responses go
- Return HTML fragments for partial updates

## Modal CLI Commands

```bash
# Add email to allowed list
modal run statefulmodal/app.py::init_admin --email=user@example.com

# List all users and allowed emails
modal run statefulmodal/app.py::list_users

# Grant admin privileges
modal run statefulmodal/app.py::make_admin --email=user@example.com
```

## Testing Locally

The app requires Modal to run, but you can test components:

```bash
# Serve with hot reload
modal serve statefulmodal/app.py

# Access at the URL printed by Modal (e.g., https://yourname--statefulmodal-web-dev.modal.run)
```

## Common Tasks

### Adding a New Database Table
1. Add schema in `Database._init_db()`
2. Add corresponding methods to `Database` class
3. Create routes in `create_app()` function

### Adding a New Protected Route
1. Define route with `@rt("/path")`
2. Call `require_auth(session)` at the start
3. Use `get_current_user(session)` to get user info
4. Return content wrapped in `page_layout()`

### Adding Admin-Only Features
1. Call both `require_auth(session)` and `require_admin(session)`
2. Add UI elements in the `/admin` route

## File Structure

```
statefulmodal/
├── statefulmodal/      # Python package
│   ├── __init__.py     # Package exports (app, create_app, Database, User)
│   └── app.py          # Main application code
├── pyproject.toml      # Project configuration and dependencies
├── README.md           # User-facing documentation
├── AGENTS.md           # This file (agent instructions)
├── CLAUDE.md           # Symlink to AGENTS.md
├── LICENSE             # Apache 2.0
└── .gitignore          # Git ignore rules
```

## Notes for Agents

- The main application code is in `statefulmodal/app.py` for pedagogical clarity
- When making changes, preserve the section organization and comments
- Environment variables are loaded from `.env` via `python-dotenv` at module load time
- Modal functions (`init_admin`, `list_users`, etc.) will have access to `.env` vars
- SQLite database lives on a Modal Volume at `/data/app.db`
- You can import from the package: `from statefulmodal import app, Database, User`
