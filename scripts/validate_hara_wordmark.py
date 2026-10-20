#!/usr/bin/env python3
"""Check the public HARA Labs brand has no dot-separated letters.

The check intentionally excludes signed installers, API and internal identifiers:
those are distinct, versioned compatibility contracts.
"""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PAGES = [ROOT / "index.html", *(ROOT / "public").rglob("*.html")]
UI = [
    ROOT / "apps/commander/public/index.html",
    ROOT / "apps/commander/public/app.js",
]
SVG = [
    ROOT / "brand/hara-capybara-gold-transparent.svg",
    *list((ROOT / "apps/identity-login/overlay").glob("hara-logo-*.svg")),
    ROOT / "apps/identity-login/overlay/favicon/hara-icon.svg",
    ROOT / "apps/identity-login/overlay/favicon/safari-pinned-tab.svg",
]
assert len(PAGES) >= 18, "MARKETING_PAGE_COVERAGE_REGRESSION"
for path in [*PAGES, *UI, *SVG]:
    text = path.read_text(encoding="utf-8")
    assert "H.A.R.A" not in text, f"LEGACY_DOTTED_BRAND:{path.relative_to(ROOT)}"
for path in [ROOT / "index.html", ROOT / "public/index.html"]:
    text = path.read_text(encoding="utf-8")
    assert '<span class="brand-word">HARA <b>Labs</b></span>' in text, "HEADER_WORDMARK"
    assert "<title>HARA Labs |" in text, "HTML_TITLE"
    assert '"name":"HARA Labs"' in text, "ORGANIZATION_SCHEMA"
    assert "hara-logo-web.webp?v=20261014-goldmark1" in text, "GOLD_CAPYBARA_PRESERVED"
assert (ROOT / "public/404.html").read_bytes() == (ROOT / "public/404/index.html").read_bytes(), "404_SOURCE_PARITY"
commander = UI[0].read_text(encoding="utf-8")
assert "<b>HARA</b><em>Labs</em>" in commander, "COMMANDER_HEADER_WORDMARK"
assert "app.js?v=20261014-wordmark1" in commander, "COMMANDER_APP_CACHE_REV"
for svg in SVG:
    ET.parse(svg)
print(f"HARA_LABS_WORDMARK=PASS; DOTTED_BRAND_REFERENCES=0; MARKETING_PAGES={len(PAGES)}; COMMANDER_UI=PASS; IDENTITY_SVG=PASS")
