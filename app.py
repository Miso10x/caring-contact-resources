"""Caring Contact Resource Finder: a password-protected resource search for volunteers.

Two shared passwords, both set as environment variables and never in source:
  VOLUNTEER_PASSWORD  search and read everything
  ADMIN_PASSWORD      also add, edit and delete (the Manage panel)
Every route except /login and /healthz requires one of them.
"""
import hmac
import os
import re
import time
from datetime import timedelta

from flask import Flask, jsonify, redirect, render_template_string, request, send_from_directory, session

import store

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
MAX_DOC_BYTES = 64 * 1024
DOC_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SESSION_SECRET") or os.urandom(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_INSECURE") != "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=MAX_DOC_BYTES,
)
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

_failures = {}  # ip -> (count, first_failure_time)


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() or request.remote_addr or "?"


def locked_out(ip):
    count, since = _failures.get(ip, (0, 0))
    if count >= MAX_ATTEMPTS and time.time() - since < LOCKOUT_SECONDS:
        return True
    if time.time() - since >= LOCKOUT_SECONDS:
        _failures.pop(ip, None)
    return False


def check_password(given):
    """Return 'admin', 'volunteer' or None. Fails closed when a password is unset."""
    given = (given or "").encode()
    admin = os.environ.get("ADMIN_PASSWORD", "").encode()
    volunteer = os.environ.get("VOLUNTEER_PASSWORD", "").encode()
    if admin and hmac.compare_digest(given, admin):
        return "admin"
    if volunteer and hmac.compare_digest(given, volunteer):
        return "volunteer"
    return None


def role():
    return session.get("role")


@app.before_request
def require_login():
    if request.path in ("/login", "/healthz"):
        return None
    if role() in ("admin", "volunteer"):
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Please sign in again."), 401
    return redirect("/login")


@app.get("/healthz")
def healthz():
    return "ok", 200


LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<title>Sign in · Caring Contact Resource Finder</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=League+Spartan:wght@700;800&display=swap">
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#E5F29C;color:#12305F;font:16px/1.5 "Atkinson Hyperlegible",system-ui,sans-serif;padding:16px;box-sizing:border-box}
form{background:#fff;border-radius:14px;padding:28px;max-width:380px;width:100%;display:grid;gap:14px;box-shadow:0 2px 0 #C9D6E3}
small{font:700 12px "League Spartan",system-ui,sans-serif;color:#0E8A78;letter-spacing:.05em;text-transform:uppercase}
h1{font:800 30px/1 "League Spartan",system-ui,sans-serif;margin:0}
label{font-weight:700;display:grid;gap:6px}
input{font:inherit;border:2px solid #0E3B7C;border-radius:8px;padding:10px 12px}
button{font:700 16px "League Spartan",system-ui,sans-serif;background:#0E3B7C;color:#fff;border:0;border-radius:8px;padding:12px}
.err{color:#A3281A;margin:0;font-weight:700}
p{margin:0;color:#4F6178;font-size:14px}
</style></head><body>
<form method="post" action="/login">
<div><small>Caring Contact · NJ</small><h1>Resource Finder</h1></div>
{% if error %}<p class="err">{{ error }}</p>{% endif %}
<label for="password">Password<input id="password" name="password" type="password" autocomplete="current-password" autofocus required></label>
<button type="submit">Sign in</button>
<p>For Caring Contact volunteers and staff. Ask Caring Contact staff if you need the password.</p>
</form></body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template_string(LOGIN_PAGE, error=None)
    ip = client_ip()
    if locked_out(ip):
        return render_template_string(LOGIN_PAGE, error="Too many wrong tries. Wait 15 minutes, then try again."), 429
    if not (os.environ.get("VOLUNTEER_PASSWORD") or os.environ.get("ADMIN_PASSWORD")):
        return render_template_string(LOGIN_PAGE, error="Sign-in isn't set up yet. Please tell Caring Contact staff."), 503
    who = check_password(request.form.get("password"))
    if not who:
        count, since = _failures.get(ip, (0, time.time()))
        _failures[ip] = (count + 1, since)
        return render_template_string(LOGIN_PAGE, error="That password isn't right. Check it and try again."), 401
    _failures.pop(ip, None)
    session.clear()
    session.permanent = True
    session["role"] = who
    return redirect("/")


@app.post("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.get("/")
def index():
    resp = send_from_directory(STATIC, "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/me")
def me():
    return jsonify(role=role())


@app.get("/api/data")
def data():
    resp = jsonify(store.all_docs())
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _check_write(collection, doc_id):
    if role() != "admin":
        return jsonify(error="Only staff can make changes."), 403
    # A JSON content type cannot be sent cross-site without a CORS preflight, which this app never grants.
    if request.method == "PUT" and not request.is_json:
        return jsonify(error="Expected JSON."), 415
    if request.headers.get("X-Requested-With") != "fetch":
        return jsonify(error="Missing request header."), 400
    if collection not in store.COLLECTIONS or not DOC_ID.match(doc_id):
        return jsonify(error="Unknown item."), 404
    return None


@app.put("/api/<collection>/<doc_id>")
def put_doc(collection, doc_id):
    bad = _check_write(collection, doc_id)
    if bad:
        return bad
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error="Expected a JSON object."), 400
    store.put(collection, doc_id, body)
    return jsonify(ok=True)


@app.delete("/api/<collection>/<doc_id>")
def delete_doc(collection, doc_id):
    bad = _check_write(collection, doc_id)
    if bad:
        return bad
    store.delete(collection, doc_id)
    return jsonify(ok=True)


store.seed_if_empty()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
