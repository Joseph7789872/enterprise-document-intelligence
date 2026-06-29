import Link from "next/link";
import { LEGAL, SUBPROCESSORS, TEMPLATE_NOTE } from "@/lib/legal";

export const metadata = { title: "Data Processing Addendum — Sales Assistant" };

export default function DpaPage() {
  return (
    <main>
      <div className="banner warn">{TEMPLATE_NOTE}</div>
      <h1>Data Processing Addendum</h1>
      <p className="muted">Effective date: {LEGAL.effectiveDate}</p>
      <p>
        This Data Processing Addendum (&ldquo;DPA&rdquo;) forms part of the agreement between you
        (&ldquo;Controller&rdquo;) and {LEGAL.company} (&ldquo;Processor&rdquo;) for {LEGAL.product}.
        It applies where we process personal data on your behalf.
      </p>

      <h2>Roles &amp; scope</h2>
      <p>
        You are the controller of the personal data within your content and accounts; we act as
        processor and process it only on your documented instructions to provide the Service.
      </p>

      <h2>Nature of processing</h2>
      <p>
        Storage, encryption, indexing/embedding, retrieval, and AI-assisted answering of the content
        your team uploads and the questions it asks, plus account and security processing.
      </p>

      <h2>Subprocessors</h2>
      <p>You authorize the following subprocessors; we remain responsible for their compliance:</p>
      <ul>
        {SUBPROCESSORS.map((s) => (
          <li key={s.name}>
            <strong>{s.name}</strong> — {s.purpose}
          </li>
        ))}
      </ul>
      <p>We will give notice of new subprocessors so you have an opportunity to object.</p>

      <h2>Security measures</h2>
      <p>
        We maintain technical and organizational measures including AES-256-GCM encryption at rest,
        TLS in transit, Argon2id password hashing, multi-tenant isolation with role-based access and
        deny-by-default document permissions, and an append-only audit trail. See the{" "}
        <Link href="/security">Security overview</Link>.
      </p>

      <h2>Data-subject requests</h2>
      <p>
        We will assist you in responding to data-subject requests (access, export, correction,
        erasure), including via in-product tooling, taking into account the nature of processing.
      </p>

      <h2>Personal-data breach</h2>
      <p>We will notify you without undue delay after becoming aware of a personal-data breach affecting your data.</p>

      <h2>Return &amp; deletion</h2>
      <p>
        On termination, we return or delete your personal data, except where retention is required
        on a legal basis (e.g. immutable security audit logs retained as security records).
      </p>

      <h2>Contact</h2>
      <p>Data-protection inquiries: {LEGAL.contact}.</p>

      <p className="muted" style={{ marginTop: 24 }}>
        <Link href="/">← Home</Link>
      </p>
    </main>
  );
}
