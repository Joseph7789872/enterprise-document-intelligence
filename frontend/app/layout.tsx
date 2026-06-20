import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sales Assistant",
  description:
    "Cited, grounded answers from your sales playbooks — ramp new reps fast and prep for objections.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="container">{children}</div>
      </body>
    </html>
  );
}
