import html
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from hashlib import pbkdf2_hmac
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
FAVICON_PATH = BASE_DIR / "crow.jpeg"
DB_PATH = BASE_DIR / "thoughts.db"
HOST = "127.0.0.1"
PORT = 8000
SESSION_COOKIE = "thoughts_session"
CATEGORIES = [
    ("home", "Home"),
    ("movies-tv-shows", "Movies & TV Shows"),
    ("books", "Books"),
    ("music", "Music"),
    ("journal", "Journal"),
    ("random-thoughts", "Random Thoughts"),
    ("about", "About Me"),
]
SESSIONS = {}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        INSERT OR IGNORE INTO site_settings (key, value)
        VALUES ('about_text', ''), ('owner_password', '')
        """
    )
    conn.commit()
    conn.close()


def get_setting(key):
    conn = db_connection()
    row = conn.execute("SELECT value FROM site_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else ""


def set_setting(key, value):
    conn = db_connection()
    conn.execute(
        """
        INSERT INTO site_settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"{salt}${digest.hex()}"


def verify_password(password, stored):
    if not stored or "$" not in stored:
        return False
    salt, expected = stored.split("$", 1)
    attempt = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return secrets.compare_digest(attempt, expected)


def category_exists(slug):
    return any(category == slug for category, _ in CATEGORIES)


def category_label(slug):
    for category, label in CATEGORIES:
        if category == slug:
            return label
    return slug.replace("-", " ").title()


