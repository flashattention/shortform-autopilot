"""자동 녹화: 배포된 웹 게임·사이트를 세로 모바일 화면으로 열고 레시피대로 조작하며 녹화합니다."""
import os
import pathlib
import random
import shutil
import tempfile

from playwright.sync_api import sync_playwright

W, H = 720, 1280  # 9:16. 편집 단계에서 1080x1920으로 키웁니다.
GL_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
           "--autoplay-policy=no-user-gesture-required", "--mute-audio"]


def _pt(x, y):
    return int(x * W), int(y * H)


def _step(page, s, rng):
    do = s["do"]
    if do == "wait":
        page.wait_for_timeout(s.get("ms", 500))
    elif do == "tap":
        page.mouse.click(*_pt(s["x"], s["y"]))
    elif do == "random_taps":
        x0, y0, x1, y1 = s.get("area", [0.15, 0.3, 0.85, 0.85])
        for _ in range(s.get("count", 3)):
            page.mouse.click(*_pt(rng.uniform(x0, x1), rng.uniform(y0, y1)))
            page.wait_for_timeout(s.get("gap_ms", 300))
    elif do in ("drag", "swipe"):
        if do == "swipe":
            d = {"up": (0, -0.3), "down": (0, 0.3), "left": (-0.35, 0), "right": (0.35, 0)}[s["dir"]]
            a, b, ms = (0.5, 0.6), (0.5 + d[0], 0.6 + d[1]), 180
        else:
            a, b, ms = s["from"], s["to"], s.get("ms", 600)
        page.mouse.move(*_pt(*a))
        page.mouse.down()
        steps = max(4, ms // 30)
        for i in range(1, steps + 1):
            t = i / steps
            page.mouse.move(*_pt(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            page.wait_for_timeout(ms // steps)
        page.mouse.up()
    elif do == "key":
        page.keyboard.press(s["key"])
    elif do == "hold_key":
        page.keyboard.down(s["key"])
        page.wait_for_timeout(s.get("ms", 600))
        page.keyboard.up(s["key"])
    elif do == "scroll":
        page.mouse.wheel(0, s.get("dy", 300))
    else:
        raise ValueError(f"모르는 동작: {do}")


def capture(url, recipe, seconds, out_path, seed=0):
    """url 을 seconds 초 동안 녹화해 out_path(.webm)에 저장."""
    rng = random.Random(seed)
    out_path = pathlib.Path(out_path)
    tmp = tempfile.mkdtemp()
    launch = {"headless": True, "args": GL_ARGS}
    if os.environ.get("CHROME_PATH"):
        launch["executable_path"] = os.environ["CHROME_PATH"]
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        ctx = browser.new_context(
            viewport={"width": W, "height": H}, is_mobile=True, has_touch=False,
            user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36",
            record_video_dir=tmp, record_video_size={"width": W, "height": H},
        )
        page = ctx.new_page()
        page.goto(url, wait_until="load", timeout=60000)
        deadline = seconds * 1000
        elapsed = 0
        while elapsed < deadline:
            for s in recipe or [{"do": "wait", "ms": 500}]:
                t0 = page.evaluate("performance.now()")
                _step(page, s, rng)
                elapsed += page.evaluate("performance.now()") - t0
                if elapsed >= deadline:
                    break
        video = page.video
        ctx.close()
        browser.close()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(video.path(), out_path)
    shutil.rmtree(tmp, ignore_errors=True)
    return out_path
