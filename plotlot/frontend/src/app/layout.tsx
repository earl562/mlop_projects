import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ToastProvider } from "@/components/Toast";
import { SidebarLayout } from "./SidebarLayout";
import { MapsProvider } from "@/components/MapsProvider";

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
          <ToastProvider>
            <MapsProvider>
              <SidebarLayout>{children}</SidebarLayout>
            </MapsProvider>
          </ToastProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
