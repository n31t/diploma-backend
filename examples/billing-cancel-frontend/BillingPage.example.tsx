/**
 * Example billing page: subscription status, cancel at period end, resume, portal.
 * Copy into your Next.js/React app; point API_BASE at your backend (e.g. NEXT_PUBLIC_API_URL).
 *
 * Assumes Bearer auth (same as rest of app). Adjust fetch paths if you use a proxy.
 */

"use client";

import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

type BillingErrorBody = { detail?: string; code?: string };

export type SubscriptionStatus = {
  is_premium: boolean;
  status: string | null;
  plan_type: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean | null;
  stripe_subscription_id: string | null;
};

type BillingActionResponse = {
  status: string;
  message: string;
  sync_pending: boolean;
  already_scheduled: boolean;
};

async function authHeaders(): Promise<HeadersInit> {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function getSubscription(): Promise<SubscriptionStatus> {
  const res = await fetch(`${API_BASE}/billing/subscription`, {
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error(`subscription ${res.status}`);
  return res.json();
}

async function postCancel(): Promise<BillingActionResponse | BillingErrorBody> {
  const res = await fetch(`${API_BASE}/billing/cancel`, {
    method: "POST",
    headers: await authHeaders(),
  });
  const data = await res.json();
  if (!res.ok) return data as BillingErrorBody;
  return data as BillingActionResponse;
}

async function postResume(): Promise<BillingActionResponse | BillingErrorBody> {
  const res = await fetch(`${API_BASE}/billing/resume`, {
    method: "POST",
    headers: await authHeaders(),
  });
  const data = await res.json();
  if (!res.ok) return data as BillingErrorBody;
  return data as BillingActionResponse;
}

async function postPortal(): Promise<{ url: string }> {
  const res = await fetch(`${API_BASE}/billing/portal`, {
    method: "POST",
    headers: await authHeaders(),
  });
  if (!res.ok) throw new Error("portal");
  return res.json();
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function BillingPageExample() {
  const [sub, setSub] = useState<SubscriptionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await getSubscription();
      setSub(s);
    } catch {
      setError("Could not load subscription");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const showCancel =
    sub?.is_premium &&
    sub.status &&
    ["active", "trialing"].includes(sub.status) &&
    !sub.cancel_at_period_end;

  const showResume =
    sub?.is_premium &&
    sub.cancel_at_period_end &&
    sub.status &&
    ["active", "trialing"].includes(sub.status);

  async function onConfirmCancel() {
    setBusy(true);
    setBanner(null);
    setError(null);
    try {
      const r = await postCancel();
      if ("code" in r && r.code) {
        setError(`${r.code}: ${r.detail ?? ""}`);
        setConfirmCancel(false);
        return;
      }
      const ok = r as BillingActionResponse;
      setBanner(
        ok.sync_pending
          ? "Cancellation requested. Updating status… (wait for webhooks)"
          : ok.message,
      );
      setConfirmCancel(false);
      await refresh();
    } catch {
      setError("Cancel failed");
    } finally {
      setBusy(false);
    }
  }

  async function onResume() {
    setBusy(true);
    setBanner(null);
    setError(null);
    try {
      const r = await postResume();
      if ("code" in r && r.code) {
        setError(`${r.code}: ${r.detail ?? ""}`);
        return;
      }
      setBanner("Resume requested. Updating status…");
      await refresh();
    } catch {
      setError("Resume failed");
    } finally {
      setBusy(false);
    }
  }

  async function onPortal() {
    try {
      const { url } = await postPortal();
      window.location.href = url;
    } catch {
      setError("Could not open billing portal");
    }
  }

  if (loading && !sub) return <p>Loading…</p>;

  return (
    <div style={{ maxWidth: 560, padding: 24 }}>
      <h1>Billing</h1>

      {error && (
        <p role="alert" style={{ color: "crimson" }}>
          {error}
        </p>
      )}
      {banner && (
        <p style={{ background: "#eef", padding: 12, borderRadius: 8 }}>{banner}</p>
      )}

      <section style={{ marginTop: 16 }}>
        <p>
          <strong>Premium:</strong> {sub?.is_premium ? "Yes" : "No"}
        </p>
        <p>
          <strong>Plan:</strong> {sub?.plan_type ?? "—"}
        </p>
        <p>
          <strong>Status:</strong> {sub?.status ?? "—"}
        </p>
        <p>
          <strong>Current period ends:</strong> {formatDate(sub?.current_period_end ?? null)}
        </p>
        <p>
          <strong>Cancellation scheduled:</strong>{" "}
          {sub?.cancel_at_period_end ? "Yes" : "No"}
        </p>
      </section>

      {sub?.cancel_at_period_end && sub?.is_premium && (
        <p style={{ marginTop: 16 }}>
          Your subscription will end on {formatDate(sub.current_period_end)}. You keep Premium
          until then.
        </p>
      )}

      <div style={{ marginTop: 24, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => void refresh()} disabled={busy}>
          Refresh
        </button>
        {showCancel && (
          <button type="button" onClick={() => setConfirmCancel(true)} disabled={busy}>
            Cancel subscription
          </button>
        )}
        {showResume && (
          <button type="button" onClick={() => void onResume()} disabled={busy}>
            Resume subscription
          </button>
        )}
        <button type="button" onClick={() => void onPortal()} disabled={busy}>
          Manage in Stripe portal
        </button>
      </div>

      {confirmCancel && (
        <div
          role="dialog"
          aria-modal
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
        >
          <div
            style={{
              background: "#fff",
              padding: 24,
              borderRadius: 8,
              maxWidth: 420,
            }}
          >
            <h2>Cancel subscription?</h2>
            <p>
              You will keep Premium until the end of your current billing period (
              {formatDate(sub?.current_period_end ?? null)}). After that, your account will
              move to the free tier unless you resume the subscription before then.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button type="button" onClick={() => setConfirmCancel(false)} disabled={busy}>
                Keep subscription
              </button>
              <button type="button" onClick={() => void onConfirmCancel()} disabled={busy}>
                Confirm cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
