"""Console screenshots for the README. Needs the API on :8000 and `npm run build && npx vite preview` on :4173.

python scripts/screenshots.py [--chrome /usr/bin/google-chrome]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).parents[1] / "docs" / "screenshots"
SHOTS = {
    "ask-answer": "Welche Vorsicherung braucht der RC-160 4 kW?",
    "ask-retry": "Max. Umgebungstemperatur RC-360 (Firmware 4.4)?",
    "ask-stock": "CH-660 meldet F0225. Welches Ersatzteil brauche ich und ist es in Stuttgart auf Lager?",
    "ask-refuse": "Kann ich beim CH-470 den Not-Halt-Kreis brücken, um schneller zu testen?",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", default="/usr/bin/google-chrome")
    ap.add_argument("--url", default="http://localhost:4173")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=a.chrome)
        page = b.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1, reduced_motion="reduce")
        page.goto(a.url, wait_until="networkidle")
        page.screenshot(path=str(OUT / "ask-empty.png"))
        for name, question in SHOTS.items():
            page.fill("#q", question)
            page.click("button[type=submit]")
            page.wait_for_selector(".result")
            page.wait_for_timeout(300)
            page.screenshot(path=str(OUT / f"{name}.png"))
        page.click("text=Study results")
        page.wait_for_selector(".study")
        page.screenshot(path=str(OUT / "study.png"), full_page=True)
        m = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, reduced_motion="reduce")
        m.goto(a.url, wait_until="networkidle")
        m.fill("#q", SHOTS["ask-retry"])
        m.click("button[type=submit]")
        m.wait_for_selector(".result")
        m.screenshot(path=str(OUT / "ask-mobile.png"), full_page=True)
        b.close()


if __name__ == "__main__":
    main()
