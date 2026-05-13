import Link from "next/link";
import type { ReactNode } from "react";

export const navItems = [
  { label: "Product", href: "#product", hasMenu: true },
  { label: "Solutions", href: "#solutions", hasMenu: true },
  { label: "Resources", href: "#resources", hasMenu: true },
  { label: "Pricing", href: "#pricing", hasMenu: false },
  { label: "About", href: "#about", hasMenu: false },
] as const;

export const proofLogos = ["Gensler", "Clayco", "CIRofus", "Hines", "McWhinney"] as const;

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="plotlot-logo" aria-label="Plotlot home">
      <span className="plotlot-mark" aria-hidden="true">
        <svg viewBox="0 0 48 48" role="img">
          <rect width="48" height="48" rx="4" fill="#3f8a2f" />
          <path d="M2 18L20 24M20 24L35 2M20 24L8 48M20 24L46 15M20 24L44 42" stroke="#fff" strokeWidth="4.3" />
          <circle cx="20" cy="24" r="6.3" fill="#3f8a2f" stroke="#fff" strokeWidth="3.8" />
        </svg>
      </span>
      {!compact && <span className="plotlot-word">Plotlot</span>}
    </Link>
  );
}

export function Arrow() {
  return <span aria-hidden="true" className="arrow">-&gt;</span>;
}

export function SectionLabel({ children, number }: { children: string; number?: string }) {
  return (
    <p className="section-label">
      {number && <span>{number}</span>}
      <span>{children}</span>
    </p>
  );
}

export function Button({
  children,
  href,
  variant = "primary",
}: {
  children: ReactNode;
  href: string;
  variant?: "primary" | "secondary" | "text";
}) {
  return (
    <Link href={href} className={`button button-${variant}`}>
      <span>{children}</span>
      {variant !== "secondary" && <Arrow />}
    </Link>
  );
}

export function Header() {
  return (
    <header className="site-header">
      <div className="container header-inner">
        <Logo />
        <nav className="desktop-nav" aria-label="Primary">
          {navItems.map((item) => (
            <a key={item.label} href={item.href}>
              <span>{item.label}</span>
              {item.hasMenu && <span className="nav-caret" aria-hidden="true" />}
            </a>
          ))}
        </nav>
        <div className="header-actions">
          <Link href="/sign-in" className="login-link">Log in</Link>
          <Button href="/workspace">Analyze a Lot</Button>
        </div>
        <details className="mobile-menu">
          <summary aria-label="Open menu"><span /></summary>
          <div>
            {navItems.map((item) => (
              <a key={item.label} href={item.href}>{item.label}</a>
            ))}
            <Link href="/sign-in">Log in</Link>
            <Link href="/workspace">Analyze a Lot</Link>
          </div>
        </details>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="plotlot-footer">
      <div className="topo-pattern" aria-hidden="true" />
      <div className="container footer-inner">
        <div>
          <Logo />
          <p>Land intelligence, made simple.</p>
        </div>
        <p>&copy; 2026 Plotlot. All rights reserved.</p>
      </div>
    </footer>
  );
}
