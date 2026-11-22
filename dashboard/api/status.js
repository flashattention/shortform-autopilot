// 화면이 5초마다 부르는 곳: 저장된 진행 상황 + GitHub Actions 실행 상태를 합쳐 돌려준다.
// GET /api/status
import { PREFIX, PRODUCTS, REPO, WORKFLOW, gh, redis, send, storeConfigured } from './_lib.js';

const GH_TTL = 15000; // GitHub 는 15초에 한 번만 묻는다

let ghCache = { at: 0, data: null };

async function github() {
  if (ghCache.data && Date.now() - ghCache.at < GH_TTL) return ghCache.data;
  try {
    const runs = (await gh(`actions/workflows/${WORKFLOW}/runs?per_page=6`)).workflow_runs || [];
    const pick = runs.find((r) => r.status !== 'completed') || runs[0];
    let jobs = [];
    if (pick) jobs = (await gh(`actions/runs/${pick.id}/jobs?per_page=30`)).jobs || [];
    const slim = (r) => r && {
      id: r.id, status: r.status, conclusion: r.conclusion, event: r.event,
      created_at: r.created_at, updated_at: r.updated_at, url: r.html_url, title: r.display_title,
    };
    const data = {
      ok: true,
      current: slim(pick),
      recent: runs.map(slim),
      jobs: jobs.map((j) => ({
        name: j.name, status: j.status, conclusion: j.conclusion,
        started_at: j.started_at, completed_at: j.completed_at, url: j.html_url,
        step: (j.steps || []).find((s) => s.status === 'in_progress')?.name || null,
      })),
    };
    ghCache = { at: Date.now(), data };
    return data;
  } catch (e) {
    return ghCache.data ? { ...ghCache.data, stale: true } : { ok: false, error: String(e.message || e) };
  }
}

export default async function handler(req, res) {
  const out = { now: Date.now(), repo: REPO, store: storeConfigured(), canRun: Boolean(process.env.DASHBOARD_PASSWORD && process.env.GITHUB_TOKEN), products: {}, videos: [] };
  if (req.query?.fresh || (req.url || '').includes('fresh=1')) ghCache.at = 0;
  const names = { ...PRODUCTS };
  if (out.store) {
    try {
      const [extra] = await redis([['SMEMBERS', `${PREFIX}products`]]);
      for (const p of extra || []) if (!names[p]) names[p] = p;
      const ids = Object.keys(names);
      const cmds = [];
      for (const p of ids) cmds.push(['GET', `${PREFIX}p:${p}`], ['LRANGE', `${PREFIX}log:${p}`, '0', '11']);
      cmds.push(['LRANGE', `${PREFIX}videos`, '0', '23']);
      const r = await redis(cmds);
      ids.forEach((p, i) => {
        out.products[p] = {
          name: names[p],
          last: r[i * 2] ? JSON.parse(r[i * 2]) : null,
          log: (r[i * 2 + 1] || []).map((x) => JSON.parse(x)),
        };
      });
      out.videos = (r[r.length - 1] || []).map((x) => JSON.parse(x));
    } catch (e) {
      out.storeError = String(e.message || e);
    }
  }
  for (const p of Object.keys(names)) if (!out.products[p]) out.products[p] = { name: names[p], last: null, log: [] };
  out.github = await github();
  return send(res, 200, out);
}
