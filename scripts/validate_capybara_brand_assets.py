#!/usr/bin/env python3
"""Read-only H.A.R.A brand conversion/usage checks."""
from __future__ import annotations

import hashlib
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "20261014-goldmark1"


def digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pixel(p: Path, x: int, y: int) -> tuple[int, ...]:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(p), "-vf",
         f"format=rgba,crop=1:1:{x}:{y}", "-frames:v", "1",
         "-pix_fmt", "rgba", "-f", "rawvideo", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if len(proc.stdout) != 4:
        raise AssertionError(f"PIXEL_INVALID:{p}:{len(proc.stdout)}")
    return tuple(proc.stdout)


def main() -> None:
    svg = ROOT / "brand/hara-capybara-gold-transparent.svg"
    assert ET.parse(svg).getroot().tag.endswith("svg")
    assert "gold" in svg.read_text()
    assert "pyramid" not in svg.read_text().lower()
    asset_pairs = sorted((ROOT / "assets/images").iterdir())
    compared = 0
    for primary in asset_pairs:
        if primary.suffix not in {".png", ".webp"}:
            continue
        deploy = ROOT / "public/assets/images" / primary.name
        assert deploy.is_file() and digest(primary) == digest(deploy), primary.name
        compared += 1

    for p, x, y in [
        (ROOT / "public/assets/images/hara-logo-web.webp", 0, 0),
        (ROOT / "public/assets/images/favicon-512.png", 0, 0),
        (ROOT / "apps/commander/public/assets/hara-commander-royal.webp", 0, 0),
        (ROOT / "apps/identity-login/overlay/favicon/favicon-32x32.png", 0, 0),
    ]:
        rgba = pixel(p, x, y)
        assert rgba[3] == 0, (p, "TRANSPARENCY_LOST", rgba)

    logo = ROOT / "public/assets/images/hara-logo-web.webp"
    assert pixel(logo, 256, 256)[3] >= 230, "EMPTY_MAIN_LOGO"
    assert pixel(logo, 256, 256)[0] > 200, "GOLD_LOST"

    htmls = [ROOT / "index.html", *(ROOT / "public").rglob("*.html")]
    refs = 0
    for p in htmls:
        src = p.read_text(encoding="utf-8")
        if "/assets/images/hara-logo-web.webp" not in src:
            continue
        assert "/assets/images/hara-logo-web.webp?v=" + VERSION in src, p
        assert "/assets/images/hara-logo-web.webp\"" not in src, p
        refs += src.count("/assets/images/hara-logo-web.webp?v=" + VERSION)
    commander = (ROOT / "apps/commander/public/index.html").read_text(encoding="utf-8")
    assert commander.count("?v=" + VERSION) == 5
    assert "?v=20260921-final1" not in commander
    for name in ["hara-logo-light.svg", "hara-logo-dark.svg", "favicon/hara-icon.svg", "favicon/safari-pinned-tab.svg"]:
        ET.parse(ROOT / "apps/identity-login/overlay" / name)
    ico = (ROOT / "apps/identity-login/overlay/favicon/favicon.ico").read_bytes()
    assert struct.unpack_from("<HHH", ico) == (0, 1, 3), "ICO_INVALID"
    print(f"BRAND_VALIDATION=PASS; asset_parity={compared}; versioned_html_refs={refs}")
    print(f"BRAND_SVG_SHA256={digest(svg)}")
    print(f"BRAND_WEBP_SHA256={digest(logo)}")


if __name__ == "__main__":
    main()
