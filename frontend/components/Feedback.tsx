import { cn } from "./cn";

/** Inline loading spinner. Inherits `currentColor`, so it tints to its context. */
export function Spinner({
  size = "sm",
  className,
  ...rest
}: { size?: "sm" | "lg" } & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn("ui-spinner", size === "lg" && "ui-spinner--lg", className)}
      {...rest}
    />
  );
}

/** Shimmer placeholder block. Set width/height via style or className. */
export function Skeleton({
  className,
  style,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn("ui-skeleton", className)}
      style={{ height: 16, ...style }}
      {...rest}
    />
  );
}

export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}

/** Friendly placeholder shown when a list/section has no content yet. */
export function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div className="ui-empty">
      {icon}
      <p className="ui-empty__title">{title}</p>
      {description && <p className="ui-empty__desc">{description}</p>}
      {action}
    </div>
  );
}
