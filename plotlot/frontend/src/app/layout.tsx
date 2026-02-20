import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PlotLot - AI Zoning Analysis",
  description:
    "AI-powered zoning analysis for South Florida real estate. Covers 104 municipalities across Miami-Dade, Broward, and Palm Beach counties.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} min-h-screen bg-[#f7f5f2] font-sans antialiased`}
      >
        {/* Top nav */}
        <nav className="sticky top-0 z-50 border-b border-stone-200 bg-white/80 backdrop-blur-lg">
          <div className="mx-auto flex h-12 max-w-3xl items-center justify-between px-4">
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-800 text-xs font-black text-white">
                P
              </div>
              <span className="text-lg font-bold tracking-tight text-stone-800">PlotLot</span>
              <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">
                Beta
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-stone-400">104 municipalities</span>
            </div>
          </div>
        </nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
