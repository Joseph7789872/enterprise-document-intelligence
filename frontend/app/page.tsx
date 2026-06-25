import Link from "next/link";

export default function LandingPage() {
  return (
    <main>
      <span className="badge">For Account Executives</span>
      <h1 style={{ marginTop: 16 }}>Sales Assistant</h1>
      <p className="muted">
        Ask natural-language questions of your team&apos;s sales playbooks — product,
        pricing, ICP, discovery scripts, competitive battlecards, and case studies — and
        get fast, cited, grounded answers. Built for AEs at small SaaS teams.
      </p>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>Two jobs it does well</h2>
        <ul className="muted">
          <li>
            <strong style={{ color: "var(--text)" }}>New-rep ramp</strong> — a curated
            starter checklist that turns into cited answers, so new AEs get productive fast.
          </li>
          <li>
            <strong style={{ color: "var(--text)" }}>Live objection prep</strong> — a
            one-click objection library that draws on your battlecards and case studies.
          </li>
          <li>Every answer is cited and shows its confidence — trustworthy under pressure.</li>
          <li>
            Managers control what&apos;s rep-visible vs. manager-only (e.g. floor pricing).
          </li>
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
