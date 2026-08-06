"""Handle uploaded member profile photos."""
import os
import uuid

from werkzeug.utils import secure_filename

import config


def save_member_photo(member, file_storage):
    """
    Save an uploaded photo for a member.

    Returns the stored filename, or None if no file was uploaded.
    """
    if not file_storage or not file_storage.filename:
        return None

    extension = _allowed_extension(file_storage.filename)
    if not extension:
        raise ValueError("Photo must be a PNG, JPG, JPEG, GIF, or WEBP file.")

    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    if member.photo_filename:
        delete_member_photo(member)

    filename = secure_filename(f"member_{member.id}_{uuid.uuid4().hex[:10]}.{extension}")
    file_storage.save(os.path.join(config.UPLOAD_FOLDER, filename))
    member.photo_filename = filename
    return filename


def delete_member_photo(member):
    """Delete a member's stored photo file if it exists."""
    if not member.photo_filename:
        return

    path = os.path.join(config.UPLOAD_FOLDER, member.photo_filename)
    if os.path.exists(path):
        os.remove(path)
    member.photo_filename = None


def _allowed_extension(filename):
    """Return a safe extension if allowed, else None."""
    if "." not in filename:
        return None
    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in config.ALLOWED_PHOTO_EXTENSIONS:
        return None
    return "jpg" if extension == "jpeg" else extension
