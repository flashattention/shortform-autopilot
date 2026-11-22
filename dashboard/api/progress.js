// 파이프라인이 단계마다 보내는 진행 상황을 받아 저장한다.
// POST /api/progress   Authorization: Bearer <PROGRESS_SECRET>
import { PREFIX, readBody, redis, send } from './_lib.js';

const KEEP_LOG = 40;
const KEEP_VIDEOS = 60;

export default async function handler(req, res) {
  if (req.method !== 'POST') return send(res, 405, { error: 'POST 만 받습니다' });
  const secret = process.env.PROGRESS_SECRET || '';
  if (!secret || req.headers.authorization !== `Bearer ${secret}`) return send(res, 401, { error: '인증 실패' });

  let ev;
  try {
    ev = await readBody(req);
  } catch {
    return send(res, 400, { error: 'JSON 이 아닙니다' });
  }
  const product = String(ev.product || '');
  if (!/^[a-z0-9-]{1,40}$/.test(product)) return send(res, 400, { error: 'product 가 올바르지 않습니다' });

  // 받은 그대로 저장하되, 문자열 길이는 잘라 둔다 (화면에 쓰는 값만)
  const clean = {};
  for (const [k, v] of Object.entries(ev)) {
    if (typeof v === 'string') clean[k] = v.slice(0, 300);
    else if (typeof v === 'number' || typeof v === 'boolean' || v === null) clean[k] = v;
  }
  clean.product = product;
  clean.ts = Date.now();
  const line = JSON.stringify(clean);

  const cmds = [
    ['SET', `${PREFIX}p:${product}`, line],
    ['LPUSH', `${PREFIX}log:${product}`, line],
    ['LTRIM', `${PREFIX}log:${product}`, '0', String(KEEP_LOG - 1)],
    ['SADD', `${PREFIX}products`, product],
  ];
  if (clean.stage === '완료' && clean.hook) {
    cmds.push(['LPUSH', `${PREFIX}videos`, line], ['LTRIM', `${PREFIX}videos`, '0', String(KEEP_VIDEOS - 1)]);
  }
  try {
    await redis(cmds);
  } catch (e) {
    return send(res, 500, { error: String(e.message || e) });
  }
  return send(res, 200, { ok: true });
}
