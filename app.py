"""
================================================================================
MODAL + FASTHTML + SQLITE TEMPLATE APPLICATION
================================================================================

This is a pedagogical template demonstrating how to build a modern, stateful
web application using:

    1. Modal.com     - Serverless cloud platform for Python
    2. FastHTML      - Python web framework with HTMX integration
    3. SQLite        - Lightweight relational database
    4. Modal Volumes - Persistent storage for database files
    5. Google OAuth  - Secure authentication without passwords
    6. Modal Secrets - Secure storage for API keys and credentials

HOW TO USE THIS TEMPLATE:
-------------------------
1. Create a Modal account at https://modal.com
2. Install Modal CLI: pip install modal
3. Authenticate: modal token new
4. Create required secrets (see SECRETS SETUP section below)
5. Create the volume: modal volume create statefulmodal-data
6. Deploy: modal deploy app.py

For local development:
    modal serve app.py

SECRETS SETUP:
--------------
Create a Modal secret named "google-oauth" with these keys:
    - GOOGLE_CLIENT_ID: Your Google OAuth client ID
    - GOOGLE_CLIENT_SECRET: Your Google OAuth client secret

To create the secret via CLI:
    modal secret create google-oauth \
        GOOGLE_CLIENT_ID=your-client-id-here \
        GOOGLE_CLIENT_SECRET=your-client-secret-here

To get Google OAuth credentials:
    1. Go to https://console.cloud.google.com/
    2. Create a new project (or select existing)
    3. Enable the Google+ API
    4. Go to Credentials > Create Credentials > OAuth client ID
    5. Application type: Web application
    6. Add authorized redirect URI: https://your-app--statefulmodal.modal.run/redirect
    7. Copy the Client ID and Client Secret

================================================================================
"""

import os

from dotenv import load_dotenv

# Load environment variables from .env file for local development
# and Modal CLI commands (modal run app.py::init_admin, etc.)
# In production Modal containers, secrets are injected directly.
load_dotenv()

import modal

# =============================================================================
# SECTION 1: MODAL APP CONFIGURATION
# =============================================================================
#
# Modal apps are the top-level container for all your serverless functions.
# Think of an "app" as a project that groups related functions together.
#
# Key concepts:
# - App: A collection of functions, volumes, and secrets
# - Image: The container environment your code runs in
# - Volume: Persistent storage that survives function restarts
# - Secret: Secure storage for API keys and credentials
# =============================================================================

# Create the Modal app - this is the entry point for everything
app = modal.App(
    name="statefulmodal",  # This name appears in the Modal dashboard
)

# -----------------------------------------------------------------------------
# CONTAINER IMAGE SETUP
# -----------------------------------------------------------------------------
# Modal runs your code in containers. We define what's installed in those
# containers using an Image. This is similar to a Dockerfile, but in Python.
#
# The image is built once and cached, so subsequent deploys are fast.
# -----------------------------------------------------------------------------

image = (
    modal.Image.debian_slim(python_version="3.12")
    # Install Python packages from PyPI
    .pip_install(
        "python-fasthtml>=0.12.0",  # Web framework
        "python-dotenv>=1.0.0",      # Environment variable management
    )
)

# -----------------------------------------------------------------------------
# PERSISTENT STORAGE WITH MODAL VOLUMES
# -----------------------------------------------------------------------------
# Modal Volumes provide persistent storage that survives container restarts.
# Unlike ephemeral container storage, data in volumes persists across:
# - Function invocations
# - Container restarts
# - Deployments
#
# IMPORTANT: You must create the volume before first use:
#     modal volume create statefulmodal-data
#
# The `create_if_missing=True` flag will auto-create it, but explicit
# creation is recommended for production.
# -----------------------------------------------------------------------------

volume = modal.Volume.from_name(
    "statefulmodal-data",
    create_if_missing=True  # Auto-create if it doesn't exist
)

# Define where the volume mounts in the container
VOLUME_PATH = "/data"
DATABASE_PATH = f"{VOLUME_PATH}/app.db"


