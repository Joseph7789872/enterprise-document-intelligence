import Link from "next/link";

export default function LandingPage() {
  return (
    <main>
      <span className="badge">Enterprise · Security-first</span>
      <h1 style={{ marginTop: 16 }}>Document Intelligence Platform</h1>
      <p className="muted">
        Ask questions of your private company documents and get cited, grounded answers —
        with encryption at rest, document-level access control, a full audit trail, and the
        option to keep everything on self-hosted models for confidential material.
      </p>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Why teams choose it</h2>
        <ul className="muted">
          <li>Envelope encryption (AES-256-GCM) and retrieval-time ACL enforcement</li>
          <li>Multi-agent workflow with human approval for low-confidence answers</li>
          <li>Append-only audit log on every document access and query</li>
          <li>Deploy as SaaS, single-tenant, private cloud, or fully air-gapped</li>
        </ul>
        <Link href="/login">
          <button>Open the app →</button>
        </Link>
      </div>

      <p className="muted" style={{ marginTop: 24, fontSize: "0.85rem" }}>
        This is a minimal reference UI. See the API docs at <code>/docs</code> on your
        backend deployment.
      </p>
    </main>
  );
}
