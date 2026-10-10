"""Small helpers: decorators, validators, uploads."""
import os
import re
import secrets
import string
import uuid
from datetime import date, datetime
from functools import wraps

from flask import abort, current_app
from flask_login import current_user
from PIL import Image, UnidentifiedImageError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MOBILE_RE = re.compile(r"^\+?\d{10,15}$")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif"}


def roles_required(*roles):
    """Login + role check. Anonymous -> login page, wrong role -> 403 page."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return current_app.login_manager.unauthorized()
            if current_user.role not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def validate_password(pw):
    """Return an error message, or None when the password is acceptable."""
    if len(pw) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain at least one letter and one number."
    return None


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if validate_password(pw) is None:
            return pw


def parse_date(value):
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def safe_next(target):
    """Only allow redirects to local paths (prevents open-redirect attacks)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def save_photo(file_storage, old_filename=None):
    """Validate and store an uploaded profile photo.

    Returns (filename, error). The image is re-encoded with Pillow, which also
    guarantees that the uploaded file really is an image.
    """
    if not file_storage or not file_storage.filename:
        return None, None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in ALLOWED_EXT:
        return None, "Photo must be a PNG, JPG or GIF image."
    try:
        img = Image.open(file_storage.stream)
        img.verify()
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        img = img.convert("RGB")
        img.thumbnail((400, 400))
    except (UnidentifiedImageError, OSError, ValueError):
        return None, "The uploaded file is not a valid image."
    filename = f"{uuid.uuid4().hex}.jpg"
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    img.save(os.path.join(folder, filename), "JPEG", quality=88)
    delete_photo(old_filename)
    return filename, None


def delete_photo(filename):
    if not filename:
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], os.path.basename(filename))
    if os.path.isfile(path):
        os.remove(path)


def csv_safe(value):
    """Neutralise spreadsheet formula injection in CSV exports."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text