# =============================================================================
# SECTION 2: DATABASE LAYER (SQLite)
# =============================================================================
#
# We use SQLite for simplicity and portability. The database file is stored
# on the Modal Volume, so it persists across container restarts.
#
# SQLite is perfect for:
# - Small to medium applications
# - Applications with mostly read operations
# - Prototyping and development
#
# For high-write-throughput applications, consider PostgreSQL or similar.
# =============================================================================

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class User:
    """
    Represents a user in our application.

    The dataclass decorator automatically generates __init__, __repr__, etc.
    This is a simple way to create structured data objects in Python.
    """
    id: Optional[int]
    email: str
    name: str
    is_admin: bool
    created_at: str
    last_login: Optional[str]

    def __ft__(self):
        """
        FastHTML magic method: defines how this object renders as HTML.

        When you return a User object from a route, FastHTML calls this
        method to convert it to HTML. This is a powerful pattern for
        creating reusable components.
        """
        from fasthtml.common import Div, Span, Small
        return Div(
            Span(self.name, cls="font-bold"),
            Small(f" ({self.email})", cls="text-muted"),
            cls="user-badge"
        )


class Database:
    """
    Database abstraction layer for SQLite operations.

    This class encapsulates all database operations, making it easy to:
    - Swap out the database implementation later
    - Test database operations in isolation
    - Manage connection lifecycles properly

    IMPORTANT FOR MODAL VOLUMES:
    After writing to the database, we call volume.commit() to ensure
    changes are persisted. Without this, changes might be lost if the
    container shuts down before the automatic commit happens.
    """

    def __init__(self, db_path: str, volume_ref=None):
        """
        Initialize the database connection.

        Args:
            db_path: Path to the SQLite database file
            volume_ref: Reference to Modal Volume for committing changes
        """
        self.db_path = db_path
        self.volume = volume_ref
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """
        Context manager for database connections.

        Using a context manager ensures connections are properly closed,
        even if an exception occurs. This prevents resource leaks.

        Example:
            with self._get_connection() as conn:
                conn.execute("SELECT * FROM users")
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
        try:
            yield conn
            conn.commit()
            # Commit changes to the Modal Volume
            if self.volume:
                self.volume.commit()
        finally:
            conn.close()

    def _init_db(self):
        """
        Initialize database schema.

        Creates tables if they don't exist. This is idempotent - safe to
        call multiple times without side effects.
        """
        with self._get_connection() as conn:
            # Users table - stores authorized users
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP
                )
            """)

            # Allowed emails table - whitelist for OAuth
            # Only users with emails in this table can access the app
            conn.execute("""
                CREATE TABLE IF NOT EXISTS allowed_emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    added_by TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Example data table - demonstrates app functionality
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)

    # -------------------------------------------------------------------------
    # USER MANAGEMENT METHODS
    # -------------------------------------------------------------------------

    def is_email_allowed(self, email: str) -> bool:
        """Check if an email is in the allowed list."""
        with self._get_connection() as conn:
            result = conn.execute(
                "SELECT 1 FROM allowed_emails WHERE LOWER(email) = LOWER(?)",
                (email,)
            ).fetchone()
            return result is not None

    def add_allowed_email(self, email: str, added_by: str = "system"):
        """Add an email to the allowed list."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO allowed_emails (email, added_by) VALUES (?, ?)",
                (email.lower(), added_by)
            )

    def remove_allowed_email(self, email: str):
        """Remove an email from the allowed list."""
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM allowed_emails WHERE LOWER(email) = LOWER(?)",
                (email,)
            )

    def get_allowed_emails(self) -> List[str]:
        """Get all allowed emails."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT email FROM allowed_emails").fetchall()
            return [row["email"] for row in rows]

    def get_or_create_user(self, email: str, name: str) -> Optional[User]:
        """
        Get existing user or create a new one.

        This is called during OAuth login. If the user exists, we update
        their last_login time. If not, we create a new user record.

        Returns None if the email is not in the allowed list.
        """
        if not self.is_email_allowed(email):
            return None

        with self._get_connection() as conn:
            # Try to get existing user
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
                (email,)
            ).fetchone()

            if row:
                # Update last login time
                conn.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?",
                    (row["id"],)
                )
                return User(
                    id=row["id"],
                    email=row["email"],
                    name=row["name"],
                    is_admin=bool(row["is_admin"]),
                    created_at=row["created_at"],
                    last_login=datetime.now().isoformat()
                )
            else:
                # Create new user
                cursor = conn.execute(
                    "INSERT INTO users (email, name) VALUES (?, ?)",
                    (email.lower(), name)
                )
                return User(
                    id=cursor.lastrowid,
                    email=email.lower(),
                    name=name,
                    is_admin=False,
                    created_at=datetime.now().isoformat(),
                    last_login=datetime.now().isoformat()
                )

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by their email address."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE LOWER(email) = LOWER(?)",
                (email,)
            ).fetchone()

            if row:
                return User(
                    id=row["id"],
                    email=row["email"],
                    name=row["name"],
                    is_admin=bool(row["is_admin"]),
                    created_at=row["created_at"],
                    last_login=row["last_login"]
                )
            return None

    def get_all_users(self) -> List[User]:
        """Get all users in the system."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
            return [
                User(
                    id=row["id"],
                    email=row["email"],
                    name=row["name"],
                    is_admin=bool(row["is_admin"]),
                    created_at=row["created_at"],
                    last_login=row["last_login"]
                )
                for row in rows
            ]

    def set_admin(self, email: str, is_admin: bool):
        """Set or remove admin privileges for a user."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET is_admin = ? WHERE LOWER(email) = LOWER(?)",
                (is_admin, email)
            )

    # -------------------------------------------------------------------------
    # NOTES METHODS (Example app functionality)
    # -------------------------------------------------------------------------

    def add_note(self, user_id: int, content: str) -> int:
        """Add a new note for a user."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO notes (user_id, content) VALUES (?, ?)",
                (user_id, content)
            )
            return cursor.lastrowid

    def get_notes(self, user_id: int) -> List[dict]:
        """Get all notes for a user."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM notes WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_note(self, note_id: int, user_id: int) -> bool:
        """Delete a note (only if it belongs to the user)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM notes WHERE id = ? AND user_id = ?",
                (note_id, user_id)
            )
            return cursor.rowcount > 0


