"""실행 진입점.

  python -m pipeline.run produce [--product 제품] [--no-queue] [--seed N]
  python -m pipeline.run record --id 영상ID --views 조회수
"""
import argparse
import datetime
import json
import pathlib
import random
import sys
import traceback

from . import edit, plan, progress
from .common import OUT, load_history, load_state, load_yaml, save_state


def _footage(spec, need, pc, work, seed, cache, strict):
    """이 영상에 쓸 원본을 마련한다. 같은 장면은 한 번만 찍어 한국어·영어 편이 나눠 쓴다.
    찍기 전에 화면을 먼저 확인하고(strict), 찍은 뒤에는 멈춘 화면·빈 화면이 아닌지 본다. 떨어지면 한 번 다시 찍는다.
    (원본 목록, 앞에서 자를 초, 문구용 장면 3장) 또는 실패 이유(str)."""
    from . import qc
    src = spec["source"]
    if src["type"] == "clip":
        ok, why, _ = qc.check_footage(src["path"])
        if not ok:
            return f"클립 화면 검사 불합격: {why}"
        work.mkdir(parents=True, exist_ok=True)
        return [src["path"]], 0.0, qc.grab_frames(src["path"], work, (0.15, 0.5, 0.85), dur=spec["duration"])
    key = src["key"]
    if key not in cache:
        from . import capture
        trim = float(pc.get("trim_start", 0))
        work.mkdir(parents=True, exist_ok=True)
        pre = None
        if strict:
            pre = lambda png: qc.check_frame(png, spec["about"], spec["scene_desc"], spec["must_show"])
        storage = dict(pc.get("storage") or {}, **(src.get("storage") or {}))
        for k, (lo, hi) in (src.get("storage_random") or {}).items():   # 장면마다 무작위로 정하는 사이트 설정 (시작 시대 등)
            storage[k] = str(random.randint(lo, hi))
        if src.get("storage_random"):
            print(f"[produce] {key} 무작위 설정: {storage}")
        result = "녹화 실패"
        for attempt in range(2):
            progress.emit("녹화 준비", f"{attempt + 1}번째 시도" if attempt else "게임 여는 중", spec=spec)
            try:
                raw = capture.capture(src["url"], src.get("recipe"), need[key] + trim + 2, work / f"raw_{attempt}.mp4",
                                      seed=(seed or 0) + attempt, setup=src.get("setup"), block=pc.get("block"),
                                      locale=src.get("locale"), touch=pc.get("touch"), prepare=pc.get("prepare"),
                                      preflight=pre, adjust=pc.get("adjust"),
                                      fps=pc.get("fps"), storage=storage or None,
                                      on_event=lambda st, d: progress.emit(st, d, spec=spec),
                                      on_frame=lambda n, t: progress.frame(spec, n, t))
            except qc.Unavailable:
                raise
            except capture.Rejected as e:
                result = f"찍기 전 화면 확인 불합격: {e}"
                continue
            except Exception as e:
                traceback.print_exc()   # 원인을 로그에 남긴다
                result = f"녹화 실패: {type(e).__name__}: {str(e).splitlines()[0][:200]}"
                continue
            ok, why, stats = qc.check_footage(raw, start=trim, min_moving=pc.get("min_moving", 0.5))
            print(f"[qc] {key} 화면 검사 {'통과' if ok else '불합격: ' + why} {stats}")
            if ok:
                result = ([raw], trim, qc.grab_frames(raw, work, (0.15, 0.5, 0.85), start=trim, dur=need[key]))
                break
            result = f"화면 검사 불합격: {why}"
        cache[key] = result
    return cache[key]


