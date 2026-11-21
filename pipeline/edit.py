"""편집: 세로 1080x1920으로 맞추고 훅(위)·CTA(아래) 자막을 얹어 mp4로 내보냅니다."""
import os
import pathlib

from PIL import Image, ImageDraw, ImageFont

from .common import ROOT, probe, run

W, H = 1080, 1920
FONT_CANDIDATES = [
    os.environ.get("FONT_PATH", ""),
    str(ROOT / "assets" / "font.ttf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]


def _font(size):
    for f in FONT_CANDIDATES:
        if f and pathlib.Path(f).exists():
            # NotoSansCJK .ttc 에서 한국어 글꼴은 1번
            idx = 1 if f.endswith("NotoSansCJK-Bold.ttc") else 0
            return ImageFont.truetype(f, size, index=idx)
    raise FileNotFoundError("한글 글꼴이 없습니다. assets/font.ttf 를 넣거나 FONT_PATH 를 지정하세요.")


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    tokens = text.split(" ")
    for tok in tokens:
        trial = (cur + " " + tok).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = tok
        while draw.textlength(cur, font=font) > max_w:  # 띄어쓰기 없는 긴 단어
            for i in range(len(cur), 0, -1):
                if draw.textlength(cur[:i], font=font) <= max_w:
                    lines.append(cur[:i])
                    cur = cur[i:]
                    break
    if cur:
        lines.append(cur)
    return lines


def text_png(text, path, y_center, size, box=False):
    """투명 배경 1080x1920 PNG 에 가운데 정렬 자막을 그림. 플랫폼 UI에 가리지 않는 안전 구역 기준."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = _font(size)
    lines = _wrap(d, text, font, W - 200)
    while len(lines) > 3 and size > 44:  # 너무 길면 글자를 줄임
        size -= 6
        font = _font(size)
        lines = _wrap(d, text, font, W - 200)
    lh = int(size * 1.3)
    y = y_center - lh * len(lines) // 2
    for line in lines:
        w = d.textlength(line, font=font)
        x = (W - w) // 2
        if box:
            d.rounded_rectangle([x - 28, y - 6, x + w + 28, y + lh - 2], radius=22, fill=(255, 255, 255, 235))
            d.text((x, y), line, font=font, fill=(20, 20, 20, 255))
        else:
            d.text((x, y), line, font=font, fill=(255, 255, 255, 255),
                   stroke_width=max(4, size // 10), stroke_fill=(0, 0, 0, 255))
        y += lh
    img.save(path)
    return path


def _fit(label_in, label_out, landscape):
    if landscape:  # 가로 영상은 흐린 배경 위에 가운데로
        return (f"[{label_in}]split[a][b];"
                f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2[bg];"
                f"[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,setsar=1[{label_out}]")
    return (f"[{label_in}]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},fps=30,setsar=1[{label_out}]")


def render(spec, sources, out_path, trim_start=0.0):
    """sources: 영상 파일 1개(일반) 또는 2개(비포·애프터)."""
    out_path = pathlib.Path(out_path)
    work = out_path.parent
    work.mkdir(parents=True, exist_ok=True)
    dur = float(spec["duration"])
    hook = text_png(spec["hook"], work / "hook.png", 420, 84)
    cta = text_png(spec["cta"], work / "cta.png", 1400, 60, box=True)

    cmd, filt = ["ffmpeg", "-y", "-v", "error"], []
    if len(sources) == 2:
        half = dur / 2
        for s in sources:
            _, _, d = probe(s)
            cmd += ["-ss", str(max(0, min(trim_start, d - half))), "-t", str(half), "-i", str(s)]
        for i, s in enumerate(sources):
            w, h, _ = probe(s)
            filt.append(_fit(f"{i}:v", f"s{i}", w > h))
        filt.append("[s0][s1]concat=n=2:v=1:a=0[base]")
        n = 2
    else:
        src = sources[0]
        w, h, d = probe(src)
        start = max(0, min(trim_start, d - dur)) if d else 0
        if d and d - start < dur:
            dur = max(3.0, d - start)
        cmd += ["-ss", str(start), "-t", str(dur), "-i", str(src)]
        filt.append(_fit("0:v", "base", w > h))
        n = 1
    cmd += ["-loop", "1", "-t", str(dur), "-i", str(hook), "-loop", "1", "-t", str(dur), "-i", str(cta)]
    hook_end = dur if spec.get("hook_hold") == "full" else min(3.0, dur)
    cta_start = round(dur * 0.4, 2)
    filt.append(f"[base][{n}:v]overlay=0:0:enable='lte(t,{hook_end})'[v1]")
    filt.append(f"[v1][{n + 1}:v]overlay=0:0:enable='gte(t,{cta_start})'[v]")

    bgm_dir = ROOT / "assets" / "bgm"
    bgm = sorted(bgm_dir.glob("*.mp3")) if bgm_dir.exists() else []
    if bgm:
        cmd += ["-stream_loop", "-1", "-i", str(bgm[hash(spec["id"]) % len(bgm)])]
        filt.append(f"[{n + 2}:a]volume=0.6,afade=t=out:st={max(0, dur - 1)}:d=1[a]")
    else:  # 무음 트랙. 소리 없는 파일은 일부 플랫폼에서 거절됨
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        filt.append(f"[{n + 2}:a]anull[a]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[v]", "-map", "[a]", "-t", str(dur),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_path)]
    run(cmd)
    return out_path