# =============================================================================
# SECTION 3: FASTHTML WEB APPLICATION
# =============================================================================
#
# FastHTML is a modern Python web framework that embraces:
# - Server-side rendering with Python
# - HTMX for dynamic updates without JavaScript
# - HTML-as-Python for type-safe templates
#
# Key concepts:
# - Routes: URL patterns that map to Python functions
# - Components: Reusable HTML elements as Python functions
# - HTMX: Update parts of the page without full reloads
# =============================================================================

def create_app():
    """
    Factory function to create the FastHTML application.

    We use a factory pattern because:
    1. It allows proper initialization within Modal's container
    2. The database connection is created when the container starts
    3. Secrets are only available inside Modal functions

    This function is called by Modal when the container starts.
    """
    from fasthtml.common import (
        fast_app, Html, Head, Body, Title, Meta, Link, Script,
        Div, H1, H2, H3, P, A, Button, Form, Input, Label,
        Nav, Main, Header, Footer, Section, Article,
        Ul, Li, Span, Small, Strong, Textarea,
        RedirectResponse
    )
    from fasthtml.oauth import GoogleAppClient, OAuth

    # -------------------------------------------------------------------------
    # INITIALIZE DATABASE
    # -------------------------------------------------------------------------
    # The database is initialized when the container starts.
    # The volume reference allows us to commit changes to persistent storage.
    # -------------------------------------------------------------------------

    db = Database(DATABASE_PATH, volume)

    # -------------------------------------------------------------------------
    # SEED INITIAL ADMIN USER
    # -------------------------------------------------------------------------
    # For first-time setup, we add a default admin email.
    # In production, you'd want to set this via environment variable.
    # -------------------------------------------------------------------------

    initial_admin = os.environ.get("INITIAL_ADMIN_EMAIL")
    if initial_admin:
        db.add_allowed_email(initial_admin, added_by="system")

    # -------------------------------------------------------------------------
    # OAUTH CONFIGURATION
    # -------------------------------------------------------------------------
    # Google OAuth allows users to log in with their Google accounts.
    # Credentials are stored in Modal Secrets for security.
    #
    # The OAuth flow:
    # 1. User clicks "Login with Google"
    # 2. User is redirected to Google's login page
    # 3. After login, Google redirects back to /redirect with a code
    # 4. We exchange the code for user info
    # 5. If the user's email is allowed, they're logged in
    # -------------------------------------------------------------------------

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    if client_id and client_secret:
        oauth_client = GoogleAppClient(client_id, client_secret)
    else:
        oauth_client = None
        print("WARNING: Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")

    # -------------------------------------------------------------------------
    # FASTHTML APP SETUP
    # -------------------------------------------------------------------------
    # fast_app() creates a FastHTML application with sensible defaults.
    #
    # Parameters:
    # - hdrs: Additional <head> elements (CSS, JS, meta tags)
    # - pico: Use PicoCSS for minimal styling (True by default)
    # - secret_key: Required for secure session cookies
    # -------------------------------------------------------------------------

    # Custom CSS for our application
    custom_css = """
    :root {
        --pico-font-size: 100%;
        --pico-border-radius: 0.5rem;
    }
    .container { max-width: 800px; margin: 0 auto; padding: 1rem; }
    .note-card {
        background: var(--pico-card-background-color);
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: var(--pico-border-radius);
        border-left: 4px solid var(--pico-primary);
    }
    .user-badge { display: inline-block; padding: 0.25rem 0.5rem; }
    .flash-message {
        padding: 1rem;
        margin: 1rem 0;
        border-radius: var(--pico-border-radius);
        background: var(--pico-primary-background);
    }
    .admin-section {
        border: 2px dashed var(--pico-muted-border-color);
        padding: 1rem;
        margin: 1rem 0;
    }
    .text-muted { color: var(--pico-muted-color); }
    .text-center { text-align: center; }
    .mb-1 { margin-bottom: 1rem; }
    .mt-1 { margin-top: 1rem; }
    """

    hdrs = (
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css"),
        Script(src="https://unpkg.com/htmx.org@1.9.10"),
    )

    # Create the FastHTML app
    # The 'rt' object is a route decorator we'll use to define URL handlers
    fasthtml_app, rt = fast_app(
        hdrs=hdrs,
        pico=False,  # We're loading PicoCSS ourselves
        secret_key=os.environ.get("SESSION_SECRET", "dev-secret-change-in-production"),
    )

    # -------------------------------------------------------------------------
    # CUSTOM OAUTH HANDLER
    # -------------------------------------------------------------------------
    # We extend FastHTML's OAuth class to implement our access control logic.
    # The get_auth method is called after successful Google login.
    # -------------------------------------------------------------------------

    class AppAuth(OAuth):
        """
        Custom OAuth handler with email whitelist verification.

        This class controls who can access the application:
        1. User logs in with Google
        2. We check if their email is in our allowed_emails table
        3. If allowed, we create/update their user record
        4. If not allowed, we show an error page
        """

        def get_auth(self, info, ident, session, state):
            """
            Called after successful OAuth authentication.

            Args:
                info: User info from Google (email, name, picture, etc.)
                ident: Unique identifier from the OAuth provider
                session: Session object for storing user data
                state: State parameter for CSRF protection

            Returns:
                RedirectResponse to appropriate page
            """
            email = info.email or ""
            name = info.name or email.split("@")[0]

            # Verify email is confirmed by Google
            if not getattr(info, 'email_verified', False):
                return RedirectResponse("/error?msg=Email+not+verified", status_code=303)

            # Check if user is allowed and create/update their record
            user = db.get_or_create_user(email, name)

            if user:
                # Store user info in session
                session["user_email"] = user.email
                session["user_name"] = user.name
                session["user_id"] = user.id
                session["is_admin"] = user.is_admin
                return RedirectResponse("/", status_code=303)
            else:
                return RedirectResponse(
                    f"/error?msg=Access+denied.+Email+{email}+is+not+authorized.",
                    status_code=303
                )

    # Initialize OAuth if credentials are available
    if oauth_client:
        oauth = AppAuth(fasthtml_app, oauth_client)
    else:
        oauth = None

    # -------------------------------------------------------------------------
    # HELPER FUNCTIONS
    # -------------------------------------------------------------------------

    def get_current_user(session) -> Optional[User]:
        """Get the currently logged-in user from session."""
        email = session.get("user_email")
        if email:
            return db.get_user_by_email(email)
        return None

    def require_auth(session):
        """Check if user is authenticated, redirect to login if not."""
        if not session.get("user_email"):
            return RedirectResponse("/login", status_code=303)
        return None

    def require_admin(session):
        """Check if user is admin, redirect with error if not."""
        if not session.get("is_admin"):
            return RedirectResponse("/error?msg=Admin+access+required", status_code=303)
        return None

    def page_layout(title: str, *content, user=None):
        """
        Base layout template for all pages.

        This is a reusable component that wraps page content with
        consistent header, navigation, and footer.

        FastHTML uses Python functions as components - just return
        HTML elements and they'll be rendered properly.
        """
        nav_items = [Li(A("Home", href="/"))]

        if user:
            nav_items.extend([
                Li(A("My Notes", href="/notes")),
                Li(Span(f"👤 {user.name}", cls="text-muted")),
            ])
            if user.is_admin:
                nav_items.append(Li(A("Admin", href="/admin")))
            nav_items.append(Li(A("Logout", href="/logout")))
        else:
            nav_items.append(Li(A("Login", href="/login")))

        return Html(
            Head(
                Title(f"{title} - StatefulModal"),
                *hdrs,
                Script(custom_css, type="text/css"),
                # Inline the CSS properly
                Link(rel="stylesheet", href="data:text/css," + custom_css.replace(" ", "%20").replace("\n", "%0A")),
            ),
            Body(
                Header(
                    Nav(
                        Ul(Li(Strong(A("StatefulModal", href="/")))),
                        Ul(*nav_items),
                        cls="container"
                    )
                ),
                Main(
                    Div(*content, cls="container"),
                    cls="container"
                ),
                Footer(
                    Div(
                        P(
                            "Built with ",
                            A("Modal", href="https://modal.com"), ", ",
                            A("FastHTML", href="https://fastht.ml"), ", and ",
                            A("SQLite", href="https://sqlite.org"),
                            cls="text-center text-muted"
                        ),
                        cls="container"
                    )
                ),
                style="min-height: 100vh; display: flex; flex-direction: column;"
            )
        )

    # -------------------------------------------------------------------------
    # ROUTE DEFINITIONS
    # -------------------------------------------------------------------------
    # Routes map URL patterns to Python functions.
    # The @rt decorator registers a route with the FastHTML app.
    #
    # FastHTML automatically:
    # - Parses request parameters
    # - Converts return values to HTTP responses
    # - Handles content negotiation
    # -------------------------------------------------------------------------

    @rt("/")
    def home(session):
        """
        Home page - shows different content based on login status.

        The 'session' parameter is automatically injected by FastHTML.
        It contains data stored in the user's encrypted session cookie.
        """
        user = get_current_user(session)

        if user:
            # Logged-in user sees their dashboard
            notes = db.get_notes(user.id)
            recent_notes = notes[:3]  # Show last 3 notes

            content = [
                H1(f"Welcome back, {user.name}!"),
                P("You're logged in and ready to use the app."),

                Section(
                    H2("Quick Stats"),
                    Ul(
                        Li(f"📝 You have {len(notes)} notes"),
                        Li(f"📧 Logged in as {user.email}"),
                        Li(f"🔐 Admin: {'Yes' if user.is_admin else 'No'}"),
                    ),
                    cls="mb-1"
                ),

                Section(
                    H2("Recent Notes"),
                    Div(
                        *[
                            Div(
                                P(note["content"]),
                                Small(note["created_at"], cls="text-muted"),
                                cls="note-card"
                            )
                            for note in recent_notes
                        ] if recent_notes else [P("No notes yet. ", A("Create one!", href="/notes"))],
                    ),
                    A("View all notes →", href="/notes", role="button"),
                    cls="mb-1"
                ),
            ]
        else:
            # Anonymous user sees landing page
            content = [
                H1("Welcome to StatefulModal"),
                P("A template application demonstrating Modal + FastHTML + SQLite"),

                Section(
                    H2("Features"),
                    Ul(
                        Li("🚀 Serverless deployment with Modal"),
                        Li("🎨 Modern UI with FastHTML + HTMX"),
                        Li("💾 Persistent storage with SQLite + Modal Volumes"),
                        Li("🔐 Secure authentication with Google OAuth"),
                        Li("👥 User management with email whitelist"),
                    ),
                    cls="mb-1"
                ),

                Div(
                    A("Login with Google", href="/login", role="button"),
                    cls="text-center"
                ),
            ]

        return page_layout("Home", *content, user=user)

    @rt("/login")
    def login(req, session):
        """
        Login page - shows Google OAuth button.

        If OAuth is not configured, shows setup instructions.
        """
        user = get_current_user(session)
        if user:
            return RedirectResponse("/", status_code=303)

        if oauth:
            login_url = oauth.login_link(req)
            content = [
                H1("Login"),
                P("Sign in with your Google account to access the app."),
                Div(
                    A("🔐 Login with Google", href=login_url, role="button"),
                    cls="text-center mt-1"
                ),
                Small(
                    "Note: Only pre-approved email addresses can access this app.",
                    cls="text-muted"
                ),
            ]
        else:
            content = [
                H1("Login"),
                Div(
                    H3("⚠️ OAuth Not Configured"),
                    P("To enable login, set up Google OAuth credentials:"),
                    Ul(
                        Li("Create a Google Cloud project"),
                        Li("Enable the Google+ API"),
                        Li("Create OAuth credentials"),
                        Li("Add credentials to Modal secrets"),
                    ),
                    P(
                        "See the ",
                        A("README", href="https://github.com/your-repo"),
                        " for detailed instructions."
                    ),
                    cls="flash-message"
                ),
            ]

        return page_layout("Login", *content)

    @rt("/error")
    def error(msg: str = "An error occurred"):
        """
        Error page - displays error messages.

        The 'msg' parameter is automatically extracted from the query string.
        For example: /error?msg=Access+denied
        """
        content = [
            H1("Error"),
            Div(
                P(msg),
                A("← Back to Home", href="/"),
                cls="flash-message"
            ),
        ]
        return page_layout("Error", *content)

    # -------------------------------------------------------------------------
    # NOTES FEATURE (Protected Routes)
    # -------------------------------------------------------------------------
    # These routes demonstrate a simple CRUD feature with HTMX.
    # HTMX allows us to update parts of the page without full reloads.
    # -------------------------------------------------------------------------

    @rt("/notes")
    def notes_page(session):
        """
        Notes management page.

        Shows all user's notes with forms to add/delete.
        Uses HTMX for dynamic updates without page reloads.
        """
        redirect = require_auth(session)
        if redirect:
            return redirect

        user = get_current_user(session)
        user_notes = db.get_notes(user.id)

        content = [
            H1("My Notes"),

            # Add note form
            # hx-post: Send POST request to /notes/add
            # hx-target: Update the #notes-list element with response
            # hx-swap: Insert new content at the beginning
            Form(
                Textarea(
                    name="content",
                    placeholder="Write a new note...",
                    required=True,
                    rows=3,
                ),
                Button("Add Note", type="submit"),
                hx_post="/notes/add",
                hx_target="#notes-list",
                hx_swap="afterbegin",
                hx_on="htmx:afterRequest: this.reset()",  # Clear form after submit
            ),

            # Notes list - this is updated by HTMX
            Div(
                *[note_card(note, user.id) for note in user_notes],
                id="notes-list",
                cls="mt-1"
            ),
        ]

        return page_layout("My Notes", *content, user=user)

    def note_card(note: dict, user_id: int):
        """
        Component to render a single note.

        Includes a delete button that uses HTMX to remove the note
        without a full page reload.
        """
        return Div(
            P(note["content"]),
            Div(
                Small(note["created_at"], cls="text-muted"),
                Button(
                    "🗑️ Delete",
                    hx_delete=f"/notes/{note['id']}",
                    hx_target="closest .note-card",
                    hx_swap="outerHTML",
                    hx_confirm="Delete this note?",
                    cls="secondary outline",
                    style="padding: 0.25rem 0.5rem; font-size: 0.875rem;",
                ),
                style="display: flex; justify-content: space-between; align-items: center;",
            ),
            cls="note-card",
            id=f"note-{note['id']}"
        )

    @rt("/notes/add")
    def add_note(session, content: str):
        """
        Add a new note (POST handler).

        Returns just the HTML for the new note card, which HTMX
        inserts into the notes list.
        """
        redirect = require_auth(session)
        if redirect:
            return redirect

        user = get_current_user(session)
        note_id = db.add_note(user.id, content)

        # Return the new note card for HTMX to insert
        return note_card({
            "id": note_id,
            "content": content,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, user.id)

    @rt("/notes/{note_id}")
    def delete_note(session, note_id: int):
        """
        Delete a note (DELETE handler).

        Returns empty string, causing HTMX to remove the element.
        """
        redirect = require_auth(session)
        if redirect:
            return redirect

        user = get_current_user(session)
        db.delete_note(note_id, user.id)

        # Return empty - HTMX will remove the target element
        return ""

    # -------------------------------------------------------------------------
    # ADMIN SECTION
    # -------------------------------------------------------------------------
    # Admin routes for managing users and access control.
    # Only users with is_admin=True can access these.
    # -------------------------------------------------------------------------

    @rt("/admin")
    def admin_page(session):
        """Admin dashboard for user management."""
        redirect = require_auth(session)
        if redirect:
            return redirect
        redirect = require_admin(session)
        if redirect:
            return redirect

        user = get_current_user(session)
        all_users = db.get_all_users()
        allowed_emails = db.get_allowed_emails()

        content = [
            H1("Admin Dashboard"),

            # User management section
            Section(
                H2("Registered Users"),
                Div(
                    *[
                        Div(
                            Strong(u.name), f" ({u.email})",
                            Small(f" - Admin: {'Yes' if u.is_admin else 'No'}", cls="text-muted"),
                            Small(f" - Last login: {u.last_login or 'Never'}", cls="text-muted"),
                        )
                        for u in all_users
                    ] if all_users else [P("No users registered yet.")],
                ),
                cls="admin-section"
            ),

            # Email whitelist section
            Section(
                H2("Allowed Emails"),
                P("Only users with these emails can log in:"),

                # Add email form
                Form(
                    Input(
                        name="email",
                        type="email",
                        placeholder="email@example.com",
                        required=True,
                    ),
                    Button("Add Email", type="submit"),
                    hx_post="/admin/emails/add",
                    hx_target="#email-list",
                    hx_swap="beforeend",
                    style="display: flex; gap: 0.5rem;",
                ),

                # Email list
                Ul(
                    *[
                        Li(
                            email,
                            Button(
                                "×",
                                hx_delete=f"/admin/emails/{email}",
                                hx_target="closest li",
                                hx_swap="outerHTML",
                                hx_confirm=f"Remove {email} from allowed list?",
                                cls="secondary outline",
                                style="padding: 0 0.5rem; margin-left: 0.5rem;",
                            ),
                            id=f"email-{email.replace('@', '-at-').replace('.', '-dot-')}",
                        )
                        for email in allowed_emails
                    ],
                    id="email-list"
                ),
                cls="admin-section"
            ),
        ]

        return page_layout("Admin", *content, user=user)

    @rt("/admin/emails/add")
    def add_email(session, email: str):
        """Add an email to the allowed list."""
        redirect = require_auth(session)
        if redirect:
            return redirect
        redirect = require_admin(session)
        if redirect:
            return redirect

        user = get_current_user(session)
        db.add_allowed_email(email, added_by=user.email)

        email_id = email.replace('@', '-at-').replace('.', '-dot-')
        return Li(
            email,
            Button(
                "×",
                hx_delete=f"/admin/emails/{email}",
                hx_target="closest li",
                hx_swap="outerHTML",
                hx_confirm=f"Remove {email} from allowed list?",
                cls="secondary outline",
                style="padding: 0 0.5rem; margin-left: 0.5rem;",
            ),
            id=f"email-{email_id}",
        )

    @rt("/admin/emails/{email:path}")
    def remove_email(session, email: str):
        """Remove an email from the allowed list."""
        redirect = require_auth(session)
        if redirect:
            return redirect
        redirect = require_admin(session)
        if redirect:
            return redirect

        db.remove_allowed_email(email)
        return ""

    # -------------------------------------------------------------------------
    # API ENDPOINTS (Example of JSON APIs)
    # -------------------------------------------------------------------------
    # FastHTML can also serve JSON APIs alongside HTML routes.
    # -------------------------------------------------------------------------

    @rt("/api/health")
    def health_check():
        """Health check endpoint for monitoring."""
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}

    @rt("/api/stats")
    def stats(session):
        """Get application statistics (requires auth)."""
        if not session.get("user_email"):
            return {"error": "Unauthorized"}, 401

        return {
            "users": len(db.get_all_users()),
            "allowed_emails": len(db.get_allowed_emails()),
        }

    return fasthtml_app


