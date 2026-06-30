// Tiny classnames joiner — filters falsy values. Avoids a dependency for the
// handful of conditional class joins the shared components need.
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
