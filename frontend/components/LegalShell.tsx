import Link from "next/link";
import { Banner } from "./Banner";
import { TEMPLATE_NOTE } from "@/lib/legal";

export interface LegalShellProps {
  title: string;
  /** Sub-line under the title (e.g. effective date, or a short summary). */
  meta?: React.ReactNode;
  children: React.ReactNode;
}

/**
 * Shared layout for the legal/trust prose pages (privacy, terms, DPA, security).
 * Renders the template-disclaimer banner, title, meta line, body, and a back link
 * with consistent long-form typography (`.prose`). Server component.
 */
export function LegalShell({ title, meta, children }: LegalShellProps) {
  return (
    <main className="prose">
      <Banner tone="warn" className="prose__note">
        {TEMPLATE_NOTE}
      </Banner>
      <h1>{title}</h1>
      {meta && <p className="prose__meta">{meta}</p>}
      {children}
      <p>
        <Link href="/" className="prose__back">
          ← Back home
        </Link>
      </p>
    </main>
  );
}