def produce(args):
    import random
    from . import mailer, qc, review
    progress.start(args.product or "all")
    progress.emit("시작", "키 점검 중")
    strict = bool(qc._key()) or not args.no_queue   # 검수 없이는 아무것도 보내지 않는다
    if strict:
        try:
            qc.api_check()
        except qc.Unavailable as e:
            progress.emit("중단", f"검수를 할 수 없음 — {e}")
            print(f"::error::검수를 할 수 없어 영상을 만들지 않았습니다 — {e}")
            if not args.no_queue:
                mailer.send_alert(f"검수를 할 수 없어 이번에는 영상을 만들지 않았습니다.\n\n이유: {e}")
            sys.exit(1)
    cfg = load_yaml("products.yaml")
    specs = plan.make_specs(seed=args.seed, only_product=args.product)
    hist_name = f"history-{args.product}.json" if args.product else "history.json"
    history = load_state(hist_name, [])
    need = {}
    for s in specs:  # 같은 원본을 쓰는 영상 중 가장 긴 길이만큼 찍는다
        k = s["source"].get("key")
        if k:
            need[k] = max(need.get(k, 0), s["duration"])
    cache, sent, failed, used, rng = {}, [], [], {}, random.Random(args.seed)
    progress.update(total=len(specs))
    progress.emit("기획 완료", f"{len(specs)}편 예정 (편마다 문구 3가지)")

    def drop(spec, why):
        print(f"[produce] 제외 {spec['id']}: {why}")
        failed.append((spec, why))
        progress.update(failed=len(failed), done=len(failed) + done[0])
        progress.emit("제외", why, spec=spec)

    done = [0]
    for spec in specs:
        progress.emit("준비", spec["format"], spec=spec)
        try:
            work = OUT / spec["id"]
            work.mkdir(parents=True, exist_ok=True)
            pc = cfg["products"][spec["product"]].get("capture") or {}
            got = _footage(spec, need, pc, OUT / ("_raw_" + (spec["source"].get("key") or spec["id"])),
                           args.seed, cache, strict)
            if isinstance(got, str):
                drop(spec, got)
                continue
            sources, trim, frames = got
            progress.emit("문구 작성", "화면을 보고 세 가지로", spec=spec)
            copies = plan.write_copy(spec, frames, used.setdefault(spec["product"], set()), strict, rng)
            versions = []
            for i, copy in enumerate(copies, 1):   # 같은 화면에 문구만 바꿔 여러 편
                progress.emit("편집", f"문구 {i}/{len(copies)}", spec=spec)
                ver = dict(spec, **copy, id=f"{spec['id']}-v{i}")
                video = edit.render(ver, sources, work / f"v{i}" / "video.mp4", trim_start=trim)
                versions.append((ver, video))
                print(f"[produce] 완성: {ver['id']} — {ver['hook']}")
            if not args.no_queue:
                for ver, video in versions:   # 메일에 못 붙이는 큰 영상만 올려 두고 링크를 건다
                    ver["url"] = None
                    if pathlib.Path(video).stat().st_size > mailer.MAX_ATTACH:
                        try:
                            ver["url"] = review.upload(ver, video)
                        except Exception as e:
                            print(f"[produce] 큰 영상 올리기 실패: {e}")
                progress.emit("메일 발송", f"{len(versions)}편", spec=spec)
                ok_mail = mailer.send_versions(spec, versions)
                for ver, _ in versions:
                    entry = {k: ver[k] for k in ("id", "product", "format", "account", "lang", "scene", "hook", "clip")}
                    entry.update(status="sent" if ok_mail else "made", url=ver["url"],
                                 created=datetime.date.today().isoformat())
                    history.append(entry)
                save_state(hist_name, history)  # 중간에 끊겨도 보낸 것까지는 남게
            sent.extend(ver for ver, _ in versions)
            done[0] += 1
            progress.update(sent=len(sent), done=len(failed) + done[0])
            progress.emit("완료", f"{len(versions)}편 {'메일로 보냄' if not args.no_queue else '만듦'}", spec=spec,
                          hook=versions[0][0]["hook"])
        except qc.Unavailable as e:   # 찍기 전 화면 확인을 할 수 없으면 그 장면은 만들지 않는다
            drop(spec, f"화면 확인 불가로 제외: {e}")
        except Exception as e:
            traceback.print_exc()
            drop(spec, f"제작 중 오류: {str(e).splitlines()[0][:200]}")
    print(f"[produce] 보냄 {len(sent)} · 제외 {len(failed)}")
    progress.emit("끝", f"영상 {len(sent)}편 보냄 · 장면 {len(failed)}개 제외")
    for spec, why in failed:
        print(f"  제외 {spec['id']}: {why}")
    if not args.no_queue and failed:   # 빠진 영상이 있을 때만 요약 메일
        try:
            mailer.send_summary(sent, failed)
        except Exception:
            traceback.print_exc()
    if specs and not sent:
        sys.exit(1)


def record(args):
    """직접 올린 영상의 조회수를 적어 둡니다. 다음 기획에서 잘된 포맷을 더 자주 고릅니다."""
    history = load_history()
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