# =============================================================================
# SECTION 4: MODAL FUNCTION DEFINITION
# =============================================================================
#
# This is where we tie everything together and deploy to Modal.
#
# The @app.function decorator defines a Modal function with:
# - image: The container environment
# - volumes: Persistent storage mounts
# - secrets: Injected environment variables
#
# The @modal.asgi_app decorator exposes the function as a web endpoint.
# =============================================================================

@app.function(
    # Use our custom container image with FastHTML installed
    image=image,

    # Mount the volume at /data for SQLite database storage
    # This ensures the database persists across container restarts
    volumes={VOLUME_PATH: volume},

    # Inject secrets as environment variables
    # These are securely stored in Modal and not visible in code
    secrets=[
        modal.Secret.from_name("google-oauth", required=False),
    ],

    # Allow concurrent requests to the same container
    # This improves performance by reusing warm containers
    # Note: SQLite handles concurrent reads well, but writes are serialized
    allow_concurrent_inputs=10,

    # Container lifecycle settings
    # container_idle_timeout: How long to keep warm containers alive
    # This reduces cold start latency for subsequent requests
    container_idle_timeout=300,  # 5 minutes
)
@modal.asgi_app()
def web():
    """
    The main Modal function that serves our web application.

    This function:
    1. Creates the FastHTML app with create_app()
    2. Returns the ASGI app for Modal to serve

    Modal handles:
    - HTTPS/TLS termination
    - Load balancing
    - Auto-scaling
    - Container lifecycle management
    """
    return create_app()


