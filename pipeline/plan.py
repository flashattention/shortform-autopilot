"""기획: 어떤 제품을 어떤 포맷으로 만들지 정하고 훅·캡션을 씁니다.

ANTHROPIC_API_KEY 가 있으면 Claude가 문구를 쓰고, 없으면 products.yaml 의 문구를 돌려 씁니다.
"""
import datetime
import json
import os
import random

import requests

from .common import CLIPS, load_state, load_yaml

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}


def unused_clips(product, history, prefix=None):
    d = CLIPS / product
    if not d.exists():
        return []
    used = {h.get("clip") for h in history}
    files = sorted(p for p in d.iterdir() if p.suffix.lower() in VIDEO_EXT)
    if prefix:
        files = [p for p in files if p.name.startswith(prefix)]
    return [p for p in files if str(p.relative_to(CLIPS)) not in used]


def pick_source(pid, product, fmt_id, fmt, history):
    """클립이 있으면 클립 우선, 없으면 자동 녹화. 둘 다 안 되면 None."""
    if fmt_id == "before_after":
        b, a = unused_clips(pid, history, "before_"), unused_clips(pid, history, "after_")
        return {"type": "before_after", "before": str(b[0]), "after": str(a[0])} if b and a else None
    if fmt_id == "bug_blooper":
        c = unused_clips(pid, history, "bug_")
        return {"type": "clip", "path": str(c[0])} if c else None
    c = [p for p in unused_clips(pid, history) if not p.name.startswith(("before_", "after_", "bug_"))]
    if c:
        return {"type": "clip", "path": str(c[0])}
    if fmt["needs"] == "capture_or_clip" and product.get("url"):
        return {"type": "capture", "url": product["url"]}
    return None


def format_scores(metrics):
    """포맷별 평균 조회수. 지표가 없으면 빈 dict."""
    agg = {}
    for m in metrics.values():
        if m.get("views") is not None:
            agg.setdefault(m["format"], []).append(m["views"])
    return {k: sum(v) / len(v) for k, v in agg.items()}


def choose(account, cfg, formats, history, metrics, rng, taken):
    last = {}
    for i, h in enumerate(history):
        if h["account"] == account:
            last[h["product"]] = i
    # 가장 오래 안 올린 제품부터
    pids = [p for p, v in cfg["products"].items() if account in v["accounts"] and p not in taken]
    pids.sort(key=lambda p: last.get(p, -1))
    scores = format_scores(metrics)
    for pid in pids:
        product = cfg["products"][pid]
        prev = next((h["format"] for h in reversed(history)
                     if h["product"] == pid and h["account"] == account), None)
        cands = [f for f in product["formats"] if account in formats[f]["accounts"] and f != prev]
        rng.shuffle(cands)
        # 80%는 성과 좋은 포맷 순, 20%는 탐색
        if scores and rng.random() < 0.8:
            cands.sort(key=lambda f: -scores.get(f, 0))
        for f in cands:
            src = pick_source(pid, product, f, formats[f], history)
            if src:
                return pid, f, src
    return None


def template_copy(pid, product, fmt_id, fmt, lang, history, rng):
    used = {h.get("hook") for h in history if h["product"] == pid}
    hooks = product["hooks"][lang]
    fresh = [h for h in hooks if h not in used] or hooks
    hook = rng.choice(fresh)
    cta = product["cta"][lang]
    tags = " ".join("#" + t for t in product["hashtags"][lang])
    name = product["name"][lang]
    link = product["link_text"].get(lang, "")
    if lang == "ko":
        ask = product.get("comment_ask", "어땠는지 댓글로 알려주세요")
        ig = f"{hook}\n\n{name} · {link}\n{ask}\n\n{tags}"
        title = f"{hook} | {name} #Shorts"
        tiktok = f"{hook} {tags}"
    else:
        ig = f"{hook}\n\n{name} · {link}\n\n{tags}"
        title = f"{hook} | {name} #Shorts"
        tiktok = f"{hook} {tags}"
    return {"hook": hook, "cta": cta, "captions": {"instagram": ig, "shorts": title[:100], "tiktok": tiktok}}


