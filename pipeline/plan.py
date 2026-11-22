"""기획: 제품마다 장면을 고르고, 장면 하나로 한국어 1편 + 영어 1편의 포맷과 문구를 정합니다.

문구는 원본을 찍은 뒤, Claude가 찍힌 화면을 직접 보고 씁니다 (write_copy).
"""
import datetime
import json
import random

from .common import CLIPS, load_state, load_yaml

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
SPECIAL = ("before_", "after_", "bug_")


def unused_clips(pid, history):
    d = CLIPS / pid
    if not d.exists():
        return []
    used = {h.get("clip") for h in history}
    files = sorted(p for p in d.iterdir() if p.suffix.lower() in VIDEO_EXT and not p.name.startswith(SPECIAL))
    return [p for p in files if str(p.relative_to(CLIPS)) not in used]


def pick_sources(pid, product, history, n, rng):
    """직접 찍은 클립을 먼저 쓰고, 모자라면 가장 오래 안 쓴 장면부터 고른다."""
    out = []
    for c in unused_clips(pid, history)[:n]:
        out.append({"type": "clip", "path": str(c), "clip": str(c.relative_to(CLIPS)), "scene": c.stem,
                    "desc": {"ko": "직접 녹화한 플레이 영상", "en": "recorded gameplay footage"}})
    cap = product.get("capture") or {}
    scenes = list(cap.get("scenes") or [])
    last = {h.get("scene"): i for i, h in enumerate(history) if h["product"] == pid}
    rng.shuffle(scenes)
    scenes.sort(key=lambda s: last.get(s["id"], -1))
    for s in scenes[: max(0, n - len(out))]:
        out.append({"type": "capture", "scene": s["id"], "desc": s["desc"], "clip": None,
                    "url": s.get("url") or cap.get("url") or product["url"], "setup": s.get("setup") or cap.get("setup"),
                    "recipe": s.get("recipe") or cap.get("recipe")})
    return out


def format_scores(metrics):
    agg = {}
    for m in metrics.values():
        if m.get("views") is not None:
            agg.setdefault(m["format"], []).append(m["views"])
    return {k: sum(v) / len(v) for k, v in agg.items()}


def pick_format(pid, product, formats, account, history, taken, scores, rng):
    """직접 찍은 특수 클립이 필요한 포맷은 빼고, 이번 실행에서 아직 안 쓴 포맷을 고른다."""
    prev = next((h["format"] for h in reversed(history)
                 if h["product"] == pid and h["account"] == account), None)
    cands = [f for f in product["formats"]
             if account in formats[f]["accounts"] and formats[f]["needs"] == "capture_or_clip"]
    fresh = [f for f in cands if f not in taken and f != prev] or [f for f in cands if f not in taken] or cands
    rng.shuffle(fresh)
    if scores and rng.random() < 0.8:  # 80%는 성과 좋은 포맷 순, 20%는 탐색
        fresh.sort(key=lambda f: -scores.get(f, 0))
    return fresh[0]


def template_copy(pid, product, lang, history, used, rng):
    seen = {h.get("hook") for h in history if h["product"] == pid} | used
    hooks = product["hooks"][lang]
    hook = rng.choice([h for h in hooks if h not in seen] or hooks)
    tags = " ".join("#" + t for t in product["hashtags"][lang])
    name, link = product["name"][lang], product["link_text"].get(lang, "")
    ask = product.get("comment_ask", "어땠는지 댓글로 알려주세요") if lang == "ko" else "What would you do? Tell me below"
    return {"hook": hook, "cta": product["cta"][lang],
            "captions": {"instagram": f"{hook}\n\n{name} · {link}\n{ask}\n\n{tags}",
                         "shorts": f"{hook} | {name} #Shorts"[:100], "tiktok": f"{hook} {tags}"}}