# =============================================================================
# SECTION 5: CLI UTILITIES
# =============================================================================
#
# Additional Modal functions for administrative tasks.
# These can be run from the command line with:
#     modal run app.py::function_name
# =============================================================================

@app.function(image=image, volumes={VOLUME_PATH: volume})
def init_admin(email: str):
    """
    Initialize an admin user.

    Usage:
        modal run app.py::init_admin --email=admin@example.com

    This adds the email to the allowed list and sets up initial access.
    """
    db = Database(DATABASE_PATH, volume)
    db.add_allowed_email(email, added_by="cli")
    print(f"Added {email} to allowed emails list")
    print("This user will be able to log in and access the application.")
    print("To make them an admin, they must first log in, then you can")
    print("update the database directly or add admin functionality.")


@app.function(image=image, volumes={VOLUME_PATH: volume})
def list_users():
    """
    List all users and allowed emails.

    Usage:
        modal run app.py::list_users
    """
    db = Database(DATABASE_PATH, volume)

    print("\n=== Allowed Emails ===")
    for email in db.get_allowed_emails():
        print(f"  - {email}")

    print("\n=== Registered Users ===")
    for user in db.get_all_users():
        admin_badge = " [ADMIN]" if user.is_admin else ""
        print(f"  - {user.name} ({user.email}){admin_badge}")
        print(f"    Last login: {user.last_login or 'Never'}")


