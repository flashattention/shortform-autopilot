"""녹화 속도 점검: GitHub 서버에서 무거운 게임을 몇 장 찍어 한 장에 몇 초 걸리는지 잰다.

  python -m pipeline.bench            # 크롬(CHROME_PATH)으로
  CHROME_PATH= python -m pipeline.bench   # Playwright 기본 브라우저로
"""
import os
import tempfile
import time

from . import capture
from .common import load_yaml

SECONDS = 2


def main():
    cfg = load_yaml("products.yaml")["products"]
    browser = os.environ.get("CHROME_PATH") or "Playwright 기본 브라우저"
    for pid in ("mouse-father", "jelly-seoul-runner"):
        cap = cfg[pid]["capture"]
        scene = (cap.get("scenes") or [{}])[0]
        url = scene.get("url") or cap.get("url") or cfg[pid]["url"]
        fps = int(cap.get("fps") or 30)
        n = {"frames": 0, "t0": None}

        def on_frame(i, total):
            if n["t0"] is None:
                n["t0"] = time.time()
            n["frames"] = i

        t = time.time()
        try:
            capture.capture(url, scene.get("recipe") or cap.get("recipe"), SECONDS, tempfile.mktemp(suffix=".mp4"),
                            setup=scene.get("setup") or cap.get("setup"), block=cap.get("block"), fps=fps,
                            storage=cap.get("storage"), touch=cap.get("touch"), on_frame=on_frame)
            per = (time.time() - n["t0"]) / max(1, n["frames"] - 1) if n["t0"] else float("nan")
            print(f"[bench] {pid} · {browser}: 한 장 {per:.1f}초 ({n['frames']}장, 준비 포함 {time.time() - t:.0f}초) "
                  f"→ 15초 영상 녹화 예상 {per * fps * 17 / 60:.0f}분")
        except Exception as e:
            print(f"[bench] {pid} · {browser}: 실패 — {type(e).__name__}: {str(e).splitlines()[0][:160]} ({time.time() - t:.0f}초)")


if __name__ == "__main__":
    main()
