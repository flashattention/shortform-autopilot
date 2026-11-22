"""검수: 보내기 전에 영상이 쓸 만한지 두 번 확인합니다.

1. 화면 검사(항상): 원본 녹화가 멈춘 화면·빈 화면이 아닌지 숫자로 확인
2. 내용 검사(ANTHROPIC_API_KEY 가 있을 때): 완성본 장면을 Claude가 보고 실제 플레이·사용 화면인지, 자막이 읽히는지, 훅이 화면과 맞는지 판단
"""
import base64
import json
import os
import pathlib
import re
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


class Unavailable(Exception):
    """검수용 Claude 호출을 쓸 수 없음. 검수 없이 보내지 않기 위해 호출한 쪽에서 멈춘다."""


def _key():
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def _ask(content, max_tokens=1024):
    """Claude에게 묻고 답 글을 받는다. 호출이 안 되거나 답이 비면 Unavailable."""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": _key(), "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.environ.get("QC_MODEL") or os.environ.get("PLANNER_MODEL") or "claude-haiku-5-5",
                  "max_tokens": max(max_tokens, 1024), "messages": [{"role": "user", "content": content}]},
            timeout=180,
        )
    except requests.RequestException as e:
        raise Unavailable(f"Claude API 연결 실패: {e}")
    if r.status_code == 401:
        raise Unavailable("Claude API 키가 거절됐습니다(401). ANTHROPIC_API_KEY Secret 값을 다시 확인하세요.")
    if r.status_code >= 400:
        raise Unavailable(f"Claude API 오류 {r.status_code}: {r.text[:300]}")
    try:
        body = r.json()
        blocks = body.get("content") or []
        # 응답 맨 앞에 글이 아닌 블록(생각 과정 등)이 올 수 있다. 글 블록만 모아서 읽는다
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")
    except Exception as e:
        raise Unavailable(f"Claude 응답을 읽을 수 없음: {e}")
    if not text.strip():
        kinds = [b.get("type") for b in blocks if isinstance(b, dict)]
        raise Unavailable(f"Claude 응답에 글이 없음 (블록 종류 {kinds}, stop_reason {body.get('stop_reason')})")
    return text


VERDICT_FORMAT = """아래 두 줄 형식으로만 답하세요. 다른 말은 쓰지 마세요.
VERDICT: PASS 또는 FAIL
REASON: 화면에 무엇이 보이는지 한 문장"""


def _verdict(text):
    """'VERDICT: PASS/FAIL' 과 'REASON: ...' 을 읽는다. JSON 은 답 안의 따옴표 하나로도 깨져서 쓰지 않는다."""
    m = re.search(r"VERDICT\s*[:：]\s*\**\s*(PASS|FAIL)", text, re.I)
    if not m:
        raise Unavailable(f"판정을 읽을 수 없음: {text[:160]!r}")
    r = re.search(r"REASON\s*[:：]\s*(.+)", text, re.I | re.S)
    return m.group(1).upper() == "PASS", (r.group(1).strip().splitlines()[0] if r else "")


def api_check():
    """실행을 시작하기 전에, 실제 검수와 같은 형태(이미지 + 질문)로 한 번 물어봐서 끝까지 동작하는지 확인한다."""
    if not _key():
        raise Unavailable("ANTHROPIC_API_KEY Secret 이 비어 있습니다.")
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (40, 120, 200)).save(buf, "PNG")
    _verdict(_ask([_img(buf.getvalue(), "image/png"),
                   {"type": "text", "text": "이 이미지가 한 가지 색으로 채워져 있으면 PASS 입니다.\n" + VERDICT_FORMAT}]))


def _img(data, media="image/jpeg"):
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": base64.b64encode(data).decode()}}


def check_frame(png, about, scene_desc, must_show):
    """찍기 전 화면 확인. 이 화면에서 바로 녹화를 시작해도 되는지 판단한다."""
    prompt = f"""게임·사이트를 자동으로 녹화하려고 합니다. 지금 화면에서 바로 녹화를 시작해도 되는지 봐 주세요.

제품: {about}
찍으려는 장면: {scene_desc}
이 화면에 반드시 보여야 하는 것: {must_show}

위 조건이 화면에 실제로 보일 때만 합격입니다. 하늘·땅·벽만 보이거나, 메뉴·로딩·결과·오류 화면이면 불합격입니다.
{VERDICT_FORMAT}"""
    return _verdict(_ask([_img(png, "image/png"), {"type": "text", "text": prompt}]))


def grab_frames(video, work, fracs, start=0.0, dur=None, width=432):
    _, _, total = probe(video)
    dur = dur or max(0.5, total - start)
    out = []
    for i, frac in enumerate(fracs):
        f = pathlib.Path(work) / f"frame_{i}.jpg"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start + dur * frac), "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={width}:-2", "-q:v", "4", str(f)], check=True)
        out.append(f.read_bytes())
    return out


def check_content(video, spec, work):
    """완성본 검수. (통과, 이유). 호출이 안 되면 Unavailable — 검수 못 한 영상은 보내지 않는다."""
    images = [_img(b) for b in grab_frames(video, work, (0.08, 0.3, 0.55, 0.8, 0.95))]
    prompt = f"""숏폼 영상에서 뽑은 장면 5장(시간 순서)입니다. 올려도 되는지 엄격하게 검수해 주세요.

제품: {spec['about']}
찍으려던 장면: {spec['scene_desc']}
화면에 반드시 보여야 하는 것: {spec.get('must_show') or '실제 플레이·사용 화면'}
화면 위 자막(훅): {spec['hook']}
화면 아래 자막: {spec['cta']}

아래 중 하나라도 해당하면 불합격입니다.
- '반드시 보여야 하는 것'이 5장 중 3장 이상에서 보이지 않는다 (하늘·땅만 보임, 적이 없음, 캐릭터가 안 보임 등)
- 5장 중 2장 이상이 메뉴·소개 페이지·로딩·오류·결과 화면이다
- 훅이 말하는 내용이 화면에 실제로 보이지 않는다 (싸운다고 했는데 적이 없음, 다른 장소 이야기 등)
- 자막이 잘리거나, 글자가 깨지거나, 배경에 묻혀 읽기 어렵다
- 확인할 수 없는 수치·순위·수상 같은 과장이 있다

{VERDICT_FORMAT}"""
    return _verdict(_ask(images + [{"type": "text", "text": prompt}]))
