import json
import pathlib
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "out"
STATE = ROOT / "state"
CLIPS = ROOT / "clips"


def load_yaml(name):
    return yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8"))


def load_state(name, default):
    p = STATE / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save_state(name, data):
    STATE.mkdir(exist_ok=True)
    (STATE / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_history():
    """모든 기록을 합쳐 읽는다. 제품별로 동시에 돌 때 서로 덮어쓰지 않게 기록 파일을 제품마다 나눠 둔다."""
    out = list(load_state("history.json", []))
    for p in sorted(STATE.glob("history-*.json")):
        out += json.loads(p.read_text(encoding="utf-8"))
    return out


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def probe(path):
    """(width, height, duration_seconds)"""
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:format=duration", "-of", "json", str(path)])
    j = json.loads(r.stdout)
    s = j["streams"][0]
    return int(s["width"]), int(s["height"]), float(j["format"].get("duration") or 0)
