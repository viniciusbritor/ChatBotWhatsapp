// API client autenticado para o Coherence Control Plane.
// Token extraido de ?token= ou sessionStorage; enviado em Authorization.

const _tok = (() => {
  try {
    const u = new URLSearchParams(location.search).get('token');
    if (u) { sessionStorage.setItem('_ctok', u); return u; }
    return sessionStorage.getItem('_ctok') || '';
  } catch (_) { return ''; }
})();

const _portalUrl = (
  import.meta.env.VITE_COHERENCE_PORTAL_URL
  || 'https://coherence-portal-test-894828119087.us-central1.run.app'
);

export function getToken(): string {
  return _tok;
}

export function getPortalUrl(): string {
  return _portalUrl;
}

export async function api<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const sep = path.includes('?') ? '&' : '?';
  const url = path + (_tok ? sep + 'token=' + encodeURIComponent(_tok) : '');
  const resp = await fetch(url, {
    credentials: 'include',
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
      ...(_tok ? { Authorization: 'Bearer ' + _tok } : {}),
    },
  });
  if (!resp.ok) {
    let detail = '';
    try { detail = (await resp.json()).detail || ''; } catch (_) {}
    const err: any = new Error(detail || 'HTTP ' + resp.status);
    err.status = resp.status;
    throw err;
  }
  const ct = resp.headers.get('content-type') || '';
  return ct.includes('json') ? resp.json() : (resp.text() as any);
}
