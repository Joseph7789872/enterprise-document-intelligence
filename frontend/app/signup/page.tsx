"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { register } from "@/lib/api";
import { AuthShell, Button, Input, Banner } from "@/components";

export default function SignupPage() {
  const router = useRouter();
  const [tenantName, setTenantName] = useState("");
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
      await register(tenantName, tenantSlug, email, password);
      router.push("/app");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Create your workspace"
      subtitle="Start a free trial — no credit card required."
      footer={
        <p>
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      }
    >
      <form onSubmit={onSubmit}>
        <Input
          label="Company name"
          value={tenantName}
          onChange={(e) => setTenantName(e.target.value)}
          placeholder="Acme Inc."
          required
        />
        <Input
          label="Workspace identifier"
          value={tenantSlug}
          onChange={(e) => setTenantSlug(e.target.value.toLowerCase())}
          placeholder="acme"
          pattern="[a-z0-9][-a-z0-9]*"
          autoComplete="organization"
          helper="Lowercase letters, numbers, and hyphens. Your team uses this to sign in."
          required
        />
        <Input
          label="Your email"
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
          autoComplete="new-password"
          minLength={12}
          helper="At least 12 characters."
          required
        />
        <Button type="submit" block loading={busy} className="auth__actions">
          {busy ? "Creating…" : "Create workspace"}
        </Button>
        {error && (
          <Banner tone="error" style={{ marginTop: "var(--space-md)" }}>
            {error}
          </Banner>
        )}
        <p className="muted" style={{ marginTop: "var(--space-md)", fontSize: "0.8rem" }}>
          By creating a workspace you agree to the <Link href="/terms">Terms</Link> and{" "}
          <Link href="/privacy">Privacy Policy</Link>.
        </p>
      </form>
    </AuthShell>
  );
}
