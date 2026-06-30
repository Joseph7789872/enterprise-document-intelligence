"use client";

import Link from "next/link";
import { useState } from "react";
import { forgotPassword } from "@/lib/api";
import { AuthShell, Button, Input, Banner } from "@/components";

export default function ForgotPasswordPage() {
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await forgotPassword(tenantSlug, email);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle={sent ? undefined : "Enter your workspace and email and we'll send a reset link."}
      footer={
        <p>
          <Link href="/login">Back to sign in</Link>
        </p>
      }
    >
      {sent ? (
        <Banner tone="success">
          If an account exists for that email, we&apos;ve sent a reset link. Check your
          inbox.
        </Banner>
      ) : (
        <form onSubmit={onSubmit}>
          <Input
            label="Workspace identifier"
            value={tenantSlug}
            onChange={(e) => setTenantSlug(e.target.value.toLowerCase())}
            placeholder="acme"
            autoComplete="organization"
            required
          />
          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="username"
            required
          />
          <Button type="submit" block loading={busy} className="auth__actions">
            {busy ? "Sending…" : "Send reset link"}
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
