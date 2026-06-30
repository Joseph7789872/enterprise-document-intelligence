import { cn } from "./cn";

export interface TabItem<T extends string = string> {
  value: T;
  label: React.ReactNode;
}

export interface TabsProps<T extends string = string> {
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  "aria-label"?: string;
  className?: string;
}

/** Segmented control for switching views (Ask / Objection lookup, date ranges). */
export function Tabs<T extends string = string>({
  items,
  value,
  onChange,
  className,
  ...rest
}: TabsProps<T>) {
  return (
    <div role="tablist" className={cn("ui-tabs", className)} {...rest}>
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          type="button"
          aria-selected={it.value === value}
          className="ui-tab"
          onClick={() => onChange(it.value)}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}