def all_posts(category=None):
    conn = db_connection()
    if category and category != "home":
        rows = conn.execute(
            "SELECT * FROM posts WHERE category = ? ORDER BY updated_at DESC", (category,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM posts ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_post(post_id):
    conn = db_connection()
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_post(category, title, content):
    timestamp = utc_now()
    conn = db_connection()
    cur = conn.execute(
        """
        INSERT INTO posts (category, title, content, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (category, title.strip(), content.strip(), timestamp, timestamp),
    )
    conn.commit()
    post_id = cur.lastrowid
    conn.close()
    return get_post(post_id)


def update_post(post_id, category, title, content):
    conn = db_connection()
    conn.execute(
        "UPDATE posts SET category = ?, title = ?, content = ?, updated_at = ? WHERE id = ?",
        (category, title.strip(), content.strip(), utc_now(), post_id),
    )
    conn.commit()
    conn.close()
    return get_post(post_id)


def delete_post(post_id):
    conn = db_connection()
    cur = conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def initial_state(page_slug):
    return {
        "page": page_slug,
        "pageLabel": category_label(page_slug),
        "categories": [{"slug": slug, "label": label} for slug, label in CATEGORIES],
        "posts": all_posts(None if page_slug == "home" else page_slug),
        "aboutText": get_setting("about_text"),
        "ownerConfigured": bool(get_setting("owner_password")),
    }


def render_nav_link(slug, label, active):
    active_class = "nav-link active" if slug == active else "nav-link"
    href = "/" if slug == "home" else f"/page/{slug}"
    return f'<a class="{active_class}" href="{href}">{html.escape(label)}</a>'


def render_category_option(slug, label):
    return f'<option value="{html.escape(slug)}">{html.escape(label)}</option>'


def hero_copy(page_slug):
    copy = {
        "home": "All the latest here!",
        "movies-tv-shows": "My Reviews on things I've watched!",
        "books": "This page is notes on books I like, my to-reads or reviews on books Ive seen.",
        "music": "Songs, playlists, or bands/lyrics i like!",
        "journal": "This one is more like my diary, day in the lifes or just how things've been!",
        "random-thoughts": "Pretty self explanitory.",
        "about": "Who i am!",
    }
    return copy.get(page_slug, "")


def page_shell(state):
    state_json = json.dumps(state).replace("</", "<\\/")
    page_name = html.escape(state["pageLabel"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>My Website!</title>
  <link rel="stylesheet" href="/static/style.css">
  <link rel="icon" type="image/jpeg" href="/crow.jpeg">
  <link rel="shortcut icon" type="image/jpeg" href="/crow.jpeg">
</head>
<body data-page="{html.escape(state['page'])}">
  <div class="page-shell">
    <aside class="sidebar">
      <div class="sidebar-inner">
        <div class="brand-card">
          <p class="brand-kicker">My archive</p>
          <h1>M.Doc</h1>
          <p class="brand-note">My wonderful amazing boyfriend made me this website! </p>
        </div>
        <nav class="nav-list" aria-label="Main navigation">
          {"".join(render_nav_link(item["slug"], item["label"], state["page"]) for item in state["categories"])}
        </nav>
        <button class="owner-toggle" id="ownerToggle" type="button" onclick="window.__softPagesOwnerAccess && window.__softPagesOwnerAccess()">Owner Access</button>
      </div>
    </aside>
    <main class="content">
      <header class="hero-card">
        <div>
          <p class="eyebrow">Page:</p>
          <h2>{page_name}</h2>
        </div>
        <p class="hero-copy">{hero_copy(state["page"])}</p>
      </header>
      <section class="content-card">
        <div class="toolbar">
          <div>
            <p class="toolbar-title">{page_name}</p>
            <p class="toolbar-subtitle" id="toolbarSubtitle"></p>
          </div>
          <div class="toolbar-actions">
            <button class="secondary hidden" id="logoutButton" type="button">Log Out</button>
            <button class="primary hidden" id="newPostButton" type="button">New Post</button>
            <button class="primary hidden" id="editAboutButton" type="button">Edit About</button>
          </div>
        </div>
        <div id="pageContent"></div>
      </section>
    </main>
  </div>
  <dialog class="modal" id="authDialog">
    <form class="modal-panel" id="authForm" method="dialog">
      <h3 id="authTitle">Owner Access</h3>
      <p id="authDescription">Log in to create or edit posts.</p>
      <label class="field">
        <span>Password</span>
        <input type="password" name="password" required minlength="6">
      </label>
      <p class="message" id="authMessage"></p>
      <div class="modal-actions">
        <button class="secondary" type="button" id="authCancel">Cancel</button>
        <button class="primary" type="submit">Continue</button>
      </div>
    </form>
  </dialog>
  <dialog class="modal" id="editorDialog">
    <form class="modal-panel large" id="editorForm" method="dialog">
      <h3 id="editorTitle">New Post</h3>
      <label class="field">
        <span>Category</span>
        <select name="category" required>
          {"".join(render_category_option(slug, label) for slug, label in CATEGORIES if slug not in {'home', 'about'})}
        </select>
      </label>
      <label class="field">
        <span>Title</span>
        <input type="text" name="title" required maxlength="120">
      </label>
      <label class="field">
        <span>Content</span>
        <textarea name="content" rows="12" required></textarea>
      </label>
      <input type="hidden" name="post_id">
      <p class="message" id="editorMessage"></p>
      <div class="modal-actions">
        <button class="secondary" type="button" id="editorCancel">Cancel</button>
        <button class="primary" type="submit">Save</button>
      </div>
    </form>
  </dialog>
  <dialog class="modal" id="aboutDialog">
    <form class="modal-panel large" id="aboutForm" method="dialog">
      <h3>Edit About Me</h3>
      <label class="field">
        <span>About text</span>
        <textarea name="about_text" rows="12" required></textarea>
      </label>
      <p class="message" id="aboutMessage"></p>
      <div class="modal-actions">
        <button class="secondary" type="button" id="aboutCancel">Cancel</button>
        <button class="primary" type="submit">Save</button>
      </div>
    </form>
  </dialog>
  <script id="initial-state" type="application/json">{state_json}</script>
  <script src="/static/app.js"></script>
</body>
</html>
"""


def validate_post_payload(category, title, content):
    if category in {"home", "about"} or not category_exists(category):
        return "Choose a valid category."
    if not title:
        return "Title is required."
    if not content:
        return "Content is required."
    return None


def parse_json_bytes(raw):
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        return {}


def session_token_from_cookie(cookie_header):
    jar = cookies.SimpleCookie()
    if cookie_header:
        jar.load(cookie_header)
    token = jar.get(SESSION_COOKIE)
    return token.value if token and token.value in SESSIONS else None


def json_payload(data):
    return json.dumps(data).encode("utf-8")


def response(status, content_type, body, set_cookie=None, clear_cookie=False):
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
    ]
    if set_cookie:
        headers.append(("Set-Cookie", set_cookie))
    if clear_cookie:
        headers.append(
            ("Set-Cookie", f"{SESSION_COOKIE}=deleted; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT")
        )
    return status, headers, body


def not_found_response():
    return response("404 Not Found", "text/html; charset=utf-8", b"<h1>Not Found</h1>")


def static_response(relative_path):
    asset_path = (STATIC_DIR / relative_path).resolve()
    if not str(asset_path).startswith(str(STATIC_DIR.resolve())) or not asset_path.exists():
        return not_found_response()
    content_type = "text/plain; charset=utf-8"
    if asset_path.suffix == ".css":
        content_type = "text/css; charset=utf-8"
    elif asset_path.suffix == ".js":
        content_type = "application/javascript; charset=utf-8"
    return response("200 OK", content_type, asset_path.read_bytes())


def favicon_response():
    if not FAVICON_PATH.exists():
        return not_found_response()
    return response("200 OK", "image/jpeg", FAVICON_PATH.read_bytes())


def route_request(method, path, query_string="", raw_body=b"", cookie_header=""):
    parsed_query = parse_qs(query_string)
    session_token = session_token_from_cookie(cookie_header)
    is_authenticated = bool(session_token)

    if method == "GET" and path.startswith("/static/"):
        return static_response(path.removeprefix("/static/"))

    if method == "GET" and path == "/crow.jpeg":
        return favicon_response()

    if method == "GET" and path == "/api/session":
        return response("200 OK", "application/json; charset=utf-8", json_payload({"authenticated": is_authenticated}))

    if method == "GET" and path == "/api/posts":
        category = parsed_query.get("category", [""])[0]
        if category and category != "home" and not category_exists(category):
            return response("404 Not Found", "application/json; charset=utf-8", json_payload({"error": "Unknown category."}))
        posts = all_posts(None if category == "home" else category)
        return response("200 OK", "application/json; charset=utf-8", json_payload({"posts": posts}))

    if method == "GET" and path == "/api/about":
        return response("200 OK", "application/json; charset=utf-8", json_payload({"aboutText": get_setting("about_text")}))

    if method == "GET" and path == "/":
        return response("200 OK", "text/html; charset=utf-8", page_shell(initial_state("home")).encode("utf-8"))

    if method == "GET" and path.startswith("/page/"):
        slug = path.split("/page/", 1)[1]
        if not category_exists(slug):
            return not_found_response()
        return response("200 OK", "text/html; charset=utf-8", page_shell(initial_state(slug)).encode("utf-8"))

    if method == "GET" and path.startswith("/post/"):
        post_id = path.split("/post/", 1)[1]
        if not post_id.isdigit():
            return not_found_response()
        post = get_post(int(post_id))
        if not post:
            return not_found_response()
        state = initial_state(post["category"])
        state["focusedPost"] = post
        return response("200 OK", "text/html; charset=utf-8", page_shell(state).encode("utf-8"))

    payload = parse_json_bytes(raw_body)

    if method == "POST" and path == "/api/setup":
        if get_setting("owner_password"):
            return response("409 Conflict", "application/json; charset=utf-8", json_payload({"error": "Owner password already set."}))
        password = payload.get("password", "").strip()
        if len(password) < 6:
            return response("400 Bad Request", "application/json; charset=utf-8", json_payload({"error": "Password must be at least 6 characters."}))
        set_setting("owner_password", hash_password(password))
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = True
        return response(
            "200 OK",
            "application/json; charset=utf-8",
            json_payload({"ok": True}),
            set_cookie=f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax",
        )

    if method == "POST" and path == "/api/login":
        password = payload.get("password", "").strip()
        if not verify_password(password, get_setting("owner_password")):
            return response("401 Unauthorized", "application/json; charset=utf-8", json_payload({"error": "That password did not match."}))
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = True
        return response(
            "200 OK",
            "application/json; charset=utf-8",
            json_payload({"ok": True}),
            set_cookie=f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax",
        )

    if method == "POST" and path == "/api/logout":
        if session_token:
            SESSIONS.pop(session_token, None)
        return response("200 OK", "application/json; charset=utf-8", json_payload({"ok": True}), clear_cookie=True)

    if method == "POST" and path == "/api/posts":
        if not is_authenticated:
            return response("401 Unauthorized", "application/json; charset=utf-8", json_payload({"error": "Please log in."}))
        category = payload.get("category", "").strip()
        title = payload.get("title", "").strip()
        content = payload.get("content", "").strip()
        error = validate_post_payload(category, title, content)
        if error:
            return response("400 Bad Request", "application/json; charset=utf-8", json_payload({"error": error}))
        return response("201 Created", "application/json; charset=utf-8", json_payload({"post": create_post(category, title, content)}))

    if method == "POST" and path == "/api/about":
        if not is_authenticated:
            return response("401 Unauthorized", "application/json; charset=utf-8", json_payload({"error": "Please log in."}))
        about_text = payload.get("about_text", "").strip()
        set_setting("about_text", about_text)
        return response("200 OK", "application/json; charset=utf-8", json_payload({"aboutText": about_text}))

    if method == "PUT" and path.startswith("/api/posts/"):
        if not is_authenticated:
            return response("401 Unauthorized", "application/json; charset=utf-8", json_payload({"error": "Please log in."}))
        post_id = path.split("/api/posts/", 1)[1]
        if not post_id.isdigit():
            return not_found_response()
        category = payload.get("category", "").strip()
        title = payload.get("title", "").strip()
        content = payload.get("content", "").strip()
        error = validate_post_payload(category, title, content)
        if error:
            return response("400 Bad Request", "application/json; charset=utf-8", json_payload({"error": error}))
        post = update_post(int(post_id), category, title, content)
        if not post:
            return response("404 Not Found", "application/json; charset=utf-8", json_payload({"error": "Post not found."}))
        return response("200 OK", "application/json; charset=utf-8", json_payload({"post": post}))

    if method == "DELETE" and path.startswith("/api/posts/"):
        if not is_authenticated:
            return response("401 Unauthorized", "application/json; charset=utf-8", json_payload({"error": "Please log in."}))
        post_id = path.split("/api/posts/", 1)[1]
        if not post_id.isdigit():
            return not_found_response()
        if not delete_post(int(post_id)):
            return response("404 Not Found", "application/json; charset=utf-8", json_payload({"error": "Post not found."}))
        return response("200 OK", "application/json; charset=utf-8", json_payload({"ok": True}))

    return not_found_response()


class ThoughtHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/crow.jpeg":
            return self.serve_favicon()
        if path.startswith("/static/"):
            return self.serve_static(path.removeprefix("/static/"))
        if path == "/api/session":
            return self.json_response({"authenticated": self.is_authenticated()})
        if path == "/api/posts":
            category = parse_qs(parsed.query).get("category", [""])[0]
            if category and category != "home" and not category_exists(category):
                return self.json_response({"error": "Unknown category."}, status=404)
            return self.json_response({"posts": all_posts(None if category == "home" else category)})
        if path == "/api/about":
            return self.json_response({"aboutText": get_setting("about_text")})
        if path == "/":
            return self.html_response(page_shell(initial_state("home")))
        if path.startswith("/page/"):
            slug = path.split("/page/", 1)[1]
            if not category_exists(slug):
                return self.not_found()
            return self.html_response(page_shell(initial_state(slug)))
        if path.startswith("/post/"):
            post_id = path.split("/post/", 1)[1]
            if not post_id.isdigit():
                return self.not_found()
            post = get_post(int(post_id))
            if not post:
                return self.not_found()
            state = initial_state(post["category"])
            state["focusedPost"] = post
            return self.html_response(page_shell(state))
        return self.not_found()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/setup":
            if get_setting("owner_password"):
                return self.json_response({"error": "Owner password already set."}, status=409)
            payload = self.read_json()
            password = payload.get("password", "").strip()
            if len(password) < 6:
                return self.json_response({"error": "Password must be at least 6 characters."}, status=400)
            set_setting("owner_password", hash_password(password))
            return self.start_session()
        if parsed.path == "/api/login":
            payload = self.read_json()
            password = payload.get("password", "").strip()
            if not verify_password(password, get_setting("owner_password")):
                return self.json_response({"error": "That password did not match."}, status=401)
            return self.start_session()
        if parsed.path == "/api/logout":
            self.end_session()
            return self.json_response({"ok": True}, clear_cookie=True)
        if parsed.path == "/api/posts":
            if not self.is_authenticated():
                return self.json_response({"error": "Please log in."}, status=401)
            payload = self.read_json()
            category = payload.get("category", "").strip()
            title = payload.get("title", "").strip()
            content = payload.get("content", "").strip()
            error = validate_post_payload(category, title, content)
            if error:
                return self.json_response({"error": error}, status=400)
            return self.json_response({"post": create_post(category, title, content)}, status=201)
        if parsed.path == "/api/about":
            if not self.is_authenticated():
                return self.json_response({"error": "Please log in."}, status=401)
            payload = self.read_json()
            about_text = payload.get("about_text", "").strip()
            set_setting("about_text", about_text)
            return self.json_response({"aboutText": about_text})
        return self.not_found()

    def do_PUT(self):
        if not self.path.startswith("/api/posts/"):
            return self.not_found()
        if not self.is_authenticated():
            return self.json_response({"error": "Please log in."}, status=401)
        post_id = self.path.split("/api/posts/", 1)[1]
        if not post_id.isdigit():
            return self.not_found()
        payload = self.read_json()
        category = payload.get("category", "").strip()
        title = payload.get("title", "").strip()
        content = payload.get("content", "").strip()
        error = validate_post_payload(category, title, content)
        if error:
            return self.json_response({"error": error}, status=400)
        post = update_post(int(post_id), category, title, content)
        if not post:
            return self.json_response({"error": "Post not found."}, status=404)
        return self.json_response({"post": post})

    def do_DELETE(self):
        if not self.path.startswith("/api/posts/"):
            return self.not_found()
        if not self.is_authenticated():
            return self.json_response({"error": "Please log in."}, status=401)
        post_id = self.path.split("/api/posts/", 1)[1]
        if not post_id.isdigit():
            return self.not_found()
        if not delete_post(int(post_id)):
            return self.json_response({"error": "Post not found."}, status=404)
        return self.json_response({"ok": True})

    def serve_static(self, relative_path):
        asset_path = (STATIC_DIR / relative_path).resolve()
        if not str(asset_path).startswith(str(STATIC_DIR.resolve())) or not asset_path.exists():
            return self.not_found()
        content_type = "text/plain; charset=utf-8"
        if asset_path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif asset_path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        data = asset_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_favicon(self):
        if not FAVICON_PATH.exists():
            return self.not_found()
        data = FAVICON_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def cookie_jar(self):
        jar = cookies.SimpleCookie()
        if self.headers.get("Cookie"):
            jar.load(self.headers.get("Cookie"))
        return jar

    def current_session(self):
        token = self.cookie_jar().get(SESSION_COOKIE)
        return token.value if token and token.value in SESSIONS else None

    def is_authenticated(self):
        return bool(self.current_session())

    def start_session(self):
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = True
        return self.json_response(
            {"ok": True},
            set_cookie=f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax",
        )

    def end_session(self):
        token = self.current_session()
        if token:
            SESSIONS.pop(token, None)

    def html_response(self, content, status=200):
        payload = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def json_response(self, data, status=200, set_cookie=None, clear_cookie=False):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        if clear_cookie:
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE}=deleted; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT",
            )
        self.end_headers()
        self.wfile.write(payload)

    def not_found(self):
        return self.html_response("<h1>Not Found</h1>", status=404)

    def log_message(self, format, *args):
        return


def application(environ, start_response):
    init_db()
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")
    query_string = environ.get("QUERY_STRING", "")
    cookie_header = environ.get("HTTP_COOKIE", "")
    try:
        content_length = int(environ.get("CONTENT_LENGTH", "0") or "0")
    except ValueError:
        content_length = 0
    raw_body = environ["wsgi.input"].read(content_length) if content_length else b""
    status, headers, body = route_request(method, path, query_string, raw_body, cookie_header)
    start_response(status, headers)
    return [body]


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), ThoughtHandler)
    print(f"Soft Pages is running at http://{HOST}:{PORT}")
    server.serve_forever()
