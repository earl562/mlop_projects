import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ToastProvider } from "@/components/Toast";
import { SidebarLayout } from "./SidebarLayout";

export const metadata: Metadata = {
  title: "PlotLot - AI Zoning Analysis",
  description:
    "AI-powered zoning analysis for US real estate. Covers municipalities across Florida, Texas, Georgia, South Carolina, and North Carolina.",
  openGraph: {
    title: "PlotLot - AI Zoning Analysis",
    description:
      "Enter any US address and get instant zoning analysis: density limits, setbacks, allowable uses, and max buildable units.",
    siteName: "PlotLot",
    type: "website",
    url: "https://mlopprojects.vercel.app",
  },
  twitter: {
    card: "summary_large_image",
    title: "PlotLot - AI Zoning Analysis",
    description:
      "AI-powered zoning analysis for US real estate. Instant density, setback, and use analysis across 5 states.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const clerkPublishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  const app = (
      <html lang="en" suppressHydrationWarning>
        <head>
          <script
            // Run before hydration to avoid a light→dark flash in the workspace.
            dangerouslySetInnerHTML={{
              __html: `(function(){try{var t=localStorage.getItem('theme');var p=window.location&&window.location.pathname?window.location.pathname:'/';var pub=(p==='/'||p==='/reference'||p==='/analyze');var theme=(t==='light'||t==='dark')?t:(pub?'light':'dark');document.documentElement.classList.toggle('dark',theme==='dark')}catch(e){}})();`,
            }}
          />
        </head>
        <body
          className="min-h-screen bg-[var(--bg-primary)] font-sans antialiased"
        >
          <ThemeProvider>
            <ToastProvider>
              <SidebarLayout>{children}</SidebarLayout>
            </ToastProvider>
          </ThemeProvider>
        </body>
      </html>
  );

  if (!clerkPublishableKey) {
    return app;
  }

  return (
    <ClerkProvider publishableKey={clerkPublishableKey} afterSignOutUrl="/sign-in">
      {app}
    </ClerkProvider>
  );
}
