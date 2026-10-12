"""Exercise the production image-to-click path on a local intercepted fixture.

The fixture checks each click against manually labelled boxes and target order.
No appointment website, credentials, order creation, or payment is involved.
"""
import base64
import json
import time
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from PIL import Image

from interview_forge.services import gym_automation as gym

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".maintenance" / "ocr-static-20261012"


def fixture(item, scale):
    image = Path(item["image"]).read_bytes()
    with Image.open(item["image"]) as original:
        display_width = round(original.width * scale)
    spec = {"boxes": [item["boxes"][i-1] for i in item["truth"]]}
    return """<!doctype html><meta charset="utf-8">
<style>body{margin:80px 100px;font-family:sans-serif}.verifybox img{display:block}</style>
<div class="verifybox"><p>请依次点击【TARGETS】</p>
<img id="captcha" src="data:image/png;base64,IMAGE" style="width:WIDTHpx">
<button id="verify">验证</button></div>
<script>
const spec=SPEC; window.smoke={clicks:[],passed:false};
const image=document.getElementById('captcha');
image.addEventListener('click', e=>{
 const r=image.getBoundingClientRect();
 const x=(e.clientX-r.left)/r.width*image.naturalWidth;
 const y=(e.clientY-r.top)/r.height*image.naturalHeight;
 const b=spec.boxes[window.smoke.clicks.length];
 window.smoke.clicks.push({x,y,correct:!!b&&x>=b[0]&&x<=b[2]&&y>=b[1]&&y<=b[3]});
});
document.getElementById('verify').onclick=()=>{
 window.smoke.passed=window.smoke.clicks.length===spec.boxes.length&&window.smoke.clicks.every(x=>x.correct);
 if(window.smoke.passed)history.replaceState({},'', '/confirm?tradeNo=local-fixture');
};
</script>""".replace("TARGETS", ",".join(item["targets"])).replace(
        "IMAGE", base64.b64encode(image).decode()).replace("WIDTH", str(display_width)).replace(
                "SPEC", json.dumps(spec, ensure_ascii=False))


def main():
    manifest = json.loads((OUT/"manifest.json").read_text(encoding="utf-8"))
    rows = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for scale in (.65, 1.8):
                for item in manifest:
                    context = browser.new_context(viewport={"width": 1600, "height": 1000})
                    try:
                        context.route("**/*", lambda route, request, html=fixture(item, scale):
                                      route.fulfill(status=200, content_type="text/html", body=html))
                        page = context.new_page()
                        page.goto("http://ocr-fixture.invalid/captcha")
                        page.wait_for_function("document.getElementById('captcha').naturalWidth>0")
                        started = time.perf_counter()
                        with patch.object(gym.time, "sleep"), \
                                patch.object(gym, "deepseek_key", side_effect=AssertionError("API lookup")), \
                                patch.object(gym, "_get_paddle", side_effect=AssertionError("Paddle init")):
                            result = gym.solve_click_captcha(page, OUT, max_attempts=1)
                        state = page.evaluate("window.smoke")
                        passed = state["passed"] and result is page and "tradeNo" in page.url
                        row = {"name": item["name"], "display_scale": scale,
                               "passed": passed, "clicks": state["clicks"],
                               "seconds_without_waits": round(time.perf_counter()-started, 3)}
                        rows.append(row)
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                        if not passed:
                            page.screenshot(path=str(OUT/f"browser-failure-{item['name']}-{scale}.png"))
                            raise AssertionError(f"Local click verification failed: {item['name']} scale={scale}")
                    finally:
                        context.close()
        finally:
            browser.close()
    (OUT/"browser-smoke-results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Local browser image-to-click checks: {len(rows)}/{len(rows)} passed")


if __name__ == "__main__":
    main()
