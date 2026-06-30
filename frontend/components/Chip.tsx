import { cn } from "./cn";

export interface ChipProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean;
}

/** Clickable pill — one-click objection/ramp prompts, segment toggles. */
export function Chip({ selected, className, children, ...rest }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn("ui-chip", selected && "ui-chip--selected", className)}
      {...rest}
    >
      {children}
    </button>
  );
}

type BadgeTone = "neutral" | "success" | "warning" | "danger";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

/** Non-interactive status pill (document status, query state). */
export function Badge({
  tone = "neutral",
  className,
  children,
  ...rest
}: BadgeProps) {
  return (
    <span
      className={cn(
        "ui-badge",
        tone !== "neutral" && `ui-badge--${tone}`,
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
