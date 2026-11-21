# shortform-autopilot

쥐 가장, 카피좀비, 드림 러너, 젤리 서울 러너, Latent Atlas 숏폼을 기획부터 게시까지 돌리는 파이프라인입니다.

```
기획(plan) → 녹화(capture) 또는 직접 찍은 클립 → 편집(edit) → 검수 이슈(review) → 승인 → 게시(publish) → 성과 수집(metrics) → 다음 기획에 반영
```

- 월·수·금 18시에 계정마다 영상 1개씩 만들어 GitHub 이슈로 올리고, 영상을 첨부해 메일로도 보냅니다.
- 이슈에서 영상을 보고 `approve` 라벨이나 `/approve` 댓글을 달면 인스타에 자동 게시됩니다.
- 쇼츠·틱톡은 이슈에 영상 링크와 캡션이 준비돼 있으니 내려받아 직접 올립니다. (두 곳 모두 API 심사 전에는 자동 게시물이 비공개로 묶입니다.)

## 계정 구성

| 계정 | 언어 | 플랫폼 | 제품 |
|---|---|---|---|
| kr | 한국어 | 인스타 릴스(자동), 쇼츠(수동) | 드림 러너, 젤리 서울 러너, 카피좀비, Latent Atlas |
| global | 영어 | 틱톡(수동), 쇼츠(수동) | 카피좀비, 쥐 가장 |

## 처음 설정

1. GitHub에 새 레포를 만들고 이 폴더를 그대로 push 합니다. 비공개 레포도 됩니다.
2. `config/products.yaml` 에서 `url: ""` 로 비어 있는 제품(쥐 가장)의 주소를 배포 후 채웁니다. 주소가 없으면 그 제품은 `clips/<제품>/` 에 넣은 클립으로만 만들어집니다.
3. 인스타 계정을 프로페셔널(비즈니스) 계정으로 바꾸고, Meta 개발자 앱에서 `instagram_content_publish` 권한이 있는 토큰을 발급합니다. 절차는 공식 문서를 따르세요: https://developers.facebook.com/documentation/instagram-platform/content-publishing
4. 레포 Settings → Secrets and variables → Actions 에 등록합니다.
   - Secrets: `IG_USER_ID`, `IG_ACCESS_TOKEN`, (선택) `ANTHROPIC_API_KEY`
   - 메일로 영상 받기: `MAIL_USERNAME`(보내는 Gmail), `MAIL_PASSWORD`(Google 앱 비밀번호 16자리), `MAIL_TO`(받는 주소) — job-autopilot 과 같은 값
   - Variables(선택): `IG_API_BASE`, `IG_UPLOAD_MODE` — `pipeline/instagram.py` 맨 위 설명 참고
5. Actions 탭 → "영상 만들기" → Run workflow 로 한 번 돌려 봅니다.

`ANTHROPIC_API_KEY` 가 없으면 `products.yaml` 에 적어둔 훅을 돌려 쓰므로 비용이 0원입니다. 키가 있으면 Claude가 포맷과 지난 성과를 보고 문구를 새로 씁니다.

## 직접 찍은 클립 쓰기

`clips/<제품>/` 에 영상을 넣고 push 하면 자동 녹화보다 먼저 쓰입니다. 한 번 쓴 클립은 다시 쓰지 않습니다.

- `before_*.mp4` + `after_*.mp4` → 비포 애프터 포맷
- `bug_*.mp4` → 버그·NG 포맷
- 그 밖의 이름 → 일반 포맷
- 가로 영상은 흐린 배경 위에 자동으로 세로 배치됩니다. 파일 하나는 100MB 아래로 유지하세요.

## 로컬에서 돌리기

```bash
pip install -r requirements.txt && playwright install chromium
python -m pipeline.run produce --no-queue     # out/ 에 영상만 만들기
```

## 고칠 곳

| 하고 싶은 일 | 파일 |
|---|---|
| 훅·CTA·해시태그, 자동 조작 레시피 | `config/products.yaml` |
| 포맷 추가, 길이 조정 | `config/formats.yaml` |
| 게시 요일·시간 | `.github/workflows/produce.yml` 의 cron |
| 배경음 | `assets/bgm/*.mp3` (사용권이 있는 음원만) |
| 자막 글꼴 | `assets/font.ttf` |

## 알아둘 한계

- **자동 녹화는 봇이 정해진 조작을 반복하는 화면입니다.** 러너나 Latent Atlas처럼 단순한 화면에는 쓸 만하지만, 카피좀비 같은 슈팅은 사람이 플레이한 클립이 훨씬 낫습니다. 플레이 테스트할 때 화면 녹화를 켜 두고 `clips/` 에 넣는 걸 권합니다.
- 자동 녹화에는 소리가 없습니다. 배경음을 넣지 않으면 무음으로 나갑니다.
- 인스타 게시 코드는 공식 문서대로 작성했지만 실제 계정으로 돌려보지는 못했습니다. 첫 승인 때 Actions 로그를 확인하세요.
- 인스타 토큰은 만료됩니다. 게시가 인증 오류로 실패하면 토큰을 새로 발급해 Secret을 바꾸세요.
- 쥐 가장의 CTA는 스팀 페이지가 생기기 전이라 "Follow for the demo" 로 해뒀습니다. 페이지를 열면 "Wishlist on Steam" 으로 바꾸세요.
