"""실행 진입점.

  python -m pipeline.run produce [--account kr|global] [--no-queue] [--seed N]
  python -m pipeline.run publish --issue N [--reject]
  python -m pipeline.run metrics
"""
import argparse
import datetime
import json
import sys
import tempfile
import traceback

from . import edit, plan
from .common import OUT, load_state, load_yaml, save_state


def produce(args):
    cfg = load_yaml("products.yaml")
    specs = plan.make_specs(seed=args.seed, only_account=args.account)
    history = load_state("history.json", [])
    ok = 0
    for spec in specs:
        try:
            work = OUT / spec["id"]
            work.mkdir(parents=True, exist_ok=True)
            pc = cfg["products"][spec["product"]].get("capture", {})
            src = spec["source"]
            trim = 0.0
            if src["type"] == "capture":
                from . import capture
                trim = float(pc.get("trim_start", 0))
                raw = capture.capture(src["url"], pc.get("recipe"), spec["duration"] + trim + 2,
                                      work / "raw.webm", seed=args.seed or 0)
                sources = [raw]
            elif src["type"] == "before_after":
                sources = [src["before"], src["after"]]
            else:
                sources = [src["path"]]
            video = edit.render(spec, sources, work / "video.mp4", trim_start=trim)
            (work / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[produce] 완성: {video}")
            entry = {k: spec[k] for k in ("id", "product", "format", "account", "hook", "clip")}
            entry.update(status="local", created=datetime.date.today().isoformat())
            if not args.no_queue:
                from . import review
                entry["issue"] = review.enqueue(spec, video)
                entry["status"] = "queued"
                print(f"[produce] 검수 이슈: {entry['issue']}")
                history.append(entry)
            ok += 1
        except Exception:
            print(f"[produce] 실패: {spec['id']}")
            traceback.print_exc()
    if not args.no_queue:
        save_state("history.json", history)
    if specs and not ok:
        sys.exit(1)


def publish(args):
    from . import instagram, review
    spec = review.read_issue(args.issue)
    history = load_state("history.json", [])
    entry = next((h for h in history if h["id"] == spec["id"]), None)
    if entry and entry.get("status") in ("published", "rejected"):
        print("이미 처리된 영상입니다.")
        return
    if args.reject:
        history = [h for h in history if h["id"] != spec["id"]]  # 클립·훅을 다시 쓸 수 있게 기록 삭제
        save_state("history.json", history)
        review.comment_and_close(args.issue, "반려했습니다. 이 소재는 다음 기획에 다시 쓸 수 있어요.", "not planned")
        return
    lines = []
    if "instagram" in spec["auto_publish"]:
        with tempfile.TemporaryDirectory() as d:
            path = review.download(spec["id"], d)
            media_id, link = instagram.publish_reel(path, spec["captions"]["instagram"],
                                                    public_url=review.asset_url(spec["id"]))
        lines.append(f"- 인스타 릴스 게시 완료: {link or media_id}")
        if entry:
            entry["media_id"] = media_id
    names = {"shorts": "유튜브 쇼츠", "tiktok": "틱톡"}
    for p in spec["platforms"]:
        if p not in spec["auto_publish"]:
            lines.append(f"- [ ] {names.get(p, p)}: 위 영상을 내려받아 직접 올리기 (캡션은 본문에서 복사)")
    if entry:
        entry.update(status="published", published=datetime.date.today().isoformat())
    save_state("history.json", history)
    review.comment_and_close(args.issue, "\n".join(lines))


def metrics(args):
    from . import instagram
    history = load_state("history.json", [])
    data = load_state("metrics.json", {})
    for h in history:
        if h.get("media_id"):
            m = instagram.insights(h["media_id"])
            data[h["id"]] = {"product": h["product"], "format": h["format"], "hook": h["hook"], **m}
    save_state("metrics.json", data)
    for k, v in sorted(data.items(), key=lambda kv: -(kv[1].get("views") or 0)):
        print(f"{v.get('views')}\t{v['format']}\t{v['hook']}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("produce")
    p.add_argument("--account", choices=["kr", "global"])
    p.add_argument("--no-queue", action="store_true", help="이슈를 만들지 않고 out/ 에만 저장")
    p.add_argument("--seed", type=int)
    p = sub.add_parser("publish")
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--reject", action="store_true")
    sub.add_parser("metrics")
    args = ap.parse_args()
    {"produce": produce, "publish": publish, "metrics": metrics}[args.cmd](args)


if __name__ == "__main__":
    main()
