# shortform-autopilot

쥐 가장, 카피좀비, 드림 러너, 젤리 서울 러너, Latent Atlas 숏폼을 기획부터 편집까지 자동으로 만들어 메일로 보내는 파이프라인입니다. 올리는 건 직접 합니다.

```
기획(plan) → 녹화(capture) 또는 직접 찍은 클립 → 편집(edit) → 검수(qc) → 메일 발송 → 직접 업로드 → 조회수 기록 → 다음 기획에 반영
```

- 아침 06:17부터 3번, 저녁 17:17부터 6번 이어서(또는 Actions → "영상 만들기" 를 직접 돌리면) 제품 다섯 개를 동시에 만들며, 제품마다 장면 2개를 골라, 장면마다 한국어 1편 + 영어 1편을 만듭니다. 제품당 4편, 지금은 4개 제품이라 한 번에 16편입니다.
- 장면은 `config/products.yaml` 의 `scenes` 에서 가장 오래 안 쓴 것부터 고릅니다 (드림 러너 맵 5개, 서울 동네 13곳, Latent Atlas 개념 24개 등). 문구는 Claude가 그 장면에 맞춰 매번 새로 씁니다.
- 카피좀비와 Latent Atlas는 브라우저 언어를 따라가므로 영어 편은 영어 화면으로 따로 찍습니다.
- 찍기 전에 스크린샷을 먼저 찍어 Claude가 확인합니다. 하늘만 찍히거나 메뉴·로딩·결과 화면처럼 말도 안 되는 화면만 거르고, 애매하면 통과시킵니다. 통과한 그 화면에서 이어서 녹화합니다.
- 문구는 검수하지 않습니다. 대신 찍힌 화면을 보고 서로 다른 방향의 문구를 세 가지 써서, 같은 화면에 문구만 다른 영상 세 편을 만듭니다.
- 장면·언어마다 메일 한 통에 세 편이 첨부되어 옵니다 (용량이 넘치면 나눠서). 마음에 드는 것만 골라 올리면 됩니다.
- 올린 뒤 조회수를 Actions → "성과 기록" 에 넣으면, 잘된 포맷을 다음 기획에서 더 자주 고릅니다.

## 계정 구성

| 계정 | 언어 | 플랫폼 | 제품 |
|---|---|---|---|
| kr | 한국어 | 인스타 릴스, 쇼츠 | 전 제품 |
| global | 영어 | 틱톡, 쇼츠 | 전 제품 |

인스타는 크리에이터 계정을 권합니다. 인사이트를 볼 수 있고 음원 제한이 덜합니다.

## 처음 설정

1. 레포 Settings → Secrets and variables → Actions 에 등록합니다.
   - `MAIL_USERNAME`(보내는 Gmail), `MAIL_PASSWORD`(Google 앱 비밀번호 16자리), `MAIL_TO`(받는 주소, 비우면 보내는 주소) — job-autopilot 과 같은 값
   - `ANTHROPIC_API_KEY` — 필수. 검수와 문구 작성에 씁니다. 키가 없거나 거절되면 영상을 보내지 않습니다
2. Actions 탭 → "영상 만들기" → Run workflow 로 한 번 돌려 봅니다.
3. 쥐 가장은 배포 후 `config/products.yaml` 의 `url` 을 채웁니다. 그전에는 `clips/mouse-father/` 에 넣은 클립으로만 만들어집니다.


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
| 훅·CTA·해시태그, 장면 목록, 자동 조작 | `config/products.yaml` |
| 포맷 추가, 길이 조정 | `config/formats.yaml` |
| 만드는 시간 | `.github/workflows/produce.yml` 의 cron |
| 배경음 | `assets/bgm/*.mp3` (사용권이 있는 음원만) |
| 자막 글꼴 | `assets/font.ttf` |

## 알아둘 한계

- 자동 녹화는 게임 시계를 붙잡고 한 장씩 찍어서 30fps 로 매끄럽게 나옵니다. 대신 영상 한 편에 몇 분이 걸립니다.
- 운영 중인 게임을 봇이 플레이하므로, 기록·통계 요청은 `config/products.yaml` 의 `block` 으로 막아 둡니다. 새 제품을 추가할 때도 꼭 넣으세요.
- **자동 녹화는 봇이 정해진 조작을 반복하는 화면입니다.** 러너나 Latent Atlas처럼 단순한 화면에는 쓸 만하지만, 카피좀비 같은 슈팅은 사람이 플레이한 클립이 훨씬 낫습니다. 플레이 테스트할 때 화면 녹화를 켜 두고 `clips/` 에 넣는 걸 권합니다.
- 자동 녹화에는 소리가 없습니다. 배경음을 넣지 않으면 무음이니, 올릴 때 앱에서 음원을 붙이세요.
- 쥐 가장의 CTA는 스팀 페이지가 생기기 전이라 "Follow for the demo" 로 해뒀습니다. 페이지를 열면 "Wishlist on Steam" 으로 바꾸세요.

## 진행 상황 대시보드 (Vercel)

`dashboard/` 폴더가 대시보드입니다. 제품마다 지금 어느 단계인지(화면 확인, 녹화 몇 장째, 문구, 편집, 메일), 이번 실행에서 보낸 수·제외 수, 최근 기록, 최근 보낸 영상을 5초마다 보여 줍니다. 위쪽 **전체 실행**(1·3·6번 이어서)과 카드마다 **실행** 버튼으로 바로 돌릴 수 있습니다. 이미 차례를 기다리는 실행이 있으면 새 요청은 받지 않습니다 (GitHub 가 대기 중인 실행을 하나만 남기고 나머지를 취소하기 때문).

1. Vercel → Add New → Project → 이 레포를 가져오고, **Root Directory 를 `dashboard`** 로 정한 뒤 배포합니다. (Framework Preset 은 Other)
2. 그 프로젝트의 Storage(또는 Marketplace)에서 **Upstash Redis** 를 만들어 연결합니다. 연결하면 `KV_REST_API_URL`, `KV_REST_API_TOKEN` 이 자동으로 들어갑니다. 무료 요금제로 충분합니다.
3. 프로젝트 Settings → Environment Variables 에 추가합니다.
   - `PROGRESS_SECRET`: 아무도 모르는 긴 문자열 (파이프라인과 똑같이 넣습니다)
   - `GITHUB_TOKEN`: GitHub 에서 만든 토큰 (Fine-grained token, 이 레포만, **Actions 권한 Read and write**). 실행 상태 읽기와 실행 버튼에 씁니다. 없으면 GitHub 가 시간당 60번만 허락해서 실행 상태가 금방 안 보이고, 버튼도 꺼집니다
   - `DASHBOARD_PASSWORD`: 실행 버튼 비밀번호. 대시보드 주소를 아는 사람 누구나 실행을 걸 수 없게 막습니다
4. 다시 배포(Redeploy)합니다.
5. 이 레포 Settings → Secrets and variables → Actions 에 넣습니다.
   - Variables: `DASHBOARD_URL` = 배포된 주소 (예: `https://shortform-dashboard.vercel.app`)
   - Secrets: `PROGRESS_SECRET` = 3번과 같은 값

`DASHBOARD_URL` 이 없거나 대시보드가 꺼져 있어도 영상 만들기는 그대로 돌아갑니다. 대시보드는 다음 실행부터 세부 진행 상황을 받습니다.
