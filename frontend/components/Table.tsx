import { cn } from "./cn";

/**
 * Lightweight table primitives. `Table` wraps the element in a horizontally
 * scrollable, bordered container so dense data never forces the page to scroll.
 *
 * Usage:
 *   <Table>
 *     <thead><tr><Th>Rep</Th><Th numeric>Queries</Th></tr></thead>
 *     <tbody><tr><Td>...</Td><Td numeric>12</Td></tr></tbody>
 *   </Table>
 */
export function Table({
  className,
  children,
  ...rest
}: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="ui-table-wrap">
      <table className={cn("ui-table", className)} {...rest}>
        {children}
      </table>
    </div>
  );
}

export function Th({
  numeric,
  className,
  children,
  ...rest
}: { numeric?: boolean } & React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th className={cn(numeric && "ui-table__num", className)} {...rest}>
      {children}
    </th>
  );
}

export function Td({
  numeric,
  className,
  children,
  ...rest
}: { numeric?: boolean } & React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn(numeric && "ui-table__num", className)} {...rest}>
      {children}
    </td>
  );
}
