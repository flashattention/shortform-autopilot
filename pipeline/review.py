"""보관: 만든 영상을 GitHub 릴리스에 올려 둡니다. 메일 첨부가 안 될 만큼 큰 영상의 받는 링크로도 씁니다."""
import os
import pathlib
import shutil
import subprocess
import tempfile

from .common import run

TAG = "videos"


def asset_url(spec_id):
    return f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{TAG}/{spec_id}.mp4"


def upload(spec, video_path):
    if subprocess.run(["gh", "release", "view", TAG], capture_output=True).returncode != 0:
        run(["gh", "release", "create", TAG, "--title", "만든 영상", "--prerelease",
             "--notes", "파이프라인이 만든 영상 보관함입니다."])
    named = pathlib.Path(tempfile.mkdtemp()) / f"{spec['id']}.mp4"   # 올라가는 이름은 파일 이름을 따른다
    shutil.copy(video_path, named)
    run(["gh", "release", "upload", TAG, str(named), "--clobber"])
    shutil.rmtree(named.parent, ignore_errors=True)
    return asset_url(spec["id"])


def prune(days=3):
    """보관함에서 며칠 지난 영상을 지운다 (릴리스 하나에 파일 1000개 한도)."""
    import datetime
    import json
    try:
        rel = json.loads(run(["gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/releases/tags/{TAG}"]).stdout)
    except Exception:
        return
    cut = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    for a in rel.get("assets", []):
        made = datetime.datetime.fromisoformat(a["created_at"].replace("Z", "+00:00"))
        if made < cut:
            run(["gh", "api", "-X", "DELETE", f"repos/{os.environ['GITHUB_REPOSITORY']}/releases/assets/{a['id']}"])
