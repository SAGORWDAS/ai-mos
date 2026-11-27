import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI-MOS",
  description: "AI marketing, sales and business growth operating system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
