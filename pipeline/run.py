"""실행 진입점.

  python -m pipeline.run produce [--account kr|global] [--no-queue] [--seed N]
  python -m pipeline.run record --id 영상ID --views 조회수
"""
import argparse
import datetime
import json
import sys
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
                from . import mailer, review
                url = review.upload(spec, video)
                sent = mailer.send_video(spec, video, url)
                entry.update(status="sent" if sent else "made", url=url)
                history.append(entry)
            ok += 1
        except Exception:
            print(f"[produce] 실패: {spec['id']}")
            traceback.print_exc()
    if not args.no_queue:
        save_state("history.json", history)
    if specs and not ok:
        sys.exit(1)


def record(args):
    """직접 올린 영상의 조회수를 적어 둡니다. 다음 기획에서 잘된 포맷을 더 자주 고릅니다."""
    history = load_state("history.json", [])
    h = next((x for x in history if x["id"] == args.id), None)
    if not h:
        sys.exit(f"영상 ID를 찾을 수 없습니다: {args.id}")
    data = load_state("metrics.json", {})
    data[h["id"]] = {"product": h["product"], "format": h["format"], "hook": h["hook"], "views": args.views}
    save_state("metrics.json", data)
    for k, m in sorted(data.items(), key=lambda kv: -(kv[1].get("views") or 0)):
        print(f"{m.get('views')}\t{m['format']}\t{m['hook']}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("produce")
    p.add_argument("--account", choices=["kr", "global"])
    p.add_argument("--no-queue", action="store_true", help="메일을 보내지 않고 out/ 에만 저장")
    p.add_argument("--seed", type=int)
    p = sub.add_parser("record")
    p.add_argument("--id", required=True)
    p.add_argument("--views", type=int, required=True)
    args = ap.parse_args()
    {"produce": produce, "record": record}[args.cmd](args)


if __name__ == "__main__":
    main()
