"""점검: 실제 Claude 키로 화면 확인·문구·편집 단계를 끝까지 돌려 본다. (녹화는 로컬에서 확인하고, 여기서는 미리 찍어 둔 샘플을 쓴다)

코드를 올릴 때마다 Actions 에서 자동으로 돈다. 1~2분이면 끝나므로, 1시간짜리 실행 전에 문제를 잡는다.
  python -m pipeline.selftest
"""
import random
import subprocess
import sys
import tempfile
import pathlib

from . import edit, plan, qc
from .common import ROOT, load_yaml

SAMPLES = {"dream-runner": "dream", "capyzombie": "farm-retreat"}


def main():
    cfg, formats = load_yaml("products.yaml"), load_yaml("formats.yaml")
    work = pathlib.Path(tempfile.mkdtemp())
    bad = []

    def step(name, fn):
        try:
            out = fn()
            print(f"  ✓ {name}: {out}")
            return out
        except Exception as e:
            print(f"  ✗ {name}: {type(e).__name__}: {e}")
            bad.append(name)
            return None

    print("[1] 키와 응답 형식")
    step("api_check", lambda: qc.api_check() or "통과")

    for pid, scene_id in SAMPLES.items():
        product = cfg["products"][pid]
        cap = product["capture"]
        scene = next(s for s in cap["scenes"] if s["id"] == scene_id)
        clip = ROOT / "selftest" / f"{pid}.mp4"
        print(f"[2] {pid}: 찍기 전 화면 확인")
        png = work / f"{pid}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "3", "-i", str(clip), "-frames:v", "1", str(png)], check=True)
        v = step("올바른 화면 → 통과해야 함", lambda: qc.check_frame(png.read_bytes(), product["about"]["ko"],
                                                              scene["desc"]["ko"], cap["must_show"]))
        if v and not v[0]:
            bad.append(f"{pid} 올바른 화면이 불합격됨")
        frames = qc.grab_frames(clip, work, (0.15, 0.5, 0.85))
        for lang, lc in cfg["langs"].items():
            print(f"[3] {pid} {lang}: 문구 세 가지 → 편집")
            spec = {"id": f"selftest-{pid}-{lang}", "product": pid, "format": "question_hook", "account": lc["account"],
                    "lang": lang, "scene": scene_id, "scene_desc": scene["desc"][lang], "about": product["about"][lang],
                    "must_show": cap["must_show"], "platforms": lc["platforms"], "duration": 8, "hook_hold": "full"}
            copies = plan.write_copy(spec, frames, set(), True, random.Random(0))
            if not copies:
                continue
            for i, c in enumerate(copies, 1):
                print(f"      {i}. {c['hook']}  /  {c['cta']}  (인스타 캡션 {len(c['captions']['instagram'])}자)")
            if len(copies) < 2:
                bad.append(f"{pid} {lang} 문구 버전이 {len(copies)}개뿐")
            step("편집", lambda: edit.render(dict(spec, **copies[0]), [clip], work / spec["id"] / "video.mp4"))

    print("[4] 엉뚱한 화면을 걸러내는지 (카피좀비 자리에 다른 사이트 화면)")
    cz = cfg["products"]["capyzombie"]
    v = step("엉뚱한 화면 → 불합격해야 함", lambda: qc.check_frame((ROOT / "selftest" / "wrong-screen.png").read_bytes(),
                                                           cz["about"]["ko"], "좀비와 싸우는 화면", cz["capture"]["must_show"]))
    if v and v[0]:
        bad.append("엉뚱한 화면이 통과됨")

    print("\n결과:", "전부 통과" if not bad else f"문제 {len(bad)}건 — {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
