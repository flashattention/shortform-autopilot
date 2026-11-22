"""진행 상황을 대시보드로 보낸다. DASHBOARD_URL 과 PROGRESS_SECRET 이 없으면 아무것도 하지 않는다.

보내기는 뒤에서 따로 돌아서 녹화를 늦추지 않고, 실패해도 파이프라인은 그대로 간다.
"""
import atexit
import os
import queue
import threading
import time

import requests

_URL = (os.environ.get("DASHBOARD_URL") or "").rstrip("/")
_SECRET = os.environ.get("PROGRESS_SECRET") or ""
_q = queue.Queue()
_ctx = {}
_last_frame_sent = 0.0
_worker = None


def _run():
    while True:
        ev = _q.get()
        if ev is None:
            return
        try:
            requests.post(f"{_URL}/api/progress", json=ev, timeout=5,
                          headers={"Authorization": f"Bearer {_SECRET}"})
        except Exception:
            pass   # 대시보드가 꺼져 있어도 영상 만들기는 계속한다
        finally:
            _q.task_done()


def _flush():
    if _worker:
        deadline = time.time() + 8
        while not _q.empty() and time.time() < deadline:
            time.sleep(0.1)


def enabled():
    return bool(_URL and _SECRET)


def start(product, **ctx):
    """이번 실행의 공통 정보. 이후 emit 에 자동으로 붙는다."""
    global _worker
    _ctx.clear()
    _ctx.update(product=product, run_id=os.environ.get("GITHUB_RUN_ID", "local"),
                rounds_left=os.environ.get("ROUNDS_LEFT", ""), event=os.environ.get("GITHUB_EVENT_NAME", "local"),
                sent=0, failed=0, done=0, **ctx)
    if enabled() and not _worker:
        _worker = threading.Thread(target=_run, daemon=True)
        _worker.start()
        atexit.register(_flush)


def update(**kw):
    _ctx.update(kw)


def emit(stage, detail="", spec=None, **kw):
    """한 단계를 알린다. spec 을 주면 장면·언어를 같이 보낸다."""
    ev = dict(_ctx, stage=stage, detail=detail, **kw)
    if spec:
        ev.update(spec_id=spec.get("id"), scene=spec.get("scene"), lang=spec.get("lang"))
    print(f"[progress] {stage} {detail}".rstrip())
    if enabled() and _ctx.get("product"):
        _q.put(ev)


def frame(spec, n, total):
    """녹화 진행. 너무 자주 보내지 않게 3초에 한 번만."""
    global _last_frame_sent
    if time.time() - _last_frame_sent < 3 and n < total:
        return
    _last_frame_sent = time.time()
    ev = dict(_ctx, stage="녹화", detail=f"{n}/{total}장", frame=n, frames=total)
    if spec:
        ev.update(spec_id=spec.get("id"), scene=spec.get("scene"), lang=spec.get("lang"))
    if enabled() and _ctx.get("product"):
        _q.put(ev)
