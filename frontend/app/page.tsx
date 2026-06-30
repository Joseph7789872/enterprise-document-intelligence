import Link from "next/link";
import { Card } from "@/components";

interface Feature {
  title: string;
  body: string;
  icon: React.ReactNode;
}

const FEATURES: Feature[] = [
  {
    title: "New-rep ramp",
    body: "A manager-curated starter checklist turns into cited answers, so new AEs get productive fast.",
    icon: (
      <path d="M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    ),
  },
  {
    title: "Live objection prep",
    body: "A one-click objection library draws on your battlecards and case studies — answers in seconds.",
    icon: (
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    ),
  },
  {
    title: "Cited & honest",
    body: "Every answer shows its sources and confidence — and says so plainly when it isn't sure.",
    icon: (
      <>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="M9 12l2 2 4-4" />
      </>
    ),
  },
  {
    title: "Manager controls",
    body: "Decide what's rep-visible vs. manager-only (e.g. floor pricing) — enforced at retrieval time.",
    icon: (
      <>
        <rect x="3" y="11" width="18" height="11" rx="2" />
        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
      </>
    ),
  },
];

function FeatureIcon({ children }: { children: React.ReactNode }) {
  return (
    <span className="lp-feature__icon">
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        {children}
      </svg>
    </span>
  );
}

export default function LandingPage() {
  return (
    <main>
      <nav className="lp-nav">
        <span className="auth__brand" style={{ margin: 0 }}>
          <span className="ui-header__mark" aria-hidden>
            SA
          </span>
          Sales Assistant
        </span>
        <span className="lp-nav__actions">
          <Link href="/login" className="ui-btn ui-btn--ghost ui-btn--sm">
            Sign in
          </Link>
          <Link href="/signup" className="ui-btn ui-btn--primary ui-btn--sm">
            Get started
          </Link>
        </span>
      </nav>

      <section className="lp-hero">
        <span className="badge lp-hero__eyebrow">For Account Executives</span>
        <h1 className="lp-hero__title">Your sales playbook, on demand</h1>
        <p className="lp-hero__sub">
          Ask natural-language questions of your team&apos;s sales knowledge — product,
          pricing, ICP, discovery scripts, competitive battlecards, and case studies — and
          get fast, cited, grounded answers. Built for AEs at small SaaS teams.
        </p>
        <div className="lp-hero__cta">
          <Link href="/signup" className="ui-btn ui-btn--primary ui-btn--lg">
            Create your workspace
          </Link>
          <Link href="/login" className="ui-btn ui-btn--secondary ui-btn--lg">
            Sign in
          </Link>
        </div>
      </section>

      <section className="lp-features" aria-label="What it does">
        {FEATURES.map((f) => (
          <Card key={f.title}>
            <FeatureIcon>{f.icon}</FeatureIcon>
            <h2 className="lp-feature__title">{f.title}</h2>
            <p className="lp-feature__body">{f.body}</p>
          </Card>
        ))}
      </section>

      <p className="muted" style={{ marginTop: "var(--space-2xl)", fontSize: "0.85rem" }}>
        This is a focused reference UI. API docs live at <code>/docs</code> on your backend
        deployment.
      </p>
    </main>
  );
}
