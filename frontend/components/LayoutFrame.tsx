"use client";

import { usePathname } from "next/navigation";
import { SiteFooter } from "./SiteFooter";

// Routes that render their own chrome (full-width AppHeader + their own
// container via AppShell) and therefore opt out of the global container/footer.
// This list grows as each app surface is migrated to the new component system.
const SELF_MANAGED = ["/app", "/ramp", "/log"];

/**
 * Wraps page content. Self-managed app routes are rendered bare (they bring
 * their own AppShell); every other route gets the centered container + footer
 * the pre-redesign pages expect. Keeps unmigrated pages working while the
 * redesign rolls out phase by phase.
 */
export function LayoutFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const selfManaged = SELF_MANAGED.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );

  if (selfManaged) return <>{children}</>;

  return (
    <div className="container">
      {children}
      <SiteFooter />
    </div>
  );
}
