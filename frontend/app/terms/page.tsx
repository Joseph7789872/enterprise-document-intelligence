import Link from "next/link";
import { LEGAL } from "@/lib/legal";
import { LegalShell } from "@/components";

export const metadata = { title: "Terms of Service — Sales Assistant" };

export default function TermsPage() {
  return (
    <LegalShell
      title="Terms of Service"
      meta={`Effective date: ${LEGAL.effectiveDate}`}
    >
      <p>
        These Terms govern your use of {LEGAL.product} (the &ldquo;Service&rdquo;), provided by{" "}
        {LEGAL.company}. By creating a workspace or using the Service, you agree to these Terms.
      </p>

      <h2>Accounts &amp; eligibility</h2>
      <p>
        You must provide accurate information and are responsible for activity under your account
        and for keeping your credentials secure. You must be authorized to bind your organization.
      </p>

      <h2>Acceptable use</h2>
      <ul>
        <li>Do not upload content you lack the rights to use.</li>
        <li>Do not attempt to breach tenant isolation, access other customers&rsquo; data, or disrupt the Service.</li>
        <li>Do not use the Service for unlawful purposes or to violate others&rsquo; rights.</li>
      </ul>

      <h2>Your content</h2>
      <p>
        You retain all ownership of the content your team uploads. You grant us a limited license to
        process and store that content solely to provide the Service to you (see the{" "}
        <Link href="/privacy">Privacy Policy</Link> and <Link href="/dpa">DPA</Link>).
      </p>

      <h2>AI-generated answers</h2>
      <p>
        The Service returns AI-generated, citation-grounded answers. These are informational aids
        and may be incomplete or wrong. Verify important answers against the cited sources before
        relying on them; you are responsible for decisions made using the Service.
      </p>

      <h2>Disclaimers &amp; liability</h2>
      <p>
        The Service is provided &ldquo;as is&rdquo; without warranties of any kind. To the maximum
        extent permitted by law, {LEGAL.company} is not liable for indirect or consequential
        damages, and our total liability is limited to the amounts you paid for the Service in the
        12 months preceding the claim.
      </p>

      <h2>Suspension &amp; termination</h2>
      <p>
        You may stop using the Service at any time. We may suspend or terminate access for breach of
        these Terms or to protect the Service. On termination, we handle your data as described in
        the <Link href="/privacy">Privacy Policy</Link>.
      </p>

      <h2>Governing law</h2>
      <p>These Terms are governed by the laws of {LEGAL.jurisdiction}, without regard to conflict-of-law rules.</p>

      <h2>Contact</h2>
      <p>Questions about these Terms: {LEGAL.contact}.</p>
    </LegalShell>
  );
}
