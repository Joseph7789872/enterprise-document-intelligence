import { AppHeader } from "./AppHeader";
import { cn } from "./cn";
import type { CurrentUser } from "@/lib/api";

export interface AppShellProps {
  user?: CurrentUser | null;
  /** Use the wide container for data-dense pages (admin, analytics). */
  wide?: boolean;
  children: React.ReactNode;
}

/** Authenticated page frame: full-width AppHeader + a centered content column. */
export function AppShell({ user, wide, children }: AppShellProps) {
  return (
    <>
      <AppHeader user={user} />
      <main className={cn("container", wide && "container--wide", "app-main")}>
        {children}
      </main>
    </>
  );
}
