const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type NicheCard = {
  id: number;
  slug: string;
  title: string;
  summary: string | null;
  score: number | null;
};

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function register(email: string, password: string): Promise<TokenPair> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function parseApiError(res: Response): Promise<string> {
  const text = await res.text();
  if (res.status === 429) {
    return "Лимит Free: 5 просмотров карточек в сутки. Оформите Pro.";
  }
  return text || res.statusText;
}

export async function fetchTopNiches(limit = 10): Promise<NicheCard[]> {
  const res = await fetch(`${API_BASE}/v1/niches/top?limit=${limit}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function searchNiches(q: string): Promise<NicheCard[]> {
  const res = await fetch(`${API_BASE}/v1/niches/search?q=${encodeURIComponent(q)}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function fetchNiche(nicheId: number): Promise<NicheCard> {
  const res = await fetch(`${API_BASE}/v1/niches/${nicheId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export async function fetchSimilarNiches(nicheId: number, limit = 5): Promise<NicheCard[]> {
  const res = await fetch(`${API_BASE}/v1/niches/${nicheId}/similar?limit=${limit}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await parseApiError(res));
  return res.json();
}

export type PaymentResponse = {
  payment_id: string;
  confirmation_url: string;
  amount_rub: string;
  human_gate_required: boolean;
  message: string | null;
};

export async function createPayment(): Promise<PaymentResponse> {
  const res = await fetch(`${API_BASE}/v1/billing/create-payment`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
