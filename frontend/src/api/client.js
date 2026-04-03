/**
 * InferenceChain API Client
 *
 * All REST calls go through this singleton.
 * Dashboard endpoints live under /dashboard/*
 * Chain/state/tx/p2p endpoints are at root level.
 */

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const WS_BASE  = process.env.REACT_APP_WS_URL  || 'ws://localhost:8000';

async function request(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json().catch(() => null);
}

// ── Chain ─────────────────────────────────────────────────────────────────────
export const chain = {
  height:       ()            => request('/chain/height'),
  tip:          ()            => request('/chain/tip'),
  block:        (height)      => request(`/chain/block/${height}`),
  blockByHash:  (hash)        => request(`/chain/block/hash/${hash}`),
  blocks:       (limit=20, before=null) =>
    request(`/chain/blocks?limit=${limit}${before != null ? `&before=${before}` : ''}`),
  stats:        ()            => request('/chain/stats'),
};

// ── State ─────────────────────────────────────────────────────────────────────
export const state = {
  balance:  (address)  => request(`/state/balance/${address}`),
  node:     (nodeId)   => request(`/state/node/${nodeId}`),
  active:   ()         => request('/state/nodes/active'),
  dnn:      ()         => request('/state/nodes/dnn'),
  pos:      ()         => request('/state/nodes/pos'),
};

// ── Transactions ──────────────────────────────────────────────────────────────
export const tx = {
  get:     (txId) => request(`/tx/${txId}`),
  pending: ()     => request('/tx/pending'),
  submit:  (body) => request('/tx/submit', { method: 'POST', body: JSON.stringify(body) }),
};

// ── P2P / Network ─────────────────────────────────────────────────────────────
export const p2p = {
  status: () => request('/p2p/status'),
  peers:  () => request('/p2p/peers'),
};

// ── Dashboard (chain-authoritative) ──────────────────────────────────────────
export const dashboard = {
  stats:      ()              => request('/dashboard/stats'),
  validators: (nodeType=null) =>
    request(`/dashboard/validators${nodeType ? `?node_type=${nodeType}` : ''}`),
  validator:  (nodeId)        => request(`/dashboard/validators/${nodeId}`),
  models:     (state=null)    =>
    request(`/dashboard/models${state ? `?state=${state}` : ''}`),
  model:      (id)            => request(`/dashboard/models/${id}`),
  health:     ()              => request('/dashboard/health'),
};

// ── Model upload (multipart) ──────────────────────────────────────────────────
export async function uploadModel(formData) {
  const res = await fetch(`${API_BASE}/dashboard/models/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Upload failed: HTTP ${res.status}`);
  }
  return res.json();
}

// ── WebSocket URLs ────────────────────────────────────────────────────────────
export const ws = {
  consensus: `${WS_BASE}/ws/consensus-rounds`,
  validators: `${WS_BASE}/ws/validators`,
  models:     `${WS_BASE}/ws/models`,
};
