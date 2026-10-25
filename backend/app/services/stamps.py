"""Stamp image checks (BE-51): PNG or SVG, at most 1 MB; a PNG is square and at least 600 px.
The type is read from the bytes, never from the file name or the browser's content type.

Stamps are served from our own origin (/api/stamps/...), so an SVG must not be able to run
anything: no DOCTYPE or entities, no script or foreignObject, no on* handlers, and no links
or url() references outside the file. The stamp route also sends a sandboxing CSP."""

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 1024 * 1024
PNG_MIN = 600
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_EXTERNAL_URL = re.compile(r"url\(\s*['\"]?(?!#)", re.IGNORECASE)
_BANNED_TAGS = {"script", "foreignobject", "iframe", "embed", "object"}


class StampError(ValueError):
    """The message goes under the file field."""


@dataclass(frozen=True)
class Stamp:
    ext: str  # "png" | "svg"
    mime: str


def check(data: bytes) -> Stamp:
    if len(data) > MAX_BYTES:
        raise StampError("The file is larger than 1 MB.")
    if data.startswith(PNG_SIGNATURE):
        _check_png(data)
        return Stamp("png", "image/png")
    _check_svg(data)
    return Stamp("svg", "image/svg+xml")


def _check_png(data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()  # reads every chunk: a truncated or corrupt file fails here
            width, height = image.size
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise StampError("Upload a PNG or SVG image; this PNG can't be read.") from None
    if width != height:
        raise StampError(f"The PNG must be square; this one is {width}x{height}.")
    if width < PNG_MIN:
        raise StampError(f"The PNG must be at least {PNG_MIN}x{PNG_MIN} px; this one is {width}.")


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1].rsplit(":", 1)[-1].lower()


def _check_svg(data: bytes) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise StampError("Upload a PNG or SVG image.") from None
    if re.search(r"<!(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise StampError("SVG files with a DOCTYPE or entities aren't accepted.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise StampError("Upload a PNG or SVG image; this file isn't valid SVG.") from None
    if _local(root.tag) != "svg":
        raise StampError("Upload a PNG or SVG image.")
    for element in root.iter():
        if _local(element.tag) in _BANNED_TAGS:
            raise StampError("SVG stamps can't contain script or embedded content.")
        if _local(element.tag) == "style" and _EXTERNAL_URL.search(element.text or ""):
            raise StampError("SVG stamps can't load external resources.")
        for name, value in element.attrib.items():
            attr = _local(name)
            if attr.startswith("on"):
                raise StampError("SVG stamps can't contain script (event handlers).")
            if attr == "href" and not value.strip().startswith("#"):
                raise StampError("SVG stamps can't link to external resources.")
            if _EXTERNAL_URL.search(value):
                raise StampError("SVG stamps can't load external resources.")
