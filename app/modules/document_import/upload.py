"""Shared bounded upload handling for document-import workflows."""

from fastapi import UploadFile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UploadTooLargeError(ValueError):
    pass


async def read_upload_bytes(upload: UploadFile, limit: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read a single upload into memory only after enforcing a hard size cap."""
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise UploadTooLargeError(f"حجم الملف يتجاوز الحد المسموح ({limit // (1024 * 1024)} ميغابايت).")
    return data
