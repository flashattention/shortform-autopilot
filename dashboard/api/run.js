// 실행 버튼: GitHub Actions 의 "영상 만들기" 를 시작한다.
// POST /api/run  { product: 'all' | 제품, rounds: 1~9, password }
// 필요한 환경변수: DASHBOARD_PASSWORD (버튼 비밀번호), GITHUB_TOKEN (이 레포 Actions 읽기·쓰기 권한)
import crypto from 'node:crypto';
import { PRODUCTS, WORKFLOW, gh, readBody, send } from './_lib.js';

const WAITING = ['queued', 'pending', 'waiting', 'requested'];

function same(a, b) {
  const x = crypto.createHash('sha256').update(String(a)).digest();
  const y = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(x, y);
}

export default async function handler(req, res) {
  if (req.method !== 'POST') return send(res, 405, { error: 'POST 만 받습니다' });
  const pass = process.env.DASHBOARD_PASSWORD || '';
  if (!pass || !process.env.GITHUB_TOKEN) {
    return send(res, 503, { error: '실행 버튼을 쓰려면 Vercel 환경변수에 DASHBOARD_PASSWORD 와 GITHUB_TOKEN(Actions 쓰기 권한)을 넣어 주세요' });
  }
  let b;
  try {
    b = await readBody(req);
  } catch {
    return send(res, 400, { error: 'JSON 이 아닙니다' });
  }
  if (!same(b.password || '', pass)) return send(res, 401, { error: '비밀번호가 틀렸습니다', badPassword: true });
  const product = String(b.product || 'all');
  if (product !== 'all' && !PRODUCTS[product]) return send(res, 400, { error: '모르는 제품입니다' });
  const rounds = Math.max(1, Math.min(9, parseInt(b.rounds, 10) || 1));

  try {
    // 이미 차례를 기다리는 실행이 있으면 새로 넣지 않는다 (GitHub 는 대기 중인 실행을 하나만 두고 나머지를 취소한다)
    const runs = (await gh(`actions/workflows/${WORKFLOW}/runs?per_page=10`)).workflow_runs || [];
    if (runs.some((r) => WAITING.includes(r.status))) {
      return send(res, 409, { error: '이미 차례를 기다리는 실행이 있어요. 그 실행이 시작된 뒤에 다시 눌러 주세요' });
    }
    const busy = runs.some((r) => r.status === 'in_progress');
    await gh(`actions/workflows/${WORKFLOW}/dispatches`, {
      method: 'POST',
      body: { ref: process.env.GITHUB_REF_NAME || 'main', inputs: { product, rounds: String(rounds) } },
    });
    return send(res, 200, {
      ok: true,
      message: busy
        ? '실행을 요청했어요. 지금 돌고 있는 실행이 끝나면 이어서 시작해요'
        : '실행을 요청했어요. GitHub가 시작하는 데 보통 10~30초 걸려요',
    });
  } catch (e) {
    const hint = e.status === 403 || e.status === 404 ? ' (GITHUB_TOKEN 에 이 레포 Actions 쓰기 권한이 있는지 확인하세요)' : '';
    return send(res, 502, { error: `GitHub 요청 실패: ${e.message}${hint}` });
  }
}
