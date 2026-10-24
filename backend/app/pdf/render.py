"""Passport PDF renderer (BE-25): Jinja2 HTML/CSS -> WeasyPrint.

Renders only from content_json and never queries the database, so the same content always
gives the same bytes (NFR-13). The template folder is PASSPORT_TEMPLATE_DIR, so BTU's design
can replace the plain one without code changes.
"""

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import jinja2
import segno
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from app.config import get_settings
from app.services import storage
from app.services.codes import format_code

BACKEND_DIR = Path(__file__).resolve().parents[2]
FONTS_DIR = Path(__file__).resolve().parent / "fonts"
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

# sha256 -> (bytes, extension)
StampLoader = Callable[[str], tuple[bytes, str] | None]


def template_dir() -> Path:
    path = Path(get_settings().passport_template_dir)
    return path if path.is_absolute() else BACKEND_DIR / path


def _long_date(value: str) -> str:
    """'2026-10-22' or an ISO timestamp -> '22 October 2026' (no locale involved)."""
    d = date.fromisoformat(value[:10])
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _css_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


@lru_cache
def _environment(directory: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(directory),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["long_date"] = _long_date
    env.filters["css_string"] = _css_string
    env.filters["code"] = format_code
    return env


def _pdf_identifier(content: dict[str, Any]) -> bytes:
    """A fixed PDF /ID derived from the content instead of a random one."""
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()[:32].encode()


@contextmanager
def _source_date_epoch(moment: datetime) -> Iterator[None]:
    """fontTools stamps every subset font with the current time (head.modified) unless
    SOURCE_DATE_EPOCH is set, so two renders a second apart differed. Pin it to issued_at.
    Not thread-safe (process environment); the worker renders one PDF at a time."""
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(int(moment.timestamp()))
    try:
        yield
    finally:
        if previous is None:
            del os.environ["SOURCE_DATE_EPOCH"]
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous


def render_passport(content: dict[str, Any], load_stamp: StampLoader = storage.get_stamp) -> bytes:
    directory = template_dir()
    template = _environment(directory).get_template("passport.html.j2")
    qr = segno.make(content["verify_url"], error="m").svg_data_uri(scale=4)
    with tempfile.TemporaryDirectory(prefix="passport-") as tmp:
        stamps: dict[str, str] = {}
        for sha in sorted({s["stamp_sha256"] for s in content["skills"] if s["stamp_sha256"]}):
            loaded = load_stamp(sha)
            if loaded is None:
                continue  # a category without a stamp image renders without one
            data, ext = loaded
            (Path(tmp) / "stamps").mkdir(exist_ok=True)
            (Path(tmp) / "stamps" / f"{sha}.{ext}").write_bytes(data)
            stamps[sha] = f"stamps/{sha}.{ext}"
        html = template.render(
            c=content,
            qr=qr,
            stamps=stamps,
            fonts_url=FONTS_DIR.as_uri(),
            template_url=directory.as_uri(),
        )
        issued_at = datetime.fromisoformat(content["issued_at"].replace("Z", "+00:00"))
        with _source_date_epoch(issued_at):
            pdf = HTML(string=html, base_url=tmp + "/").write_pdf(
                font_config=FontConfiguration(),
                pdf_identifier=_pdf_identifier(content),
            )
    assert isinstance(pdf, bytes)
    return pdf
