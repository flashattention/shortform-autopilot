"""검수 대기열: 영상을 GitHub 릴리스에 올리고, 승인용 이슈를 만듭니다. (gh CLI 사용)"""
import json
import os
import re
import subprocess

from .common import run

TAG = "queue"
PLATFORM_KO = {"instagram": "인스타 릴스", "shorts": "유튜브 쇼츠", "tiktok": "틱톡"}


def _repo():
    return os.environ["GITHUB_REPOSITORY"]


def asset_url(spec_id):
    return f"https://github.com/{_repo()}/releases/download/{TAG}/{spec_id}.mp4"


def enqueue(spec, video_path):
    if subprocess.run(["gh", "release", "view", TAG], capture_output=True).returncode != 0:
        run(["gh", "release", "create", TAG, "--title", "검수 대기 영상", "--prerelease",
             "--notes", "파이프라인이 만든 영상이 여기에 올라옵니다."])
    run(["gh", "release", "upload", TAG, f"{video_path}#{spec['id']}.mp4", "--clobber"])
    auto = [PLATFORM_KO[p] for p in spec["auto_publish"]]
    manual = [PLATFORM_KO[p] for p in spec["platforms"] if p not in spec["auto_publish"]]
    c = spec["captions"]
    body = f"""**{spec['product']}** · {spec['format']} · {spec['duration']}초 · {spec['account']} 계정

▶ 영상 보기: {asset_url(spec['id'])}

### 화면 자막
- 훅: {spec['hook']}
- CTA: {spec['cta']}

### 인스타 캡션
```text
{c['instagram']}
```

### 쇼츠 제목
```text
{c['shorts']}
```

### 틱톡 캡션
```text
{c['tiktok']}
```

---
- 승인: `approve` 라벨을 붙이거나 댓글로 `/approve`
- 반려: `reject` 라벨 또는 댓글 `/reject`
- 캡션을 고치고 싶으면 이 본문의 캡션 칸을 수정한 뒤 승인하세요. 수정한 내용으로 올라갑니다.
- 승인하면 자동 게시: {', '.join(auto) or '없음'} / 직접 올리기: {', '.join(manual) or '없음'}

<!-- meta: {json.dumps(spec, ensure_ascii=False)} -->"""
    r = run(["gh", "issue", "create", "--title", f"[검수] {spec['hook']}", "--body", body,
             "--label", "review", "--label", spec["account"]])
    return r.stdout.strip()


def read_issue(number):
    r = run(["gh", "issue", "view", str(number), "--json", "body,title,state"])
    body = json.loads(r.stdout)["body"].replace("\r\n", "\n")
    spec = json.loads(re.search(r"<!-- meta: (.*) -->", body, re.S).group(1))
    for key, head in (("instagram", "인스타 캡션"), ("shorts", "쇼츠 제목"), ("tiktok", "틱톡 캡션")):
        m = re.search(rf"### {head}\n```text\n(.*?)\n```", body, re.S)
        if m:
            spec["captions"][key] = m.group(1).strip()
    return spec


def download(spec_id, dest_dir):
    run(["gh", "release", "download", TAG, "-p", f"{spec_id}.mp4", "-D", str(dest_dir), "--clobber"])
    return f"{dest_dir}/{spec_id}.mp4"


def comment_and_close(number, text, reason="completed"):
    run(["gh", "issue", "comment", str(number), "--body", text])
    run(["gh", "issue", "close", str(number), "--reason", reason])
