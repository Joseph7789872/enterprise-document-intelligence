import type { Metadata } from "next";
import Link from "next/link";
import { LEGAL } from "@/lib/legal";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sales Assistant",
  description:
    "Cited, grounded answers from your sales playbooks — ramp new reps fast and prep for objections.",
};

// Minimal, undesigned footer so the legal/trust pages are discoverable. The design pass
// will restyle this.
function SiteFooter() {
  return (
    <footer
      className="muted"
      style={{
        marginTop: 48,
        paddingTop: 16,
        borderTop: "1px solid var(--border)",
        fontSize: "0.85rem",
        display: "flex",
        gap: 12,
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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="container">
          {children}
          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
