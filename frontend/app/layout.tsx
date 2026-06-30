import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { LayoutFrame } from "@/components/LayoutFrame";
import "./globals.css";
import "@/components/ui.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

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
    <html lang="en" className={inter.variable}>
      <body>
        <LayoutFrame>{children}</LayoutFrame>
      </body>
    </html>
  );
}
