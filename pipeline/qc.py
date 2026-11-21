"""검수: 보내기 전에 영상이 쓸 만한지 두 번 확인합니다.

1. 화면 검사(항상): 원본 녹화가 멈춘 화면·빈 화면이 아닌지 숫자로 확인
2. 내용 검사(ANTHROPIC_API_KEY 가 있을 때): 완성본 장면을 Claude가 보고 실제 플레이·사용 화면인지, 자막이 읽히는지, 훅이 화면과 맞는지 판단
"""
import base64
import json
import os
import pathlib
import subprocess

import requests

from .common import probe

SW, SH = 54, 96


def _gray_frames(path, start, dur, every=1.0):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(dur), "-i", str(path),
                        "-vf", f"fps={1 / every},scale={SW}:{SH},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    n = SW * SH
    return [r.stdout[i:i + n] for i in range(0, len(r.stdout) - n + 1, n)]


def check_footage(path, start=0.0, dur=None, min_moving=0.5):
    """원본 녹화 검사. (통과 여부, 이유, 수치) 를 돌려준다."""
    _, _, total = probe(path)
    dur = dur or max(1.0, total - start)
    frames = _gray_frames(path, start, dur)
    if len(frames) < 3:
        return False, "녹화가 너무 짧음", {}
    diffs = [sum(abs(a - b) for a, b in zip(f1, f2)) / len(f1) for f1, f2 in zip(frames, frames[1:])]
    moving = sum(1 for d in diffs if d > 1.0) / len(diffs)
    mid = frames[len(frames) // 2]
    mean = sum(mid) / len(mid)
    spread = (sum((v - mean) ** 2 for v in mid) / len(mid)) ** 0.5
    stats = {"moving": round(moving, 2), "spread": round(spread, 1)}
    if spread < 6:
        return False, "화면이 거의 한 가지 색(빈 화면·로딩 화면으로 보임)", stats
    if moving < min_moving:
        return False, "화면이 거의 움직이지 않음(멈춘 화면·첫 화면으로 보임)", stats
    return True, "", stats


def check_content(video, spec, work):
    """완성본 내용 검사. 키가 없거나 호출이 실패하면 (None, 이유) — 화면 검사 결과만으로 보낸다."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None, "API 키 없음"
    _, _, dur = probe(video)
    images = []
    for i, frac in enumerate((0.15, 0.5, 0.85)):
        out = pathlib.Path(work) / f"qc_{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(dur * frac), "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=432:-2", "-q:v", "4", str(out)], check=True)
        images.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                   "data": base64.b64encode(out.read_bytes()).decode()}})
    prompt = f"""숏폼 영상에서 뽑은 장면 3장(앞·중간·뒤)입니다. 올려도 되는지 검수해 주세요.

제품: {spec['about']}
나와야 하는 화면: {spec['scene_desc']}
화면 위 자막(훅): {spec['hook']}
화면 아래 자막: {spec['cta']}

아래 중 하나라도 해당하면 불합격입니다.
- 3장 중 2장 이상이 실제 플레이·사용 화면이 아니라 메뉴·소개 페이지·로딩·오류·결과 화면이다
- 자막이 잘리거나, 글자가 깨지거나, 배경에 묻혀 읽기 어렵다
- 훅이 화면에 보이는 내용과 분명히 어긋난다 (다른 게임·다른 장면 이야기)
- 훅이나 자막에 확인할 수 없는 수치·순위·수상 같은 과장이 있다

사소한 흠은 합격으로 둡니다. JSON만 출력: {{"ok": true 또는 false, "reason": "한 문장"}}"""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.environ.get("QC_MODEL") or os.environ.get("PLANNER_MODEL") or "claude-haiku-5-5",
                  "max_tokens": 300, "messages": [{"role": "user", "content": images + [{"type": "text", "text": prompt}]}]},
            timeout=120,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return bool(data["ok"]), str(data.get("reason", ""))
    except Exception as e:
        return None, f"내용 검사 호출 실패: {e}"
