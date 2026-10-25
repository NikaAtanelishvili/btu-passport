"""Passport PDF renderer (BE-25): Jinja2 HTML/CSS -> WeasyPrint.

Renders only from content_json and never queries the database, so the same content always
gives the same bytes (NFR-13). The template is BTU's passport design (docs/design/passport/);
PASSPORT_TEMPLATE_DIR can still point at another one. Only new versions are rendered: issued PDFs
are stored by SHA-256 and never rendered again.
"""

import base64
import hashlib
import io
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import jinja2
import segno
from PIL import Image
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from app.config import get_settings
from app.services import storage
from app.services.codes import format_code

BACKEND_DIR = Path(__file__).resolve().parents[2]
FONTS_DIR = Path(__file__).resolve().parent / "fonts"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"  # BTU logo, cover stickers, stamps
# btu-logo.png is an 8041 px square canvas with the mark inside this box (fractions; the same box
# as web/components/brand.tsx). The file stays as it is: the mark is cropped and scaled in memory,
# since decoding the whole canvas on every render took seconds and ~256 MB.
LOGO_BOX = (0.2102, 0.2807, 0.5794, 0.7014)  # left, top, width, height
LOGO_HEIGHT = 480  # px: sharp at the largest size printed (57 px = 15 mm, ~800 dpi)
SLOTS_PER_PAGE = 10  # the skillset grid: 5 x 2 boxes, empty ones stay empty

# sha256 -> (bytes, extension)
StampLoader = Callable[[str], tuple[bytes, str] | None]


def template_dir() -> Path:
    path = Path(get_settings().passport_template_dir)
    return path if path.is_absolute() else BACKEND_DIR / path


def _dotted_date(value: str) -> str:
    """'2026-10-22' or an ISO timestamp -> '22.10.2026' (the design's skillset grid)."""
    d = date.fromisoformat(value[:10])
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _earned_through(skill: dict[str, Any]) -> str:
    """The event's name, else the direct award's reason. DEFAULT(PDF): seed awards (earlier BTU
    records) and direct awards without a reason say "Direct award"."""
    source = skill["source"]
    if source["type"] == "event":
        return str(source["event_name"])
    return str(source.get("reason") or "Direct award")


def grid_pages(skills: list[dict[str, Any]]) -> list[list[dict[str, Any] | None]]:
    """Skills in pages of SLOTS_PER_PAGE, the last one padded with empty slots; at least one."""
    pages: list[list[dict[str, Any] | None]] = [
        list(skills[i : i + SLOTS_PER_PAGE]) for i in range(0, len(skills), SLOTS_PER_PAGE)
    ] or [[]]
    pages[-1] += [None] * (SLOTS_PER_PAGE - len(pages[-1]))
    return pages


@lru_cache
def _environment(directory: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(directory),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["code"] = format_code
    env.filters["dotted_date"] = _dotted_date
    env.filters["earned_through"] = _earned_through
    return env


@lru_cache(maxsize=1)
def btu_mark() -> bytes:
    """The BTU mark as a PNG, cropped from the logo canvas; the same bytes on every call."""
    left, top, width, height = LOGO_BOX
    with Image.open(ASSETS_DIR / "btu-logo.png") as canvas:
        size = canvas.width
        box = (
            round(left * size),
            round(top * size),
            round((left + width) * size),
            round((top + height) * size),
        )
        mark = canvas.crop(box)
        mark = mark.resize(
            (round(mark.width * LOGO_HEIGHT / mark.height), LOGO_HEIGHT), Image.Resampling.LANCZOS
        )
    out = io.BytesIO()
    mark.save(out, "PNG", optimize=False)
    return out.getvalue()


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


def _data_uri(data: bytes, ext: str) -> str:
    mime = "image/svg+xml" if ext == "svg" else f"image/{ext}"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def render_passport(content: dict[str, Any], load_stamp: StampLoader = storage.get_stamp) -> bytes:
    """Stamps and the BTU mark go in as data: URIs. WeasyPrint names each image in the PDF after
    its URL, so files in a fresh temporary folder gave different bytes on every render."""
    directory = template_dir()
    template = _environment(directory).get_template("passport.html.j2")
    qr = segno.make(content["verify_url"], error="m").svg_data_uri(scale=4, border=1)
    stamps: dict[str, str] = {}
    for sha in sorted({s["stamp_sha256"] for s in content["skills"] if s["stamp_sha256"]}):
        loaded = load_stamp(sha)
        if loaded is None:
            continue  # a category without a stamp image renders without one
        stamps[sha] = _data_uri(*loaded)
    html = template.render(
        c=content,
        qr=qr,
        stamps=stamps,
        btu_mark=_data_uri(btu_mark(), "png"),
        grid_pages=grid_pages(content["skills"]),
        fonts_url=FONTS_DIR.as_uri(),
        assets_url=ASSETS_DIR.as_uri(),
        template_url=directory.as_uri(),
    )
    issued_at = datetime.fromisoformat(content["issued_at"].replace("Z", "+00:00"))
    with _source_date_epoch(issued_at):
        pdf = HTML(string=html, base_url=directory.as_uri() + "/").write_pdf(
            font_config=FontConfiguration(),
            pdf_identifier=_pdf_identifier(content),
        )
    assert isinstance(pdf, bytes)
    return pdf
