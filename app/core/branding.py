"""Load release branding shared by the welcome screen and application shell."""

import base64
import json
import mimetypes
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = {
    "institution_name": "اسم المؤسسة",
    "description": "مساحة للنص التعريفي أو رسالة الترحيب",
    "developer_name": "اسم المطوّر أو الفريق",
    "version": "1.0.0",
    "logo_file": "logo.png",
}


def customization_directory() -> Path:
    """Return the branding assets shipped with this build.

    Frozen builds read from the protected PyInstaller bundle. In source mode,
    the project folder is the programmer-controlled source for the next build.
    """
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent / "_internal"))
        return bundle_root / "splash-screen"
    return PROJECT_ROOT / "splash-screen"


def _load_configuration() -> tuple[Path, dict[str, str]]:
    directory = customization_directory()
    values = DEFAULTS.copy()
    try:
        loaded = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = {}
    if isinstance(loaded, dict):
        for key in DEFAULTS:
            value = loaded.get(key)
            if isinstance(value, str) and value.strip():
                values[key] = value.strip()
    return directory, values


def load_institution_name() -> str:
    """Read the institution name from the editable branding configuration."""
    _, values = _load_configuration()
    return values["institution_name"]


def load_splash_content() -> dict[str, str | None]:
    """Read editable welcome text and an optional logo without rebuilding."""
    directory, values = _load_configuration()

    logo_file = values["logo_file"]
    logo_path = directory / logo_file
    logo_url = None
    if Path(logo_file).name == logo_file and logo_path.is_file() and logo_path.stat().st_size <= 5_000_000:
        mime_type = mimetypes.guess_type(logo_path.name)[0] or "application/octet-stream"
        if mime_type.startswith("image/"):
            encoded_logo = base64.b64encode(logo_path.read_bytes()).decode("ascii")
            logo_url = f"data:{mime_type};base64,{encoded_logo}"
    values["logo_url"] = logo_url
    return values
