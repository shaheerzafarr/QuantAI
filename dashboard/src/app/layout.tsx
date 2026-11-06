import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuantAI - Autonomous Quantitative Trading & Intelligence Platform",
  description: "Next-generation institutional cryptocurrency trading and multi-agent intelligence ecosystem",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased selection:bg-blue-600 selection:text-white">
        {children}
      </body>
    </html>
  );
}