def claude_copy(spec, product, fmt, frames, recent, best):
    """찍힌 화면(frames)을 직접 보고 문구를 쓴다. 화면에 없는 이야기를 못 하게 하기 위함."""
    from . import qc
    lang = spec["lang"]
    ko = lang == "ko"
    prompt = f"""위 이미지는 숏폼 영상에 실제로 들어갈 화면 3장(시간 순서)입니다. 이 화면에 붙일 문구를 써 주세요. JSON만 출력합니다.

제품: {product['name'][lang]} — {product['about'][lang]}
장면: {spec['scene_desc']}
포맷: {fmt['label']} — {fmt['guide']}
언어와 시청자: {'한국어. 한국 인스타 릴스·쇼츠. 큰 예능 자막, 공감, 반말 톤' if ko else 'English. Global TikTok and Shorts. Plain, punchy, first-second hook'}
안내 문구: {product['link_text'].get(lang, '')}
톤 참고용 훅(그대로 쓰지 말 것): {json.dumps(product['hooks'][lang], ensure_ascii=False)}
이미 쓴 훅(겹치거나 비슷하면 안 됨): {json.dumps(recent, ensure_ascii=False)}
잘된 영상의 훅: {json.dumps(best, ensure_ascii=False)}

규칙:
- 먼저 이미지에 실제로 무엇이 보이는지 확인하고, 보이는 것만 말할 것. 화면에 적이 없으면 싸운다고 쓰지 말 것
- 없는 기능·수치·순위·수상·사용자 수를 지어내지 말 것
- hook: 화면 위에 크게 들어갈 한 문장. {'한국어 20자 안팎' if ko else 'max 9 words'}. 이 화면에만 맞는 구체적인 내용으로
- cta: 화면 아래 한 줄. {'한국어 16자 안팎' if ko else 'max 6 words'}
- instagram: 캡션 2~3줄 + 댓글로 답할 질문 하나 + 해시태그 5개
- shorts: 검색되는 제목 60자 이내, 끝에 #Shorts
- tiktok: 한 줄 + 해시태그 4~5개
- 모든 문구는 {'한국어' if ko else 'English'}로

출력 형식: {{"seen": "이미지에 보이는 것 한 문장", "hook": "...", "cta": "...", "captions": {{"instagram": "...", "shorts": "...", "tiktok": "..."}}}}"""
    data = qc._ask([qc._img(f) for f in frames] + [{"type": "text", "text": prompt}], max_tokens=900)
    if not (data.get("hook") and data.get("cta") and set(data.get("captions") or {}) >= {"instagram", "shorts", "tiktok"}):
        raise qc.Unavailable("문구 응답에 빠진 항목이 있음")
    return {k: data[k] for k in ("hook", "cta", "captions")}


def write_copy(spec, frames, used, use_claude, rng):
    """원본을 찍은 뒤에 부른다. spec 에 hook·cta·captions 를 채운다."""
    cfg, formats = load_yaml("products.yaml"), load_yaml("formats.yaml")
    history, metrics = load_state("history.json", []), load_state("metrics.json", {})
    pid, product, fmt = spec["product"], cfg["products"][spec["product"]], formats[spec["format"]]
    if use_claude:
        recent = [h.get("hook") for h in history if h["product"] == pid][-20:] + sorted(used)
        best = [m.get("hook") for m in sorted((m for m in metrics.values() if m.get("views")),
                                               key=lambda m: -m["views"])[:5]]
        copy = claude_copy(spec, product, fmt, frames, recent, best)
    else:
        copy = template_copy(pid, product, spec["lang"], history, used, rng)
    used.add(copy["hook"])
    if fmt.get("series"):
        day = 1 + sum(1 for h in history if h["product"] == pid and h["format"] == spec["format"]
                      and h["account"] == spec["account"])
        copy["hook"] = f"Day {day} · {copy['hook']}"
    spec.update(copy)


def make_specs(seed=None, only_product=None):
    cfg, formats = load_yaml("products.yaml"), load_yaml("formats.yaml")
    history = load_state("history.json", [])
    scores = format_scores(load_state("metrics.json", {}))
    rng = random.Random(seed)
    today = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    specs = []
    for pid, product in cfg["products"].items():
        if only_product and pid != only_product:
            continue
        sources = pick_sources(pid, product, history, cfg["scenes_per_product"], rng)
        if not sources:
            print(f"[plan] {pid}: 찍을 장면도 클립도 없어 건너뜁니다")
            continue
        cap = product.get("capture") or {}
        i18n = bool(cap.get("i18n"))
        taken = {lang: set() for lang in cfg["langs"]}
        for src in sources:
            for lang, lc in cfg["langs"].items():
                account = lc["account"]
                fmt_id = pick_format(pid, product, formats, account, history, taken[lang], scores, rng)
                taken[lang].add(fmt_id)
                fmt = formats[fmt_id]
                lo, hi = fmt["duration"]
                source = dict(src)
                if src["type"] == "capture":
                    source["locale"] = {"ko": "ko-KR", "en": "en-US"}[lang] if i18n else "ko-KR"
                    source["key"] = f"{pid}-{src['scene']}-{source['locale']}"  # 같은 key 는 한 번만 찍어 나눠 쓴다
                specs.append({
                    "id": f"{today}-{pid}-{src['scene']}-{lang}",
                    "product": pid, "format": fmt_id, "account": account, "lang": lang,
                    "scene": src["scene"], "scene_desc": src["desc"][lang], "about": product["about"][lang],
                    "platforms": lc["platforms"], "duration": rng.randint(lo, hi), "hook_hold": fmt["hook_hold"],
                    "must_show": cap.get("must_show", ""),
                    "source": source, "clip": src.get("clip"), "hook": None, "cta": None, "captions": None,
                })
    return specs
