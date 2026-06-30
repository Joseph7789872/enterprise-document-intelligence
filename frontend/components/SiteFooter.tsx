import Link from "next/link";
import { LEGAL } from "@/lib/legal";

/** Shared site footer — legal/trust links, discoverable from every non-app page. */
export function SiteFooter() {
  return (
    <footer
      className="muted"
      style={{
        marginTop: "var(--space-3xl)",
        paddingTop: "var(--space-lg)",
        borderTop: "1px solid var(--color-border)",
        fontSize: "var(--text-sm)",
        display: "flex",
        gap: "var(--space-lg)",
        alignItems: "center",
        flexWrap: "wrap",
      }}
    >
      <Link href="/privacy">Privacy</Link>
      <Link href="/terms">Terms</Link>
      <Link href="/dpa">DPA</Link>
      <Link href="/security">Security</Link>
      <span style={{ marginLeft: "auto" }}>© {LEGAL.company}</span>
    </footer>
  );
}
