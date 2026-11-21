"""완성된 영상을 메일로 보냅니다. job-autopilot 과 같은 Secret 이름을 씁니다.

MAIL_USERNAME 보내는 Gmail · MAIL_PASSWORD 앱 비밀번호(16자리) · MAIL_TO 받는 주소(없으면 보내는 주소)
"""
import os
import pathlib
import smtplib
from email.message import EmailMessage

MAX_ATTACH = 20 * 1024 * 1024  # Gmail 첨부 한도 25MB. 인코딩으로 커지는 몫을 빼고 20MB까지만 첨부
PLATFORM_KO = {"instagram": "인스타 릴스", "shorts": "유튜브 쇼츠", "tiktok": "틱톡"}


def send_video(spec, video_path, issue_url=None, video_url=None):
    user = (os.environ.get("MAIL_USERNAME") or "").strip()
    password = "".join(c for c in (os.environ.get("MAIL_PASSWORD") or "") if not c.isspace()).strip("\"'")
    if not user or not password:
        print("::warning::MAIL_USERNAME / MAIL_PASSWORD 가 없어 메일을 보내지 않았습니다.")
        return False
    video = pathlib.Path(video_path)
    size = video.stat().st_size
    c = spec["captions"]
    auto = [PLATFORM_KO[p] for p in spec["auto_publish"]]
    manual = [PLATFORM_KO[p] for p in spec["platforms"] if p not in spec["auto_publish"]]
    lines = [
        f"{spec['product']} · {spec['format']} · {spec['duration']}초 · {spec['account']} 계정",
        "",
        f"화면 자막: {spec['hook']} / {spec['cta']}",
        "",
    ]
    if issue_url:
        lines += [f"승인하기: {issue_url}", "  (이슈에 /approve 댓글을 달면 " +
                  (", ".join(auto) + "에 자동 게시" if auto else "처리 완료로 표시") + ")", ""]
    if manual:
        lines += [f"직접 올릴 곳: {', '.join(manual)} — 첨부 영상을 저장해서 올리세요.", ""]
    if size > MAX_ATTACH:
        lines += [f"영상이 {size / 1e6:.0f}MB라 첨부하지 못했습니다. 여기서 받으세요: {video_url}", ""]
    for p in spec["platforms"]:
        lines += [f"[{PLATFORM_KO[p]} {'제목' if p == 'shorts' else '캡션'}]", c[p], ""]
    msg = EmailMessage()
    msg["Subject"] = f"[숏폼] {spec['hook']}"
    msg["From"] = user
    msg["To"] = os.environ.get("MAIL_TO") or user
    msg.set_content("\n".join(lines))
    if size <= MAX_ATTACH:
        msg.add_attachment(video.read_bytes(), maintype="video", subtype="mp4", filename=f"{spec['id']}.mp4")
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
            print(f"[mail] 보냄: {msg['To']} ({size / 1e6:.1f}MB)")
            return True
        except smtplib.SMTPAuthenticationError as e:
            print(f"::warning::Gmail 로그인 거절({e.smtp_code}). MAIL_PASSWORD 가 앱 비밀번호(16자리)인지 확인하세요.")
            return False
        except (smtplib.SMTPServerDisconnected, OSError) as e:
            last = e
    print(f"::warning::메일 발송 실패: {last}")
    return False
