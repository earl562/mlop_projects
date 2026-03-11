import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import { ThemeProvider, ThemeToggle } from "@/components/ThemeProvider";
import { ToastProvider } from "@/components/Toast";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  weight: "400",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PlotLot - AI Zoning Analysis",
  description:
    "AI-powered zoning analysis for South Florida real estate. Covers 104 municipalities across Miami-Dade, Broward, and Palm Beach counties.",
  openGraph: {
    title: "PlotLot - AI Zoning Analysis",
    description:
      "Enter any address in South Florida and get instant zoning analysis: density limits, setbacks, allowable uses, and max buildable units.",
    siteName: "PlotLot",
    type: "website",
    url: "https://mlopprojects.vercel.app",
  },
  twitter: {
    card: "summary_large_image",
    title: "PlotLot - AI Zoning Analysis",
    description:
      "AI-powered zoning analysis for South Florida real estate. Instant density, setback, and use analysis for 104 municipalities.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var mode = localStorage.getItem('theme');
                  if (mode === 'dark' || (!mode && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
                    document.documentElement.classList.add('dark');
                  }
                } catch(e) {}
              })();
            `,
          }}
        />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${instrumentSerif.variable} min-h-screen bg-[var(--bg-primary)] font-sans antialiased`}
      >
        <ThemeProvider>
          {/* Floating pill nav */}
          <div className="fixed left-1/2 top-4 z-50 -translate-x-1/2">
            <nav
              className="flex items-center gap-3 rounded-full border bg-[var(--nav-bg)] px-4 py-2 backdrop-blur-xl transition-all sm:gap-4 sm:px-5"
              style={{ borderColor: "var(--nav-border)", boxShadow: "var(--shadow-nav)" }}
            >
              <div className="flex items-center gap-2.5">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-800 text-[10px] font-black text-white dark:bg-amber-600">
                  P
                </div>
                <span className="font-display text-lg tracking-tight" style={{ color: "var(--text-primary)" }}>PlotLot</span>
                <span className="rounded-full px-1.5 py-0.5 text-[10px] font-medium" style={{ background: "var(--brand-subtle)", color: "var(--brand)" }}>
                  Beta
                </span>
              </div>
              <div className="h-4 w-px bg-[var(--border)]" />
              <span className="hidden text-xs sm:block" style={{ color: "var(--text-muted)" }}>104 municipalities</span>
              <ThemeToggle />
            </nav>
          </div>
          <ToastProvider>
            <main className="pt-16">{children}</main>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}