@app.function(image=image, volumes={VOLUME_PATH: volume})
def make_admin(email: str):
    """
    Grant admin privileges to a user.

    Usage:
        modal run app.py::make_admin --email=user@example.com

    The user must have logged in at least once.
    """
    db = Database(DATABASE_PATH, volume)
    user = db.get_user_by_email(email)

    if not user:
        print(f"Error: User {email} not found. They must log in first.")
        return

    db.set_admin(email, True)
    print(f"Granted admin privileges to {email}")


# =============================================================================
# SECTION 6: LOCAL DEVELOPMENT
# =============================================================================
#
# For local development without Modal, you can run the app directly.
# This is useful for testing before deploying.
#
# Note: This won't work in Modal's container - it's just for local dev.
# =============================================================================

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║                    StatefulModal Template                          ║
    ╠═══════════════════════════════════════════════════════════════════╣
    ║                                                                    ║
    ║  For local development:                                           ║
    ║      modal serve app.py                                           ║
    ║                                                                    ║
    ║  For production deployment:                                        ║
    ║      modal deploy app.py                                          ║
    ║                                                                    ║
    ║  To add an initial admin:                                          ║
    ║      modal run app.py::init_admin --email=you@example.com        ║
    ║                                                                    ║
    ║  See README.md for complete setup instructions.                    ║
    ║                                                                    ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)
