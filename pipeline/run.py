"""실행 진입점.

  python -m pipeline.run produce [--product 제품] [--no-queue] [--seed N]
  python -m pipeline.run record --id 영상ID --views 조회수
"""
import argparse
import datetime
import json
import sys
import traceback

from . import edit, plan
from .common import OUT, load_state, load_yaml, save_state


def _footage(spec, need, pc, work, seed, cache):
    """이 영상에 쓸 원본을 마련한다. 같은 장면은 한 번만 찍어 한국어·영어 편이 나눠 쓴다.
    화면 검사에 떨어지면 한 번 다시 찍는다. (원본 목록, 앞에서 자를 초) 또는 실패 이유(str)."""
    from . import qc
    src = spec["source"]
    if src["type"] == "clip":
        ok, why, _ = qc.check_footage(src["path"])
        return ([src["path"]], 0.0) if ok else f"클립 화면 검사 불합격: {why}"
    key = src["key"]
    if key not in cache:
        from . import capture
        trim = float(pc.get("trim_start", 0))
        result = "녹화 실패"
        for attempt in range(2):
            try:
                raw = capture.capture(src["url"], src.get("recipe"), need[key] + trim + 2, work / f"raw_{attempt}.mp4",
                                      seed=(seed or 0) + attempt, setup=src.get("setup"), block=pc.get("block"),
                                      locale=src.get("locale"))
            except Exception as e:
                result = f"녹화 실패: {str(e).splitlines()[0][:200]}"
                continue
            ok, why, stats = qc.check_footage(raw, start=trim, min_moving=pc.get("min_moving", 0.5))
            print(f"[qc] {key} 화면 검사 {'통과' if ok else '불합격: ' + why} {stats}")
            if ok:
                result = ([raw], trim)
                break
            result = f"화면 검사 불합격: {why}"
        cache[key] = result
    return cache[key]


def produce(args):
    from . import mailer, qc, review
    cfg = load_yaml("products.yaml")
    specs = plan.make_specs(seed=args.seed, only_product=args.product)
    history = load_state("history.json", [])
    need = {}
    for s in specs:  # 같은 원본을 쓰는 영상 중 가장 긴 길이만큼 찍는다
        k = s["source"].get("key")
        if k:
            need[k] = max(need.get(k, 0), s["duration"])
    cache, sent, failed = {}, [], []
    for spec in specs:
        try:
            work = OUT / spec["id"]
            work.mkdir(parents=True, exist_ok=True)
            pc = cfg["products"][spec["product"]].get("capture") or {}
            got = _footage(spec, need, pc, OUT / ("_raw_" + (spec["source"].get("key") or spec["id"])), args.seed, cache)
            if isinstance(got, str):
                failed.append((spec, got))
                continue
            sources, trim = got
            video = edit.render(spec, sources, work / "video.mp4", trim_start=trim)
            ok, why = qc.check_content(video, spec, work)
            print(f"[qc] {spec['id']} 내용 검사: {'통과' if ok else ('건너뜀' if ok is None else '불합격')} {why}")
            if ok is False:
                failed.append((spec, f"내용 검사 불합격: {why}"))
                continue
            (work / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            entry = {k: spec[k] for k in ("id", "product", "format", "account", "lang", "scene", "hook", "clip")}
            entry.update(status="local", created=datetime.date.today().isoformat())
            if not args.no_queue:
                url = review.upload(spec, video)
                ok_mail = mailer.send_video(spec, video, url)
                entry.update(status="sent" if ok_mail else "made", url=url)
                history.append(entry)
                save_state("history.json", history)  # 중간에 끊겨도 보낸 것까지는 남게
            sent.append(spec)
            print(f"[produce] 완성: {video}")
        except Exception as e:
            traceback.print_exc()
            failed.append((spec, f"제작 중 오류: {str(e).splitlines()[0][:200]}"))
    print(f"[produce] 보냄 {len(sent)} · 제외 {len(failed)}")
    for spec, why in failed:
        print(f"  제외 {spec['id']}: {why}")
    if not args.no_queue:
        try:
            mailer.send_summary(sent, failed)
        except Exception:
            traceback.print_exc()
    if specs and not sent:
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
    p.add_argument("--product", help="이 제품만 만들기")
    p.add_argument("--no-queue", action="store_true", help="메일을 보내지 않고 out/ 에만 저장")
    p.add_argument("--seed", type=int)
    p = sub.add_parser("record")
    p.add_argument("--id", required=True)
    p.add_argument("--views", type=int, required=True)
    args = ap.parse_args()
    {"produce": produce, "record": record}[args.cmd](args)


if __name__ == "__main__":
    main()
