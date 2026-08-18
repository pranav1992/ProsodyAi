import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoAce Voice Tone & Noise Dashboard",
  description: "Emotional tone and background noise analysis for production call audio",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <div className="mx-auto max-w-6xl px-6 py-8">{children}</div>
      </body>
    </html>
  );
}
