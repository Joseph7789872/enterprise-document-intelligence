"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { acceptInvite } from "@/lib/api";

export default function AcceptInvitePage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") ?? "");
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await acceptInvite(token, password);
      router.push("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not accept invitation");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Join your team</h1>
      <p className="muted">Set a password to accept your invitation and get started.</p>
      <form className="card" onSubmit={onSubmit}>
        {!token && <p className="error">Missing invite token. Use the link from your email.</p>}
        <label htmlFor="password">Choose a password (12+ characters)</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          minLength={12}
          required
        />
        <button type="submit" disabled={busy || !token}>
          {busy ? "Joining…" : "Accept invitation"}
        </button>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  );
}
