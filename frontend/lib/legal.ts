// Single source of the placeholder identity used across the legal/trust pages. These are
// TEMPLATE values — swap in real values here (one place) before launch, after counsel review.

export const LEGAL = {
  product: "Sales Assistant",
  company: "Sales Assistant",
  jurisdiction: "[JURISDICTION]",
  contact: "legal@[yourdomain]",
  effectiveDate: "[EFFECTIVE DATE]",
} as const;

export const TEMPLATE_NOTE =
  "TEMPLATE — this document is a starting point, not legal advice. Review and adapt it " +
  "with qualified counsel, and fill in the bracketed placeholders, before relying on it.";

// Subprocessors referenced by the Privacy Policy and DPA. Keep this list accurate as the
// stack changes; each entry is a third party that may process customer data.
export const SUBPROCESSORS: { name: string; purpose: string }[] = [
  { name: "OpenAI", purpose: "Embeddings + LLM inference for answering questions" },
  { name: "Stripe", purpose: "Subscription billing and payment processing" },
  { name: "Email/SMTP provider", purpose: "Transactional email (invites, password resets)" },
  { name: "Cloud hosting provider", purpose: "Application + database hosting" },
];
