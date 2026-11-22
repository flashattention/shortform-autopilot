"""자동 녹화: 배포된 웹 게임·사이트를 세로 모바일 화면으로 열고 레시피대로 조작하며 녹화합니다.

GitHub Actions 에는 그래픽카드가 없어 3D 게임이 초당 몇 장밖에 안 그려집니다. 그대로 녹화하면 끊겨 보이므로
게임 시계를 붙잡아 두고 1/30초씩 넘기면서 한 장씩 찍습니다. 그리는 데 오래 걸려도 결과 영상은 30fps 로 매끄럽습니다.
"""
import os
import pathlib
import random
import shutil
import subprocess
import tempfile

from playwright.sync_api import sync_playwright

W, H = 720, 1280  # 9:16. 편집 단계에서 1080x1920으로 키웁니다.
FPS = 30
GL_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
           "--autoplay-policy=no-user-gesture-required", "--mute-audio"]


def _pt(x, y):
    return int(x * W), int(y * H)


def _step(page, s, rng, wait):
    """레시피 한 동작. wait(ms) 는 그 시간만큼 게임 시간을 넘긴다(녹화 중이면 프레임도 찍는다)."""
    do = s["do"]
    if do == "wait":
        wait(s.get("ms", 500))
    elif do == "click":  # CSS 선택자로 버튼 누르기. if_visible 이면 화면에 보일 때만 누른다
        hit = page.evaluate("([sel, vis]) => { const el = document.querySelector(sel);"
                            " if (!el || (vis && !el.getClientRects().length)) return false; el.click(); return true; }",
                            [s["sel"], bool(s.get("if_visible"))])
        if hit:
            wait(s.get("ms", 300))
    elif do == "tap":
        page.mouse.click(*_pt(s["x"], s["y"]))
        wait(s.get("ms", 100))
    elif do == "random_taps":
        x0, y0, x1, y1 = s.get("area", [0.15, 0.3, 0.85, 0.85])
        for _ in range(s.get("count", 3)):
            page.mouse.click(*_pt(rng.uniform(x0, x1), rng.uniform(y0, y1)))
            wait(s.get("gap_ms", 300))
    elif do in ("drag", "swipe"):
        if do == "swipe":
            d = {"up": (0, -0.3), "down": (0, 0.3), "left": (-0.35, 0), "right": (0.35, 0)}[s["dir"]]
            a, b, ms = (0.5, 0.6), (0.5 + d[0], 0.6 + d[1]), 180
        else:
            a, b, ms = s["from"], s["to"], s.get("ms", 600)
        page.mouse.move(*_pt(*a))
        page.mouse.down()
        steps = max(4, ms // 33)
        for i in range(1, steps + 1):
            t = i / steps
            page.mouse.move(*_pt(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            wait(ms / steps)
        page.mouse.up()
    elif do == "key":
        page.keyboard.down(s["key"])
        wait(s.get("ms", 80))
        page.keyboard.up(s["key"])
    elif do == "hold_key":
        page.keyboard.down(s["key"])
        wait(s.get("ms", 600))
        page.keyboard.up(s["key"])
    elif do == "random_keys":  # 목록에서 아무 키나 골라 누름. 러너 게임용
        for _ in range(s.get("count", 3)):
            key = rng.choice(s["keys"])
            page.keyboard.down(key)
            wait(s.get("hold_ms", 120))
            page.keyboard.up(key)
            wait(rng.uniform(*s.get("gap_ms", [200, 700])))
    elif do == "hold_mouse":  # 마우스 버튼을 누른 채 유지 (연사 등). sweep 이 있으면 누른 채 좌우로 움직인다
        x, y = _pt(s.get("x", 0.5), s.get("y", 0.5))
        page.mouse.move(x, y)
        page.mouse.down()
        ms, sweep = s.get("ms", 1000), s.get("sweep", 0)
        steps = max(1, ms // 100)
        for i in range(steps):
            if sweep:
                page.mouse.move(x + int(sweep * W * rng.uniform(-1, 1)), y)
            wait(ms / steps)
        page.mouse.up()
    elif do == "touch_hold":  # 손가락을 댄 채 유지·이동. touches: [{from:[x,y], to:[x,y]}] 여러 손가락 가능
        cdp, pts = page.cdp, s["touches"]
        def at(t):
            return [{"x": (a["from"][0] + (a.get("to", a["from"])[0] - a["from"][0]) * t) * W,
                     "y": (a["from"][1] + (a.get("to", a["from"])[1] - a["from"][1]) * t) * H, "id": i}
                    for i, a in enumerate(pts)]
        cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": at(0)})
        ms = s.get("ms", 1000)
        steps = max(1, ms // 66)
        for i in range(1, steps + 1):
            cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": at(i / steps)})
            wait(ms / steps)
        cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
    elif do == "scroll":
        page.mouse.wheel(0, s.get("dy", 300))
        wait(s.get("ms", 300))
    else:
        raise ValueError(f"모르는 동작: {do}")


class Rejected(Exception):
    """찍기 전 화면 확인에서 끝내 통과하지 못함."""


def capture(url, recipe, seconds, out_path, seed=0, setup=None, block=None, routes=None, locale=None,
            touch=False, preflight=None, adjust=None, prepare=None):
    """url 을 seconds 초(게임 시간) 동안 녹화해 out_path(.mp4)에 저장.

    setup: 녹화 전에 실시간으로 실행할 동작(시작 버튼 누르기 등)
    preflight: 스크린샷(png bytes)을 받아 (통과, 이유)를 돌려주는 함수. 통과한 그 화면에서 이어서 녹화한다.
               떨어지면 adjust 동작으로 화면을 바꿔 다시 확인하고, 끝내 안 되면 Rejected 를 던진다
    block: 막을 요청 주소 패턴 목록. 봇 플레이가 운영 서버에 기록·통계를 남기지 않게 한다
    """
    rng = random.Random(seed)
    out_path = pathlib.Path(out_path)
    frames = pathlib.Path(tempfile.mkdtemp())
    launch = {"headless": True, "args": GL_ARGS}
    if os.environ.get("CHROME_PATH"):
        launch["executable_path"] = os.environ["CHROME_PATH"]
    total = int(seconds * FPS)
    n = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        ctx = browser.new_context(
            viewport={"width": W, "height": H}, is_mobile=True, has_touch=bool(touch),
            locale=locale or "ko-KR",   # 사이트가 브라우저 언어를 따라가면 화면도 그 언어로 나온다
            user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36",
        )
        page = ctx.new_page()
        page.set_default_timeout(180000)   # 무거운 3D 장면은 한 장 찍는 데도 오래 걸린다
        page.cdp = ctx.new_cdp_session(page)
        for pat in block or []:
            page.route(pat, lambda route: route.abort())
        for pat, handler in (routes or {}).items():
            page.route(pat, handler)
        page.clock.install()
        page.goto(url, wait_until="load", timeout=90000)
        page.wait_for_timeout(1500)
        for s in setup or []:  # 시작 버튼 등은 실시간으로
            _step(page, s, rng, page.wait_for_timeout)
        page.clock.pause_at(page.evaluate("Date.now()") + 50)

        class Done(Exception):
            pass

        recording = False

        def tick(ms):
            nonlocal n
            for _ in range(max(1, round(ms * FPS / 1000))):
                step = round((n + 1) * 1000 / FPS) - round(n * 1000 / FPS)  # 33·33·34ms 를 번갈아 (정수만 받는다)
                page.clock.run_for(step)
                if not recording:
                    continue
                page.screenshot(path=str(frames / f"f_{n:05d}.jpg"), type="jpeg", quality=92)
                n += 1
                if n >= total:
                    raise Done

        for st in prepare or []:  # 녹화하지 않고 게임 시간만 흘려보내는 준비 동작 (적이 다가올 때까지 기다리기 등)
            _step(page, st, rng, tick)
        if preflight:  # 찍기 전에 화면부터 확인하고, 통과한 그 화면에서 이어서 찍는다
            why = ""
            for attempt in range(5):
                tick(400)
                ok, why = preflight(page.screenshot(type="png"))
                print(f"[preflight] {attempt + 1}번째 화면: {'통과' if ok else '불합격 — ' + why}")
                if ok:
                    break
                for st in adjust or [{"do": "wait", "ms": 1500}]:
                    _step(page, st, rng, tick)
            else:
                ctx.close()
                browser.close()
                shutil.rmtree(frames, ignore_errors=True)
                raise Rejected(why)
        recording = True

        try:
            while True:
                for s in recipe or [{"do": "wait", "ms": 500}]:
                    _step(page, s, rng, tick)
        except Done:
            pass
        ctx.close()
        browser.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(FPS), "-i", str(frames / "f_%05d.jpg"),
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out_path)], check=True)
    shutil.rmtree(frames, ignore_errors=True)
    return out_path
