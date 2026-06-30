"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { resetPassword } from "@/lib/api";
import { AuthShell, Button, Input, Banner } from "@/components";

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
    <AuthShell
      title="Choose a new password"
      footer={
        <p>
          <Link href="/login">{done ? "Sign in now" : "Back to sign in"}</Link>
        </p>
      }
    >
      {done ? (
        <Banner tone="success">
          Your password has been reset. Redirecting to sign in…
        </Banner>
      ) : (
        <form onSubmit={onSubmit}>
          {!token && (
            <Banner tone="warn" style={{ marginBottom: "var(--space-md)" }}>
              Missing reset token. Use the link from your email.
            </Banner>
          )}
          <Input
            label="New password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            minLength={12}
            helper="At least 12 characters."
            required
          />
          <Button
            type="submit"
            block
            loading={busy}
            disabled={!token}
            className="auth__actions"
          >
            {busy ? "Resetting…" : "Reset password"}
          </Button>
          {error && (
            <Banner tone="error" style={{ marginTop: "var(--space-md)" }}>
              {error}
            </Banner>
          )}
        </form>
      )}
    </AuthShell>
  );
}
