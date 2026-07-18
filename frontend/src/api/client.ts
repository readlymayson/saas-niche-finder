/** API client for NicheFinder DaaS. */

const API_BASE = "";

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = localStorage.getItem("access_token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (res.status === 429) {
    const data = await res.json();
    throw new Error(data.detail?.error || "Rate limit exceeded");
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed: ${res.status}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ──────────────────────────────────

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function register(email: string, password: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function refreshToken(refresh_token: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token }),
  });
}

// ── API Keys ──────────────────────────────

export interface ApiKeyInfo {
  id: number;
  key_prefix: string;
  name: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreated extends ApiKeyInfo {
  raw_key: string;
}

export async function listApiKeys(): Promise<ApiKeyInfo[]> {
  return request<ApiKeyInfo[]>("/api-keys");
}

export async function createApiKey(name?: string): Promise<ApiKeyCreated> {
  return request<ApiKeyCreated>("/api-keys", {
    method: "POST",
    body: JSON.stringify({ name: name || "default" }),
  });
}

export async function revokeApiKey(keyId: number): Promise<void> {
  return request<void>(`/api-keys/${keyId}`, { method: "DELETE" });
}

export async function updateApiKey(
  keyId: number,
  data: { name?: string; is_active?: boolean },
): Promise<ApiKeyInfo> {
  return request<ApiKeyInfo>(`/api-keys/${keyId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// ── Billing ───────────────────────────────

export interface TierInfo {
  slug: string;
  name: string;
  price_rub: number;
  requests_per_min: number;
  requests_per_month: number;
  duration_days: number;
}

export interface SubscriptionStatus {
  tier: string;
  is_active: boolean;
  expires_at: string | null;
  requests_per_min: number;
  requests_per_month: number;
}

export interface PaymentResponse {
  payment_id: string;
  confirmation_url: string | null;
  status: string;
}

export async function listTiers(): Promise<TierInfo[]> {
  return request<TierInfo[]>("/billing/tiers");
}

export async function getSubscription(): Promise<SubscriptionStatus> {
  return request<SubscriptionStatus>("/billing/subscription");
}

export async function subscribe(tierSlug: string): Promise<PaymentResponse> {
  return request<PaymentResponse>("/billing/subscribe", {
    method: "POST",
    body: JSON.stringify({ tier_slug: tierSlug }),
  });
}

// ── Niches (DaaS) ─────────────────────────

export interface NichePainPoint {
  text: string;
  source_url: string;
  source_title: string;
  author: string | null;
  published_at: string | null;
}

export interface NicheCompetitor {
  name: string;
  mention_count: number;
  sentiment: string;
}

export interface NicheMetrics {
  yandex_wordstat_requests: number;
  yandex_wordstat_trend: string;
  vcru_mentions: number;
  pain_point_count: number;
  competitor_count: number;
}

export interface NicheScore {
  niche_name: string;
  category: string;
  overall_score: number;
  confidence: number;
  metrics: NicheMetrics;
  pain_points: NichePainPoint[];
  competitors: NicheCompetitor[];
  summary_ru: string;
}

export interface NicheSearchResults {
  items: NicheScore[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}

export async function getTopNiches(
  limit = 10,
  offset = 0,
  category?: string,
): Promise<NicheSearchResults> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (category) params.set("category", category);
  return request<NicheSearchResults>(`/v1/niches/top?${params}`);
}

export async function searchNiches(
  query: string,
  limit = 10,
  offset = 0,
): Promise<NicheSearchResults> {
  const params = new URLSearchParams({ q: query, limit: String(limit), offset: String(offset) });
  return request<NicheSearchResults>(`/v1/niches/search?${params}`);
}
