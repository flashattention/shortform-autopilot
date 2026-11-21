"""인스타그램 릴스 게시와 지표 수집 (Instagram Platform Content Publishing API).

필요한 값: IG_USER_ID, IG_ACCESS_TOKEN (권한 instagram_content_publish 포함)
- 기본은 파일을 직접 올리는 resumable 업로드 (Facebook 로그인 방식 앱, graph.facebook.com).
- IG_UPLOAD_MODE=url 로 두면 공개 주소(video_url)를 넘기는 표준 방식. 레포가 공개여야 합니다.
- Instagram 로그인 방식 앱이면 IG_API_BASE=https://graph.instagram.com 과 IG_UPLOAD_MODE=url 을 함께 쓰세요.
"""
import os
import pathlib
import time

import requests


def _base():
    return (os.environ.get("IG_API_BASE") or "https://graph.facebook.com").rstrip("/")


def _check(r):
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram API 오류 {r.status_code}: {r.text[:500]}")
    return r.json()


def publish_reel(video_path, caption, public_url=None):
    uid, tok = os.environ["IG_USER_ID"], os.environ["IG_ACCESS_TOKEN"]
    auth = {"Authorization": f"Bearer {tok}"}
    if os.environ.get("IG_UPLOAD_MODE") == "url":
        c = _check(requests.post(f"{_base()}/{uid}/media", headers=auth, timeout=120,
                                 data={"media_type": "REELS", "video_url": public_url, "caption": caption}))
    else:
        c = _check(requests.post(f"{_base()}/{uid}/media", params={"upload_type": "resumable"},
                                 headers=auth, json={"media_type": "REELS", "caption": caption}, timeout=120))
        data = pathlib.Path(video_path).read_bytes()
        _check(requests.post(c["uri"], data=data, timeout=600, headers={
            "Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(data))}))
    cid = c["id"]
    for _ in range(60):  # 처리 완료까지 최대 10분 대기
        s = _check(requests.get(f"{_base()}/{cid}", headers=auth, timeout=60,
                                params={"fields": "status_code,status"}))
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"영상 처리 실패: {s}")
        time.sleep(10)
    else:
        raise RuntimeError("영상 처리 시간이 초과됐습니다.")
    media = _check(requests.post(f"{_base()}/{uid}/media_publish", headers=auth, timeout=120,
                                 data={"creation_id": cid}))
    info = _check(requests.get(f"{_base()}/{media['id']}", headers=auth, timeout=60,
                               params={"fields": "permalink"}))
    return media["id"], info.get("permalink", "")


def insights(media_id):
    tok = os.environ["IG_ACCESS_TOKEN"]
    out = {}
    for metric in ("views", "reach", "saved", "shares", "likes", "comments"):
        try:
            j = _check(requests.get(f"{_base()}/{media_id}/insights", timeout=60,
                                    headers={"Authorization": f"Bearer {tok}"}, params={"metric": metric}))
            d = j["data"][0]
            out[metric] = d.get("total_value", {}).get("value", (d.get("values") or [{}])[0].get("value"))
        except Exception as e:  # 지표 이름은 API 버전에 따라 바뀌므로 하나가 실패해도 계속
            print(f"[metrics] {metric} 건너뜀: {e}")
    return out
