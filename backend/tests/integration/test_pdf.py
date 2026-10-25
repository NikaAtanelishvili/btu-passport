"""BE-25: PDF rendering on BTU's design — pages, Georgian text, determinism (NFR-12, NFR-13).

Uses poppler's pdfinfo / pdffonts / pdftotext, as the plan's Done when does.
"""

import copy
import hashlib
import shutil
import subprocess
import time
from datetime import UTC, date, datetime
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


def _pages(pdf: bytes, tmp_path: Path) -> list[str]:
    """pdftotext of each page."""
    info = _poppler("pdfinfo", pdf, tmp_path)
    count = int(next(line.split()[-1] for line in info.splitlines() if line.startswith("Pages:")))
    path = tmp_path / f"{hashlib.sha256(pdf).hexdigest()[:8]}.pdf"
    return [
        subprocess.run(
            ["pdftotext", "-f", str(n), "-l", str(n), str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        for n in range(1, count + 1)
    ]


def _with_skills(c: dict[str, Any], n: int) -> dict[str, Any]:
    more = copy.deepcopy(c)
    more["skills"] = [
        {**c["skills"][i % len(c["skills"])], "skill_id": f"SKL-{i:03d}", "name": f"Skill {i}"}
        for i in range(n)
    ]
    return more


def test_design_pages_with_id_code_and_version_on_every_page(
    salome: dict[str, Any], tmp_path: Path
) -> None:
    """Cover, About, one skillset grid page (6 of 10 slots), then the detail table."""
    pages = _pages(render_passport(salome), tmp_path)
    assert len(pages) >= 4
    cover, about, grid, *detail = pages
    assert "Salome" in cover and "Chkheidze" in cover and "22.10.2026" in cover  # date of issue
    assert "UNDERSTANDING AI SKILLS STAMPS" in about
    assert "VERIFIED AI SKILLSET" in grid and "AI SKILLS DETAILED INFORMATION" in detail[0]
    for text in pages:
        flat = " ".join(text.split())
        assert "PASSPORT ID: BTU-AI-000135" in flat
        assert "CODE K7QM-3XWP-9D · VERSION 1" in flat
    table = " ".join(" ".join(detail).split())
    for skill in salome["skills"]:
        assert skill["name"].upper() in " ".join(grid.split()) and skill["name"].upper() in table
        assert date.fromisoformat(skill["date_earned"]).strftime("%d.%m.%Y") in table


def test_more_than_ten_skills_take_another_grid_page(
    salome: dict[str, Any], tmp_path: Path
) -> None:
    pages = _pages(render_passport(_with_skills(salome, 14)), tmp_path)
    grids = [text for text in pages if "VERIFIED AI SKILLSET" in text]
    assert len(grids) == 2
    assert "SKILL 9" in grids[0] and "SKILL 10" in grids[1]
    tables = " ".join(" ".join(t for t in pages if "DETAILED INFORMATION" in t).split())
    assert all(f"SKILL {i} " in tables + " " for i in range(14))


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
    assert any("Outfit" in line for line in fonts.splitlines()), fonts
    cover = _pages(pdf, tmp_path)[0]
    assert GEORGIAN[0] in cover and GEORGIAN[1] in cover


STAMP_PNG = (Path(__file__).parents[3] / "seed" / "stamps" / "stamp-ai-skill.png").read_bytes()


def _stamp(sha: str) -> tuple[bytes, str]:
    return STAMP_PNG, "png"


def test_same_content_gives_the_same_bytes(salome: dict[str, Any]) -> None:
    """With stamp images: they once came from a fresh temporary folder, and WeasyPrint names
    each image after its URL, so the bytes changed on every render."""
    first = render_passport(salome, _stamp)
    time.sleep(1.1)  # the font subsetter used to stamp the wall-clock second into the PDF
    second = render_passport(copy.deepcopy(salome), _stamp)
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_different_code_gives_different_bytes(salome: dict[str, Any]) -> None:
    other = {**salome, "verification_code": "AAAA0000AA", "verify_url": "x/v/AAAA0000AA"}
    assert render_passport(salome) != render_passport(other)
