"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { resetPassword } from "@/lib/api";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  // Read ?token= from the URL on mount (avoids useSearchParams' prerender constraints).
  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") ?? "");
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await resetPassword(token, password);
      setDone(true);
      setTimeout(() => router.push("/login"), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>Choose a new password</h1>
      {done ? (
        <div className="card">
          <p>Your password has been reset. Redirecting to sign in…</p>
          <p className="muted">
            <Link href="/login">Sign in now</Link>
          </p>
        </div>
      ) : (
        <form className="card" onSubmit={onSubmit}>
          {!token && <p className="error">Missing reset token. Use the link from your email.</p>}
          <label htmlFor="password">New password (12+ characters)</label>
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
            {busy ? "Resetting…" : "Reset password"}
          </button>
          {error && <p className="error">{error}</p>}
        </form>
      )}
    </main>
  );
}
