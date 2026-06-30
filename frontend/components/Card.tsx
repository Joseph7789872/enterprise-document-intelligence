import { cn } from "./cn";

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  interactive?: boolean;
}

/** Surface panel. Pass `interactive` only when the whole card is clickable. */
export function Card({ interactive, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn("ui-card", interactive && "ui-card--interactive", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

export interface CardHeaderProps {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Right-aligned slot for actions (buttons, menu). */
  action?: React.ReactNode;
}

export function CardHeader({ title, description, action }: CardHeaderProps) {
  return (
    <div className="ui-card__header">
      <div>
        <h3 className="ui-card__title">{title}</h3>
        {description && <p className="ui-card__desc">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export interface StatCardProps {
  label: string;
  value: React.ReactNode;
  hint?: string;
}

/** Compact KPI card for the analytics dashboard. */
export function StatCard({ label, value, hint }: StatCardProps) {
  return (
    <div className="ui-stat">
      <p className="ui-stat__label">{label}</p>
      <p className="ui-stat__value">{value}</p>
      {hint && <p className="ui-stat__hint">{hint}</p>}
    </div>
  );
}
