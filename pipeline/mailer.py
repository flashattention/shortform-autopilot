"""완성된 영상을 메일로 보냅니다. job-autopilot 과 같은 Secret 이름을 씁니다.

MAIL_USERNAME 보내는 Gmail · MAIL_PASSWORD 앱 비밀번호(16자리) · MAIL_TO 받는 주소(없으면 보내는 주소)
"""
import os
import pathlib
import smtplib
from email.message import EmailMessage

MAX_ATTACH = 17 * 1024 * 1024  # Gmail 한도 25MB 는 인코딩 뒤 크기 기준(약 1.37배)이라 원본 17MB까지만 첨부
PLATFORM_KO = {"instagram": "인스타 릴스", "shorts": "유튜브 쇼츠", "tiktok": "틱톡"}


def send_video(spec, video_path, video_url=None):
    video = pathlib.Path(video_path)
    size = video.stat().st_size
    c = spec["captions"]
    where = ", ".join(PLATFORM_KO[p] for p in spec["platforms"])
    lines = [
        f"{spec['product']} · {spec['scene']} · {spec['format']} · {spec['duration']}초 · {spec['account']} 계정",
        f"올릴 곳: {where}",
        f"화면 자막: {spec['hook']} / {spec['cta']}",
        "",
    ]
    if size > MAX_ATTACH:
        lines += [f"영상이 {size / 1e6:.0f}MB라 첨부하지 못했습니다. 여기서 받으세요: {video_url}", ""]
    for p in spec["platforms"]:
        lines += [f"[{PLATFORM_KO[p]} {'제목' if p == 'shorts' else '캡션'}]", c[p], ""]
    lines += ["---", f"성과 기록용 영상 ID: {spec['id']}",
              "(Actions → 성과 기록 → Run workflow 에 이 ID와 조회수를 넣으면 다음 기획에 반영됩니다)"]
    msg = EmailMessage()
    msg["Subject"] = f"[숏폼·{'한국어' if spec['lang'] == 'ko' else '영어'}] {spec['hook']}"
    msg.set_content("\n".join(lines))
    if size <= MAX_ATTACH:
        msg.add_attachment(video.read_bytes(), maintype="video", subtype="mp4", filename=f"{spec['id']}.mp4")
    return _send(msg, f"{size / 1e6:.1f}MB")


def send_summary(sent, failed):
    """한 번 실행이 끝나면 무엇을 보냈고 무엇을 검수에서 뺐는지 한 통으로 알린다."""
    lines = [f"보낸 영상 {len(sent)}편, 검수에서 제외 {len(failed)}편", ""]
    for s in sent:
        lines.append(f"✓ [{s['lang']}] {s['product']} · {s['scene']} · {s['hook']}")
    if failed:
        lines += ["", "제외한 영상과 이유"]
        for s, why in failed:
            lines.append(f"✗ [{s['lang']}] {s['product']} · {s['scene']} — {why}")
    msg = EmailMessage()
    msg["Subject"] = f"[숏폼 요약] 보냄 {len(sent)} · 제외 {len(failed)}"
    msg.set_content("\n".join(lines))
    return _send(msg, "요약")


def _send(msg, note):
    user = (os.environ.get("MAIL_USERNAME") or "").strip()
    password = "".join(c for c in (os.environ.get("MAIL_PASSWORD") or "") if not c.isspace()).strip("\"'")
    if not user or not password:
        print("::warning::MAIL_USERNAME / MAIL_PASSWORD 가 없어 메일을 보내지 않았습니다.")
        return False
    msg["From"] = user
    msg["To"] = os.environ.get("MAIL_TO") or user
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    last = None
    for port in (int(os.environ.get("SMTP_PORT") or 465), 587):  # 465가 끊기면 587로 한 번 더
        try:
            smtp = smtplib.SMTP_SSL(host, port, timeout=120) if port == 465 else smtplib.SMTP(host, port, timeout=120)
            if port != 465:
                smtp.starttls()
            with smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
            print(f"[mail] 보냄: {msg['To']} ({note})")
            return True
        except smtplib.SMTPAuthenticationError as e:
            print(f"::warning::Gmail 로그인 거절({e.smtp_code}). MAIL_PASSWORD 가 앱 비밀번호(16자리)인지 확인하세요.")
            return False
        except (smtplib.SMTPServerDisconnected, OSError) as e:
            last = e
    print(f"::warning::메일 발송 실패: {last}")
    return False
