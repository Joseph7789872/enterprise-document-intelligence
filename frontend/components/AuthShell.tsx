import Link from "next/link";

export interface AuthShellProps {
  title: string;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  /** Centered links below the card (e.g. "Already have an account?"). */
  footer?: React.ReactNode;
}

/**
 * Centered, branded layout for the unauthenticated auth screens (login, signup,
 * invite acceptance, password reset). Sits inside the root container.
 */
export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <main className="auth">
      <Link href="/" className="auth__brand">
        <span className="ui-header__mark" aria-hidden>
          SA
        </span>
        Sales Assistant
      </Link>
      <h1 className="auth__title">{title}</h1>
      {subtitle && <p className="auth__subtitle">{subtitle}</p>}
      <div className="ui-card auth__card">{children}</div>
      {footer && <div className="auth__footer">{footer}</div>}
    </main>
  );
}
