import Link from "next/link";
import { LEGAL, SUBPROCESSORS, TEMPLATE_NOTE } from "@/lib/legal";

export const metadata = { title: "Privacy Policy — Sales Assistant" };

export default function PrivacyPage() {
  return (
    <main>
      <div className="banner warn">{TEMPLATE_NOTE}</div>
      <h1>Privacy Policy</h1>
      <p className="muted">Effective date: {LEGAL.effectiveDate}</p>
      <p>
        This Privacy Policy explains how {LEGAL.company} (&ldquo;we&rdquo;) collects, uses, and
        protects information when you use {LEGAL.product} (the &ldquo;Service&rdquo;).
      </p>

      <h2>Information we collect</h2>
      <ul>
        <li>
          <strong>Account information</strong> — your name, work email, organization, and password
          (stored only as an Argon2id hash, never in plaintext).
        </li>
        <li>
          <strong>Content you upload</strong> — the sales playbooks, pricing, scripts, and other
          documents your team adds, and the questions your team asks the assistant.
        </li>
        <li>
          <strong>Usage and security data</strong> — audit events (logins, uploads, queries),
          IP address, and timestamps, used for security and to power your team analytics.
        </li>
        <li>
          <strong>Billing data</strong> — handled by our payment processor; we do not store full
          card numbers.
        </li>
      </ul>

      <h2>How we use information</h2>
      <ul>
        <li>To provide the Service: ingest your content and return cited, grounded answers.</li>
        <li>To secure the Service and maintain an audit trail.</li>
        <li>To operate billing and communicate with you (invites, password resets, notices).</li>
      </ul>
      <p>
        We do not sell your data, and we do not use your private content to train shared or
        third-party models.
      </p>

      <h2>Encryption &amp; security</h2>
      <p>
        Uploaded content and your questions/answers are encrypted at rest using AES-256-GCM
        envelope encryption, and all traffic is encrypted in transit (TLS). See our{" "}
        <Link href="/security">Security overview</Link> for details.
      </p>

      <h2>Subprocessors</h2>
      <p>We use a small set of vetted third parties to operate the Service:</p>
      <ul>
        {SUBPROCESSORS.map((s) => (
          <li key={s.name}>
            <strong>{s.name}</strong> — {s.purpose}
          </li>
        ))}
      </ul>

      <h2>Data retention &amp; deletion</h2>
      <p>
        We retain your content for as long as your account is active. You can delete documents at
        any time, and we delete or anonymize your data on account termination, except records we
        must retain on a legal basis (e.g. immutable security audit logs). Your browser stores a
        session token in <code>localStorage</code>; signing out clears it.
      </p>

      <h2>Your rights</h2>
      <p>
        Depending on your jurisdiction, you may have rights to access, export, correct, or erase
        your personal data. To exercise them, contact us at {LEGAL.contact}.
      </p>

      <h2>Contact</h2>
      <p>Questions about this policy: {LEGAL.contact}.</p>

      <p className="muted" style={{ marginTop: 24 }}>
        <Link href="/">← Home</Link>
      </p>
    </main>
  );
}
