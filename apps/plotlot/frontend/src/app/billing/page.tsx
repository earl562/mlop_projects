"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface SubscriptionStatus {
  plan: "free" | "pro";
  analyses_used: number;
  analyses_limit: number | null;
}

export default function BillingPage() {
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/subscription/status`, { credentials: "include" })
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false));
  }, []);

  async function handleUpgrade() {
    setCheckoutLoading(true);
    try {
      const res = await fetch("/api/stripe/checkout", { method: "POST" });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } catch {
      setCheckoutLoading(false);
    }
  }

  const isPro = status?.plan === "pro";
  const searchParams =
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search)
      : null;
  const justUpgraded = searchParams?.get("success") === "true";
  const canceled = searchParams?.get("canceled") === "true";

  return (
    <div className="mx-auto max-w-2xl px-6 py-12">
      <h1
        className="mb-2 font-display text-3xl"
        style={{ color: "var(--text-primary)" }}
      >
        Billing
      </h1>
      <p className="mb-8 text-sm" style={{ color: "var(--text-muted)" }}>
        Manage your PlotLot subscription.
      </p>

      {justUpgraded && (
        <div className="mb-6 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800 dark:border-green-800 dark:bg-green-950 dark:text-green-300">
          You&apos;re now on Pro. Unlimited analyses unlocked.
        </div>
      )}

      {canceled && (
        <div className="mb-6 rounded-xl border px-4 py-3 text-sm" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
          Checkout canceled. Your plan was not changed.
        </div>
      )}

      {loading ? (
        <div className="h-32 animate-pulse rounded-xl" style={{ background: "var(--bg-inset)" }} />
      ) : (
        <div
          className="rounded-2xl border p-6"
          style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}
        >
          <div className="mb-6 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                Current plan
              </p>
              <p className="mt-1 text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
                {isPro ? "Pro" : "Free"}
              </p>
            </div>
            <span
              className="rounded-full px-3 py-1 text-xs font-semibold"
              style={
                isPro
                  ? { background: "var(--brand-subtle)", color: "var(--brand)" }
                  : { background: "var(--bg-inset)", color: "var(--text-muted)" }
              }
            >
              {isPro ? "Active" : "Free tier"}
            </span>
          </div>

          {/* Usage bar */}
          <div className="mb-6">
            <div className="mb-1.5 flex items-center justify-between text-xs" style={{ color: "var(--text-muted)" }}>
              <span>Analyses this month</span>
              <span>
                {status?.analyses_used ?? 0}
                {!isPro && ` / ${status?.analyses_limit ?? 5}`}
              </span>
            </div>
            {!isPro && (
              <div className="h-1.5 overflow-hidden rounded-full" style={{ background: "var(--bg-inset)" }}>
                <div
                  className="h-full rounded-full bg-amber-500 transition-all"
                  style={{
                    width: `${Math.min(100, ((status?.analyses_used ?? 0) / (status?.analyses_limit ?? 5)) * 100)}%`,
                  }}
                />
              </div>
            )}
          </div>

          {/* Plan details */}
          <div className="mb-6 space-y-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            {isPro ? (
              <>
                <p>✓ Unlimited analyses</p>
                <p>✓ Document generation (LOI, PSA, Pro Forma)</p>
                <p>✓ AI chat assistant</p>
                <p>✓ Portfolio tracking</p>
              </>
            ) : (
              <>
                <p>✓ 5 analyses/month</p>
                <p>✓ Zoning report, parcel map, 3D view</p>
                <p className="opacity-50">✗ Document generation</p>
                <p className="opacity-50">✗ AI chat assistant</p>
              </>
            )}
          </div>

          {!isPro && (
            <button
              type="button"
              onClick={handleUpgrade}
              disabled={checkoutLoading}
              className="w-full rounded-xl bg-amber-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-amber-700 disabled:opacity-60"
            >
              {checkoutLoading ? "Redirecting…" : "Upgrade to Pro — $49/month"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
