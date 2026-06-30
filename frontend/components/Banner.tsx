import { cn } from "./cn";

type Tone = "info" | "warn" | "error" | "success";

export interface BannerProps extends React.HTMLAttributes<HTMLDivElement> {
  tone?: Tone;
}

/**
 * Inline contextual message. Used for the honest low-confidence answer notice,
 * form-level errors, and success confirmations. Errors get role="alert" so
 * screen readers announce them.
 */
export function Banner({
  tone = "info",
  className,
  children,
  ...rest
}: BannerProps) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn("ui-banner", `ui-banner--${tone}`, className)}
      {...rest}
    >
      <div className="ui-banner__body">{children}</div>
    </div>
  );
}
