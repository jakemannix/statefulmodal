# StatefulModal: Modal + FastHTML + SQLite Template

A pedagogical template demonstrating how to build stateful, authenticated web applications using modern Python serverless infrastructure.

## 🎯 What This Template Demonstrates

This template teaches you how to combine several powerful technologies:

| Component | Purpose | Why It's Great |
|-----------|---------|----------------|
| **[Modal](https://modal.com)** | Serverless cloud platform | Deploy Python apps with zero infrastructure management |
| **[FastHTML](https://fastht.ml)** | Python web framework | Build modern UIs in pure Python with HTMX |
| **[SQLite](https://sqlite.org)** | Embedded database | Simple, reliable data persistence |
| **Modal Volumes** | Persistent storage | Keep your database across container restarts |
| **Google OAuth** | Authentication | Secure login without managing passwords |
| **Modal Secrets** | Credential storage | Keep API keys secure and out of code |

## 📁 Project Structure

```
statefulmodal/
├── app.py              # Main application (heavily commented for learning)
├── requirements.txt    # Python dependencies
├── README.md          # This file
└── .gitignore         # Git ignore patterns
```

## 🚀 Quick Start

### Prerequisites

1. **Python 3.10+** installed locally
2. **Modal account** - Sign up free at [modal.com](https://modal.com)
3. **Google Cloud account** - For OAuth (optional, but recommended)

### Step 1: Install Modal CLI

```bash
pip install modal
modal token new
```

This opens a browser to authenticate with Modal.

### Step 2: Create the Modal Volume

Volumes provide persistent storage for your SQLite database:

```bash
modal volume create statefulmodal-data
```

### Step 3: Set Up Google OAuth (Optional but Recommended)

<details>
<summary>Click to expand OAuth setup instructions</summary>

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Navigate to **APIs & Services > Credentials**
4. Click **Create Credentials > OAuth client ID**
5. Choose **Web application**
6. Add authorized redirect URI:
   - For development: `https://your-username--statefulmodal-web-dev.modal.run/redirect`
   - For production: `https://your-username--statefulmodal-web.modal.run/redirect`
7. Copy the **Client ID** and **Client Secret**

Create the Modal secret:

```bash
modal secret create google-oauth \
    GOOGLE_CLIENT_ID="your-client-id-here" \
    GOOGLE_CLIENT_SECRET="your-client-secret-here"
```

</details>

### Step 4: Add Your Admin Email

Before deploying, add yourself as an allowed user:

```bash
modal run app.py::init_admin --email=your-email@gmail.com
```

### Step 5: Deploy!

**For development** (creates temporary URL, hot-reloads on changes):

```bash
modal serve app.py
```

**For production** (creates permanent URL):

```bash
modal deploy app.py
```

## 📖 Understanding the Code

The `app.py` file is extensively commented to explain each concept. Here's an overview:

### Section 1: Modal App Configuration

```python
app = modal.App(name="statefulmodal")

image = modal.Image.debian_slim(python_version="3.12").pip_install(...)

volume = modal.Volume.from_name("statefulmodal-data", create_if_missing=True)
```

**Key concepts:**
- **App**: Groups related functions together
- **Image**: Defines the container environment (like a Dockerfile)
- **Volume**: Persistent storage that survives restarts

### Section 2: Database Layer

```python
class Database:
    def __init__(self, db_path: str, volume_ref=None):
        self.volume = volume_ref  # For committing changes

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
            if self.volume:
                self.volume.commit()  # Persist to Modal Volume!
        finally:
            conn.close()
```

**Key concepts:**
- **Context managers**: Ensure connections are properly closed
- **Volume.commit()**: Explicitly saves changes to persistent storage
- **Dataclasses**: Clean data structures with `__ft__` for HTML rendering

### Section 3: FastHTML Application

```python
from fasthtml.common import *

app, rt = fast_app(hdrs=hdrs, secret_key=...)

@rt("/")
def home(session):
    return Div(H1("Hello"), P("World"))
```

**Key concepts:**
- **`fast_app()`**: Creates app with sensible defaults
- **`@rt` decorator**: Registers URL routes
- **HTML as Python**: `Div`, `H1`, `P` are Python functions
- **Session**: Encrypted cookie storage for user data

### Section 4: OAuth Integration

```python
from fasthtml.oauth import GoogleAppClient, OAuth

class AppAuth(OAuth):
    def get_auth(self, info, ident, session, state):
        # Check if email is allowed
        user = db.get_or_create_user(info.email, info.name)
        if user:
            session["user_email"] = user.email
            return RedirectResponse("/")
        return RedirectResponse("/error?msg=Access+denied")
```

**Key concepts:**
- **OAuth flow**: User → Google → Redirect back with token
- **Email whitelist**: Only approved emails can access
- **Session storage**: Keep user logged in

### Section 5: HTMX for Dynamic Updates

```html
<form hx-post="/notes/add" hx-target="#notes-list" hx-swap="afterbegin">
    <textarea name="content"></textarea>
    <button type="submit">Add Note</button>
</form>
```

**Key concepts:**
- **`hx-post`**: Send POST request without page reload
- **`hx-target`**: Where to put the response
- **`hx-swap`**: How to insert (afterbegin, beforeend, outerHTML, etc.)

### Section 6: Modal Function Definition

```python
@app.function(
    image=image,
    volumes={"/data": volume},
    secrets=[modal.Secret.from_name("google-oauth")],
    allow_concurrent_inputs=10,
)
@modal.asgi_app()
def web():
    return create_app()
```

**Key concepts:**
- **`@app.function`**: Defines a Modal function with resources
- **`@modal.asgi_app()`**: Exposes as web endpoint
- **Secrets injection**: Environment variables from Modal Secrets

## 🔧 CLI Commands

The template includes helpful CLI utilities:

```bash
# Add an email to the allowed list
modal run app.py::init_admin --email=user@example.com

# List all users and allowed emails
modal run app.py::list_users

# Grant admin privileges to a user
modal run app.py::make_admin --email=user@example.com
```

## 🏗️ Extending the Template

### Adding New Routes

```python
@rt("/my-feature")
def my_feature(session):
    user = get_current_user(session)
    if not user:
        return RedirectResponse("/login")

    return page_layout(
        "My Feature",
        H1("Welcome!"),
        P(f"Hello, {user.name}"),
        user=user
    )
```

### Adding Database Tables

```python
# In Database._init_db()
conn.execute("""
    CREATE TABLE IF NOT EXISTS my_table (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        data TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
""")
```

### Adding HTMX Interactions

```python
# In your route handler
@rt("/my-action")
def my_action(session, param: str):
    # Do something
    return Div("Updated content!", id="target")

# In your template
Button(
    "Click me",
    hx_post="/my-action",
    hx_target="#target",
    hx_swap="outerHTML"
)
```

## 🔒 Security Considerations

1. **Session Secret**: Change `SESSION_SECRET` in production
2. **Email Whitelist**: Only approved emails can access
3. **Admin Access**: Separate admin panel with privilege checks
4. **CSRF Protection**: Built into FastHTML's OAuth implementation
5. **Secrets Management**: API keys stored in Modal Secrets, not code

## 📚 Learning Resources

### Modal
- [Modal Documentation](https://modal.com/docs)
- [Modal Examples](https://github.com/modal-labs/modal-examples)
- [Modal Volumes Guide](https://modal.com/docs/guide/volumes)

### FastHTML
- [FastHTML Documentation](https://docs.fastht.ml)
- [FastHTML Examples](https://github.com/AnswerDotAI/fasthtml-example)
- [HTMX Documentation](https://htmx.org/docs/)

### SQLite
- [SQLite Documentation](https://sqlite.org/docs.html)
- [Python sqlite3 Module](https://docs.python.org/3/library/sqlite3.html)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## 📄 License

Apache License 2.0 - See [LICENSE](LICENSE) for details.

---

Built with ❤️ using [Modal](https://modal.com), [FastHTML](https://fastht.ml), and [SQLite](https://sqlite.org)
