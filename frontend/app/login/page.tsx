"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { login } from "@/lib/api";
import { AuthShell, Button, Input, Banner } from "@/components";

export default function LoginPage() {
  const router = useRouter();
  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(tenantSlug, email, password);
      router.push("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Sign in"
      subtitle="Use the credentials of a registered workspace user."
      footer={
        <>
          <p>
            <Link href="/forgot-password">Forgot password?</Link> · New here?{" "}
            <Link href="/signup">Create an account</Link>
          </p>
          <p>
            Have an invite key? <Link href="/accept-invite">Join your workspace</Link>
          </p>
        </>
      }
    >
      <form onSubmit={onSubmit}>
        <Input
          label="Workspace identifier"
          value={tenantSlug}
          onChange={(e) => setTenantSlug(e.target.value)}
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
        <Input
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
        <Button type="submit" block loading={busy} className="auth__actions">
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        {error && (
          <Banner tone="error" style={{ marginTop: "var(--space-md)" }}>
            {error}
          </Banner>
        )}
      </form>
    </AuthShell>
  );
}
