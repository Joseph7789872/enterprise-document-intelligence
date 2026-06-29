import Link from "next/link";
import { LEGAL, TEMPLATE_NOTE } from "@/lib/legal";

export const metadata = { title: "Security — Sales Assistant" };

export default function SecurityPage() {
  return (
    <main>
      <div className="banner warn">{TEMPLATE_NOTE}</div>
      <h1>Security overview</h1>
      <p className="muted">
        How {LEGAL.product} protects your data. For a security questionnaire or the latest details,
        contact {LEGAL.contact}.
      </p>

      <h2>Encryption</h2>
      <ul>
        <li>
          <strong>At rest:</strong> uploaded content, your questions and answers, and stored
          credentials/tokens are encrypted with <strong>AES-256-GCM envelope encryption</strong> — a
          per-record data key wrapped by a master key, with authenticated encryption (tamper
          detection) and per-record key versioning to support rotation.
        </li>
        <li>
          <strong>In transit:</strong> all connections use TLS.
        </li>
      </ul>

      <h2>Authentication &amp; access control</h2>
      <ul>
        <li>Passwords are hashed with <strong>Argon2id</strong> (OWASP-recommended); we never store plaintext.</li>
        <li>Sessions use signed (HS256) JWT access tokens with short lifetimes plus refresh tokens.</li>
        <li>
          <strong>Multi-tenant isolation:</strong> every record is scoped to your tenant, and the
          tenant is derived from the authenticated token — never from client input.
        </li>
        <li>
          <strong>Role-based access</strong> (manager vs. rep) plus <strong>deny-by-default</strong>{" "}
          document-level permissions, and manager-only visibility for sensitive content.
        </li>
      </ul>

      <h2>Auditing</h2>
      <p>
        Every security-sensitive action (logins, uploads, queries, admin changes) is written to an
        <strong> append-only audit log</strong> with no update or delete path, and can be exported
        for your SIEM.
      </p>

      <h2>Secrets &amp; configuration</h2>
      <p>
        Encryption keys and secrets are supplied via the environment, never committed. The
        application <strong>fails fast on startup</strong> if required secrets are missing or weak, so
        a misconfigured deployment never serves traffic.
      </p>

      <h2>Deployment options</h2>
      <p>
        Beyond our multi-tenant cloud, {LEGAL.product} supports <strong>private-cloud and air-gapped
        </strong> deployments that keep all inference on self-hosted models — the app refuses to start
        if any third-party egress is configured in those modes.
      </p>

      <h2>Privacy</h2>
      <p>
        We do not sell your data or use your private content to train shared models. See the{" "}
        <Link href="/privacy">Privacy Policy</Link> and <Link href="/dpa">DPA</Link>.
      </p>

      <p className="muted" style={{ marginTop: 24 }}>
        <Link href="/">← Home</Link>
      </p>
    </main>
  );
}
