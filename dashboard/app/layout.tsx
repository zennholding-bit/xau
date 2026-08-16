import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "XAU — Signal Terminal",
  description: "Paper trading & signal terminal för XAU/USD",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="sv">
      <body>{children}</body>
    </html>
  );
}
