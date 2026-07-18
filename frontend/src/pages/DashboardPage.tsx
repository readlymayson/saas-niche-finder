/** Dashboard page — API key management, usage stats, and playground. */
import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import {
  listApiKeys,
  createApiKey,
  revokeApiKey,
  updateApiKey,
  getSubscription,
  subscribe,
  listTiers,
  getTopNiches,
  type ApiKeyInfo,
  type ApiKeyCreated,
  type SubscriptionStatus,
  type TierInfo,
  type NicheSearchResults,
} from "@/api/client";

export function DashboardPage() {
  const { user, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<"keys" | "billing" | "playground">("keys");
  const [keys, setKeys] = useState<ApiKeyInfo[]>([]);
  const [newKey, setNewKey] = useState<ApiKeyCreated | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionStatus | null>(null);
  const [tiers, setTiers] = useState<TierInfo[]>([]);
  const [niches, setNiches] = useState<NicheSearchResults | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── Load data ──

  useEffect(() => {
    listApiKeys()
      .then(setKeys)
      .catch(() => {});
    getSubscription()
      .then(setSubscription)
      .catch(() => {});
    listTiers()
      .then(setTiers)
      .catch(() => {});
  }, []);

  // ── API Keys handlers ──

  const handleCreateKey = async () => {
    setError(null);
    try {
      const key = await createApiKey();
      setNewKey(key);
      setKeys((prev) => [
        {
          id: key.id,
          key_prefix: key.key_prefix,
          name: key.name,
          is_active: key.is_active,
          last_used_at: null,
          created_at: key.created_at,
        },
        ...prev,
      ]);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleRevoke = async (keyId: number) => {
    setError(null);
    try {
      await revokeApiKey(keyId);
      setKeys((prev) => prev.filter((k) => k.id !== keyId));
    } catch (err: any) {
      setError(err.message);
    }
  };

  // ── Subscribe ──

  const handleSubscribe = async (tierSlug: string) => {
    setError(null);
    try {
      const payment = await subscribe(tierSlug);
      if (payment.confirmation_url) {
        window.location.href = payment.confirmation_url;
      } else {
        // Free tier or mock — refresh subscription
        const sub = await getSubscription();
        setSubscription(sub);
      }
    } catch (err: any) {
      setError(err.message);
    }
  };

  // ── Playground ──

  const handlePlayground = async () => {
    setError(null);
    try {
      const results = await getTopNiches(5);
      setNiches(results);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const rpm = subscription?.requests_per_min ?? 10;

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <h1 className="text-lg font-semibold">NicheFinder DaaS</h1>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-muted-foreground">{user?.email}</span>
            <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded-full">
              {subscription?.tier ?? "free"}
            </span>
            <Button variant="outline" size="sm" onClick={logout}>
              Logout
            </Button>
          </div>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b">
        <div className="max-w-6xl mx-auto px-6 flex gap-6">
          {([
            { key: "keys", label: "API Keys" },
            { key: "billing", label: "Billing" },
            { key: "playground", label: "Playground" },
          ] as const).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600">
            {error}
            <button onClick={() => setError(null)} className="float-right font-bold">&times;</button>
          </div>
        )}

        {activeTab === "keys" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">API Keys</h2>
              <Button onClick={handleCreateKey}>Generate New Key</Button>
            </div>

            {/* New key banner */}
            {newKey && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 space-y-2">
                <p className="text-amber-800 font-medium text-sm">
                  🎉 New API key created!
                </p>
                <pre className="bg-amber-100 rounded p-2 text-xs font-mono break-all select-all">
                  {newKey.raw_key}
                </pre>
                <p className="text-amber-600 text-xs">
                  Copy it now — you won&apos;t see it again!
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setNewKey(null)}
                >
                  Dismiss
                </Button>
              </div>
            )}

            {/* Keys table */}
            {keys.length === 0 ? (
              <p className="text-muted-foreground text-sm py-8 text-center">
                No API keys yet. Generate your first key to get started.
              </p>
            ) : (
              <div className="border rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="text-left px-4 py-3 font-medium">Name</th>
                      <th className="text-left px-4 py-3 font-medium">Key</th>
                      <th className="text-left px-4 py-3 font-medium">Status</th>
                      <th className="text-left px-4 py-3 font-medium">Created</th>
                      <th className="text-left px-4 py-3 font-medium">Last used</th>
                      <th className="text-right px-4 py-3 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {keys.map((key) => (
                      <tr key={key.id} className="hover:bg-muted/30">
                        <td className="px-4 py-3">{key.name}</td>
                        <td className="px-4 py-3 font-mono text-xs">
                          nf_{key.key_prefix}_...
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                              key.is_active
                                ? "bg-green-100 text-green-700"
                                : "bg-gray-100 text-gray-500"
                            }`}
                          >
                            {key.is_active ? "active" : "disabled"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">
                          {new Date(key.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground text-xs">
                          {key.last_used_at
                            ? new Date(key.last_used_at).toLocaleDateString()
                            : "never"}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex gap-2 justify-end">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                updateApiKey(key.id, { is_active: !key.is_active })
                                  .then((updated) =>
                                    setKeys((prev) =>
                                      prev.map((k) =>
                                        k.id === key.id
                                          ? { ...k, is_active: updated.is_active }
                                          : k,
                                      ),
                                    ),
                                  )
                                  .catch((err: any) => setError(err.message))
                              }
                            >
                              {key.is_active ? "Disable" : "Enable"}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-red-500 border-red-200 hover:bg-red-50"
                              onClick={() => handleRevoke(key.id)}
                            >
                              Revoke
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Usage info */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-800">
              <strong>Usage:</strong> Pass your API key in the Authorization header:
              <pre className="mt-1 bg-blue-100 rounded p-2 text-xs font-mono">
                curl -H "Authorization: Bearer nf_&lt;prefix&gt;_&lt;secret&gt;" \
                https://api.nichefinder.com/v1/niches/top
              </pre>
            </div>
          </div>
        )}

        {activeTab === "billing" && (
          <div className="space-y-6">
            <h2 className="text-xl font-semibold">Billing & Plans</h2>

            {/* Current subscription */}
            {subscription && (
              <div className="border rounded-lg p-4">
                <h3 className="font-medium mb-2">Current Plan</h3>
                <p className="text-sm">
                  <span className="text-muted-foreground">Tier:</span>{" "}
                  <strong className="capitalize">{subscription.tier}</strong>
                </p>
                <p className="text-sm">
                  <span className="text-muted-foreground">Rate limit:</span>{" "}
                  {subscription.requests_per_min} req/min
                </p>
                {subscription.expires_at && (
                  <p className="text-sm">
                    <span className="text-muted-foreground">Expires:</span>{" "}
                    {new Date(subscription.expires_at).toLocaleDateString()}
                  </p>
                )}
              </div>
            )}

            {/* Tier cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {tiers.map((tier) => (
                <div
                  key={tier.slug}
                  className={`border rounded-lg p-6 flex flex-col gap-4 ${
                    subscription?.tier === tier.slug
                      ? "border-primary ring-1 ring-primary"
                      : ""
                  }`}
                >
                  <div>
                    <h3 className="font-semibold text-lg">{tier.name}</h3>
                    <p className="text-2xl font-bold mt-2">
                      {tier.price_rub === 0 ? (
                        "Free"
                      ) : (
                        <>
                          {tier.price_rub.toLocaleString()} ₽
                          <span className="text-sm font-normal text-muted-foreground">
                            /mo
                          </span>
                        </>
                      )}
                    </p>
                  </div>
                  <ul className="space-y-2 text-sm">
                    <li className="flex items-center gap-2">
                      <span className="text-green-500">✓</span>
                      {tier.requests_per_min.toLocaleString()} req/min
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="text-green-500">✓</span>
                      {tier.requests_per_month.toLocaleString()} req/month
                    </li>
                    <li className="flex items-center gap-2">
                      <span className="text-green-500">✓</span>
                      Full scoring data & embeddings
                    </li>
                  </ul>
                  <Button
                    variant={
                      subscription?.tier === tier.slug ? "outline" : "default"
                    }
                    disabled={subscription?.tier === tier.slug}
                    onClick={() => handleSubscribe(tier.slug)}
                    className="mt-auto"
                  >
                    {subscription?.tier === tier.slug
                      ? "Current plan"
                      : tier.price_rub === 0
                        ? "Get Started"
                        : "Subscribe"}
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === "playground" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold">Playground</h2>
                <p className="text-sm text-muted-foreground">
                  Test the API and preview niche scoring results ({rpm} req/min
                )
              </div>
              <Button onClick={handlePlayground}>Fetch Top Niches</Button>
            </div>

            {niches ? (
              <div className="space-y-4">
                {niches.items.map((niche, i) => (
                  <div key={i} className="border rounded-lg p-5 space-y-3">
                    <div className="flex items-start justify-between">
                      <div>
                        <h3 className="font-semibold text-lg">
                          {niche.niche_name}
                        </h3>
                        <span className="text-xs bg-muted px-2 py-0.5 rounded-full">
                          {niche.category}
                        </span>
                      </div>
                      <div className="text-right">
                        <div className="text-2xl font-bold text-primary">
                          {niche.overall_score}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          confidence: {niche.confidence}
                        </div>
                      </div>
                    </div>

                    <p className="text-sm text-muted-foreground">
                      {niche.summary_ru}
                    </p>

                    {/* Metrics */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div className="bg-muted/30 rounded p-2 text-center">
                        <div className="text-lg font-semibold">
                          {niche.metrics.yandex_wordstat_requests.toLocaleString()}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Wordstat req/mo
                        </div>
                      </div>
                      <div className="bg-muted/30 rounded p-2 text-center">
                        <div className="text-lg font-semibold">
                          {niche.metrics.vcru_mentions}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          VC.ru mentions
                        </div>
                      </div>
                      <div className="bg-muted/30 rounded p-2 text-center">
                        <div className="text-lg font-semibold">
                          {niche.metrics.pain_point_count}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Pain points
                        </div>
                      </div>
                      <div className="bg-muted/30 rounded p-2 text-center">
                        <div className="text-lg font-semibold">
                          {niche.metrics.competitor_count}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Competitors
                        </div>
                      </div>
                    </div>

                    {/* Pain points */}
                    {niche.pain_points.length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium mb-2">
                          Pain points
                        </h4>
                        <div className="space-y-1">
                          {niche.pain_points.map((pp, j) => (
                            <div
                              key={j}
                              className="text-sm bg-red-50 border border-red-100 rounded p-2"
                            >
                              &ldquo;{pp.text}&rdquo;
                              {pp.author && (
                                <span className="text-xs text-muted-foreground ml-1">
                                  — {pp.author}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Competitors */}
                    {niche.competitors.length > 0 && (
                      <div>
                        <h4 className="text-sm font-medium mb-2">
                          Competitors
                        </h4>
                        <div className="flex flex-wrap gap-2">
                          {niche.competitors.map((comp, j) => (
                            <span
                              key={j}
                              className="text-xs bg-gray-100 rounded-full px-2 py-1"
                            >
                              {comp.name} ({comp.mention_count})
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {niches.has_more && (
                  <p className="text-sm text-muted-foreground text-center">
                    More results available — use the API for pagination
                  </p>
                )}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-muted-foreground text-sm">
                  Click &ldquo;Fetch Top Niches&rdquo; to preview API results
                </p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
