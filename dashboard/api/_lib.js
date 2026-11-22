// 공용: 저장소(Upstash Redis REST)와 제품 목록
// Vercel 마켓플레이스에서 Upstash Redis 를 연결하면 KV_REST_API_URL / KV_REST_API_TOKEN 이 자동으로 들어온다.

export const PRODUCTS = {
  'dream-runner': '드림 러너',
  'jelly-seoul-runner': '젤리 서울 러너',
  capyzombie: '카피좀비',
  'mouse-father': '쥐구멍에도 볕 들 날',
  'latent-atlas': 'Latent Atlas',
};

export const PREFIX = 'sfa:';

const URL_ = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL || '';
const TOKEN = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN || '';

export const storeConfigured = () => Boolean(URL_ && TOKEN);

// 명령 여러 개를 한 번에 보낸다. 결과는 명령 순서대로.
export async function redis(commands) {
  if (!storeConfigured()) throw new Error('저장소(Upstash Redis)가 연결되지 않았습니다');
  const r = await fetch(`${URL_.replace(/\/$/, '')}/pipeline`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(commands),
  });
  if (!r.ok) throw new Error(`저장소 오류 ${r.status}: ${(await r.text()).slice(0, 200)}`);
  const out = await r.json();
  return out.map((x) => {
    if (x.error) throw new Error(`저장소 오류: ${x.error}`);
    return x.result;
  });
}

export function send(res, status, body) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(body));
}

export async function readBody(req) {
  if (req.body !== undefined) return typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body;
  const chunks = [];
  for await (const c of req) chunks.push(c);
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

// GitHub API (실행 상태 읽기, 실행 버튼)
export const REPO = process.env.GITHUB_REPO || 'flashattention/shortform-autopilot';
export const WORKFLOW = process.env.GITHUB_WORKFLOW_FILE || 'produce.yml';
const GH_API = (process.env.GITHUB_API || 'https://api.github.com').replace(/\/$/, '');

export async function gh(path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/vnd.github+json', 'User-Agent': 'shortform-dashboard' };
  if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  if (body) headers['Content-Type'] = 'application/json';
  const r = await fetch(`${GH_API}/repos/${REPO}/${path}`, { method, headers, body: body && JSON.stringify(body) });
  if (!r.ok) {
    const err = new Error(`GitHub ${r.status}`);
    err.status = r.status;
    err.detail = (await r.text()).slice(0, 300);
    throw err;
  }
  return r.status === 204 ? null : r.json();
}