def claude_copy(pid, product, fmt_id, fmt, lang, account, history, metrics):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    recent = [h.get("hook") for h in history if h["product"] == pid][-8:]
    best = sorted((m for m in metrics.values() if m.get("views")), key=lambda m: -m["views"])[:5]
    prompt = f"""숏폼 영상 한 편의 문구를 써 주세요. JSON만 출력합니다.

제품: {json.dumps(product['name'], ensure_ascii=False)} / 안내 문구: {product['link_text'].get(lang, '')}
참고 훅(톤 참고용, 그대로 쓰지 말 것): {json.dumps(product['hooks'][lang], ensure_ascii=False)}
최근에 쓴 훅(겹치지 말 것): {json.dumps(recent, ensure_ascii=False)}
포맷: {fmt['label']} — {fmt['guide']}
계정: {account} / 언어: {'한국어' if lang == 'ko' else 'English'}
잘된 영상의 훅: {json.dumps([b.get('hook') for b in best], ensure_ascii=False)}

규칙:
- hook: 화면 위쪽에 크게 들어갈 한 문장. {'한국어 18자 안팎, 예능 자막 톤' if lang == 'ko' else 'max 9 words, plain and punchy'}
- cta: 화면 아래 한 줄. 과장 금지, 없는 기능·수치 지어내지 말 것
- instagram: 캡션 2~3줄 + 댓글로 답할 질문 하나 + 해시태그 5개
- shorts: 검색되는 제목 60자 이내, 끝에 #Shorts
- tiktok: 한 줄 + 해시태그 4~5개

출력 형식: {{"hook": "...", "cta": "...", "captions": {{"instagram": "...", "shorts": "...", "tiktok": "..."}}}}"""
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.environ.get("PLANNER_MODEL", "claude-haiku-5-5"), "max_tokens": 700,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        assert data["hook"] and data["cta"] and set(data["captions"]) >= {"instagram", "shorts", "tiktok"}
        return data
    except Exception as e:  # 문구 생성이 실패해도 파이프라인은 계속 돈다
        print(f"[plan] Claude 문구 생성 실패, 기본 문구 사용: {e}")
        return None


def make_specs(seed=None, only_account=None):
    cfg, formats = load_yaml("products.yaml"), load_yaml("formats.yaml")
    history = load_state("history.json", [])
    metrics = load_state("metrics.json", {})
    rng = random.Random(seed)
    today = datetime.date.today().strftime("%Y%m%d")
    specs, taken = [], set()
    for account, n in cfg["per_run"].items():
        if only_account and account != only_account:
            continue
        lang = cfg["accounts"][account]["lang"]
        for _ in range(n):
            got = choose(account, cfg, formats, history + specs, metrics, rng, taken)
            if not got:
                print(f"[plan] {account}: 만들 수 있는 소재가 없습니다 (url 또는 clips 확인)")
                break
            pid, fmt_id, src = got
            taken.add(pid)
            product, fmt = cfg["products"][pid], formats[fmt_id]
            copy = claude_copy(pid, product, fmt_id, fmt, lang, account, history, metrics) \
                or template_copy(pid, product, fmt_id, fmt, lang, history, rng)
            if fmt.get("series"):
                day = 1 + sum(1 for h in history if h["product"] == pid and h["format"] == fmt_id
                              and h["account"] == account)
                copy["hook"] = f"Day {day} · {copy['hook']}"
            lo, hi = fmt["duration"]
            spec = {
                "id": f"{today}-{pid}-{fmt_id}-{account}",
                "product": pid, "format": fmt_id, "account": account, "lang": lang,
                "platforms": cfg["accounts"][account]["platforms"],
                "auto_publish": cfg["accounts"][account]["auto_publish"],
                "duration": rng.randint(lo, hi), "hook_hold": fmt["hook_hold"],
                "source": src, "clip": None, **copy,
            }
            if src["type"] == "clip":
                spec["clip"] = str(pathlib_rel(src["path"]))
            specs.append(spec)
    return specs


def pathlib_rel(p):
    import pathlib
    return pathlib.Path(p).resolve().relative_to(CLIPS.resolve())
