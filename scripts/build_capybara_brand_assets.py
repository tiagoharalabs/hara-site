#!/usr/bin/env python3
"""Render one approved transparent HARA capybara SVG to legacy site brand slots.

Run from any directory: python3 scripts/build_capybara_brand_assets.py
Requires ffmpeg (librsvg, png, libwebp). No auth/production mutation.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "brand/hara-capybara-gold-transparent.svg"
SITE_IMAGES = ROOT / "assets/images"
DEPLOY_IMAGES = ROOT / "public/assets/images"
IDENTITY = ROOT / "apps/identity-login/overlay"
COMMANDER = ROOT / "apps/commander/public/assets"


def run(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], check=True)


def ico_from_pngs(target: Path, source: dict[int, Path]) -> None:
    offsets = 6 + 16 * len(source)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(source)))
    data = bytearray()
    for size, path in source.items():
        raw = path.read_bytes()
        directory.extend(struct.pack("<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0, 0, 0, 1, 32, len(raw), offsets + len(data)))
        data.extend(raw)
    target.write_bytes(directory + data)


def logo_lockup(color: str, subtitle: str) -> str:
    # Inline only the approved vector drawing, not an old triangular favicon.
    source = MASTER.read_text(encoding="utf-8")
    inner = source.split(">", 1)[1].rsplit("</svg>", 1)[0]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 310 64" role="img" aria-label="HARA Labs">'
        '<svg x="0" y="0" width="64" height="64" viewBox="108 50 1080 1150">' + inner + '</svg>'
        '<text x="80" y="31" font-family="Inter,Arial,sans-serif" font-size="24" font-weight="800" fill="' + color + '">HARA</text>'
        '<text x="80" y="51" font-family="Inter,Arial,sans-serif" font-size="16" font-weight="700" fill="' + subtitle + '">Labs · Identity</text>'
        '</svg>\n'
    )


def main() -> None:
    assert MASTER.is_file()
    with tempfile.TemporaryDirectory(prefix="hara-brand-") as td:
        tmp = Path(td)
        pngs: dict[int, Path] = {}
        for size in [16, 32, 150, 180, 192, 512, 1024]:
            target = tmp / f"logo-{size}.png"
            run("-i", str(MASTER), "-vf",
                f"scale={size}:{size}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:color=black@0",
                "-frames:v", "1", "-pix_fmt", "rgba", str(target))
            pngs[size] = target
        webp = tmp / "logo-512.webp"
        run("-i", str(pngs[512]), "-frames:v", "1", "-c:v", "libwebp",
            "-lossless", "1", "-pix_fmt", "yuva420p", str(webp))

        png_targets = {
            "hara-brand-flat-matte.png": 512,
            "hara-commander-logo.png": 512,
            "hara-logo-premium.png": 1024,
            "hara-mark-square.png": 512,
            "favicon-512.png": 512,
            "favicon-192.png": 192,
            "favicon-32.png": 32,
            "favicon-16.png": 16,
        }
        webp_targets = (
            "hara-logo-web.webp", "hara-mark-square.webp", "hara-logo-premium.webp",
            "capivara-01.webp", "capivara-02.webp", "capivara-03.webp",
            "404-capivara-watermark.webp",
        )
        for directory in [SITE_IMAGES, DEPLOY_IMAGES]:
            for file, size in png_targets.items():
                shutil.copyfile(pngs[size], directory / file)
            for file in webp_targets:
                shutil.copyfile(webp, directory / file)

        shutil.copyfile(pngs[1024], ROOT / "brand/hara-capybara-gold-transparent.png")
        shutil.copyfile(pngs[1024], ROOT / "brand/hara-capybara-flat-matte-source.png")
        shutil.copyfile(webp, COMMANDER / "hara-commander-royal.webp")

        favicon = IDENTITY / "favicon"
        icon_pngs = {
            "favicon-16x16.png": 16,
            "favicon-32x32.png": 32,
            "android-chrome-192x192.png": 192,
            "android-chrome-512x512.png": 512,
            "apple-touch-icon.png": 180,
            "mstile-150x150.png": 150,
        }
        for name, size in icon_pngs.items():
            shutil.copyfile(pngs[size], favicon / name)
        ico_from_pngs(favicon / "favicon.ico", {16: pngs[16], 32: pngs[32], 192: pngs[192]})
        shutil.copyfile(MASTER, favicon / "hara-icon.svg")
        shutil.copyfile(MASTER, favicon / "safari-pinned-tab.svg")

        (IDENTITY / "hara-logo-dark.svg").write_text(logo_lockup("#f4f8fb", "#8bdcff"), encoding="utf-8")
        (IDENTITY / "hara-logo-light.svg").write_text(logo_lockup("#0a2840", "#2d98d0"), encoding="utf-8")

    print("HARA_CAPYBARA_BRAND_ASSETS=GENERATED")
    print("HARA_CAPYBARA_CANONICAL_SOURCE=" + str(MASTER.relative_to(ROOT)))
    print("HARA_CAPYBARA_PUBLIC_ASSETS=" + str(len(png_targets) + len(webp_targets)))
    print("HARA_CAPYBARA_IDENTITY_AND_COMMANDER=GENERATED")


if __name__ == "__main__":
    main()
