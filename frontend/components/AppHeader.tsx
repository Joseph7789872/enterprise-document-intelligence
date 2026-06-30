"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "./cn";
import { Button } from "./Button";
import { clearToken, isManager, type CurrentUser } from "@/lib/api";

interface NavLink {
  href: string;
  label: string;
  managerOnly?: boolean;
}

const NAV: NavLink[] = [
  { href: "/app", label: "Ask" },
  { href: "/ramp", label: "Ramp" },
  { href: "/log", label: "Q&A Log" },
  { href: "/admin", label: "Admin", managerOnly: true },
  { href: "/analytics", label: "Analytics", managerOnly: true },
];

export interface AppHeaderProps {
  /** Current user — drives which manager-only links show and the email label. */
  user?: CurrentUser | null;
}

/**
 * Shared top navigation for all authenticated pages. Replaces the per-page
 * hand-rolled header each page used to duplicate inline. Highlights the active
 * route, gates Admin/Analytics behind manager roles, and owns sign-out.
 */
export function AppHeader({ user }: AppHeaderProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const manager = user ? isManager(user.role) : false;
  const links = NAV.filter((l) => !l.managerOnly || manager);

  function signOut() {
    clearToken();
    router.push("/login");
  }

  const isActive = (href: string) =>
    pathname === href || pathname?.startsWith(`${href}/`);

  return (
    <header className="ui-header">
      <div className="ui-header__inner">
        <Link href="/app" className="ui-header__brand">
          <span className="ui-header__mark" aria-hidden>
            SA
          </span>
          Sales Assistant
        </Link>

        <nav
          className={cn("ui-header__nav", open && "ui-header__nav--open")}
          aria-label="Primary"
        >
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="ui-header__link"
              aria-current={isActive(l.href) ? "page" : undefined}
              onClick={() => setOpen(false)}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="ui-header__spacer" />

        {user && <span className="ui-header__email">{user.email}</span>}
        <Button variant="ghost" size="sm" onClick={signOut}>
          Sign out
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="ui-header__toggle"
          aria-label="Toggle navigation"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden
          >
            {open ? (
              <>
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </>
            ) : (
              <>
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </>
            )}
          </svg>
        </Button>
      </div>
    </header>
  );
}
