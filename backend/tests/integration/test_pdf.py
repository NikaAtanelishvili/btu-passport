"""BE-25: PDF rendering — multi-page, Georgian text, determinism (NFR-12, NFR-13).

Uses poppler's pdfinfo / pdffonts / pdftotext, as the plan's Done when does.
"""

import copy
import hashlib
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models import PassportVersion
from app.pdf.render import render_passport
from app.services import content, issuance

ISSUED = datetime(2026, 10, 22, 15, 40, 12, tzinfo=UTC)
GEORGIAN = ("ნიკოლოზ", "გელაშვილი")

pytestmark = pytest.mark.skipif(not shutil.which("pdffonts"), reason="needs poppler-utils")


def _poppler(tool: str, pdf: bytes, tmp_path: Path) -> str:
    path = tmp_path / f"{hashlib.sha256(pdf).hexdigest()[:8]}.pdf"
    path.write_bytes(pdf)
    args = [tool, str(path)] + (["-"] if tool == "pdftotext" else [])
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def salome(seeded: Session) -> dict[str, Any]:
    """BTU-T-0007: the seed student with 6 skills."""
    [made] = issuance.create_versions(seeded, ["BTU-T-0007"])
    version = seeded.get(PassportVersion, made.version_id)
    assert version is not None
    c = content.build_content(seeded, version, verification_code="K7QM3XWP9D", issued_at=ISSUED)
    assert len(c["skills"]) == 6
    return c


def test_six_skills_render_to_several_pages_with_footer(
    salome: dict[str, Any], tmp_path: Path
) -> None:
    pdf = render_passport(salome)
    assert pdf.startswith(b"%PDF-")
    pages = int(
        next(
            line.split()[-1]
            for line in _poppler("pdfinfo", pdf, tmp_path).splitlines()
            if line.startswith("Pages:")
        )
    )
    assert pages >= 4  # cover, version, skills (one or more), last page
    text = _poppler("pdftotext", pdf, tmp_path)
    assert "BTU-AI-000135" in text and "Salome Chkheidze" in text and "K7QM-3XWP-9D" in text
    assert f"BTU-AI-000135 · v1 · K7QM-3XWP-9D · page 1 of {pages}" in text
    for skill in salome["skills"]:
        assert skill["name"] in text.replace("\n", " ")
    assert "http://localhost:3000/v/K7QM3XWP9D" in text


def test_georgian_name_is_embedded_and_extractable(salome: dict[str, Any], tmp_path: Path) -> None:
    georgian = copy.deepcopy(salome)
    georgian["holder"] = {"first_name": GEORGIAN[0], "last_name": GEORGIAN[1]}
    pdf = render_passport(georgian)
    fonts = _poppler("pdffonts", pdf, tmp_path)
    # WeasyPrint names the embedded subset "XXXXXX+Noto-Sans-Georgian".
    georgian_rows = [
        line for line in fonts.splitlines() if "NotoSansGeorgian" in line.replace("-", "")
    ]
    assert georgian_rows, fonts
    assert all(" yes " in row for row in georgian_rows)  # emb column
    assert " ".join(GEORGIAN) in _poppler("pdftotext", pdf, tmp_path)


def test_same_content_gives_the_same_bytes(salome: dict[str, Any]) -> None:
    first = render_passport(salome)
    time.sleep(1.1)  # the font subsetter used to stamp the wall-clock second into the PDF
    second = render_passport(copy.deepcopy(salome))
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_different_code_gives_different_bytes(salome: dict[str, Any]) -> None:
    other = {**salome, "verification_code": "AAAA0000AA", "verify_url": "x/v/AAAA0000AA"}
    assert render_passport(salome) != render_passport(other)
