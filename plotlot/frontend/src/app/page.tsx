"use client";

import Image from "next/image";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, ChevronDown, Square, X } from "lucide-react";

const asset = (name: string) => `/plotlot-assets/${name}.png`;

const navItems = [
  { label: "Product", href: "#product" },
  { label: "Solutions", href: "#solutions" },
  { label: "Resources", href: "#workflow" },
  { label: "Pricing", href: "#pricing" },
  { label: "About", href: "#proof" },
];

const proofLogos = ["Gensler", "Clayco", "CIRofus", "Hines", "McWhinney"];

const capabilityCards = [
  {
    title: "Zoning Intelligence",
    copy: "Instantly understand zoning, overlays, and land use rules.",
    image: "cap-zoning",
    href: "#product",
  },
  {
    title: "Setbacks & Overlays",
    copy: "See building envelopes, setbacks, and overlay constraints.",
    image: "cap-setbacks",
    href: "#product",
  },
  {
    title: "Massing Studies",
    copy: "Test bulk, height, and scale with real-time massing.",
    image: "cap-massing",
    href: "#product",
  },
  {
    title: "Parcel Insights",
    copy: "Explore parcel details, dimensions, ownership, and more.",
    image: "cap-parcel",
    href: "#product",
  },
  {
    title: "Export Reports",
    copy: "Generate clean, shareable reports with all key findings.",
    image: "cap-report",
    href: "/sign-up?intent=report",
  },
  {
    title: "Collaborative Review",
    copy: "Share, comment, and align with your team.",
    image: "cap-review",
    href: "/sign-up?intent=team",
  },
];

const workflowSteps = [
  {
    number: "1",
    title: "Enter an address",
    copy: "Search any site to get started in seconds.",
    image: "workflow-search",
  },
  {
    number: "2",
    title: "Review zoning & parcel constraints",
    copy: "Understand what is possible on your site.",
    image: "workflow-summary",
  },
  {
    number: "3",
    title: "Explore massing options",
    copy: "Compare options that fit the rules and context.",
    image: "workflow-massing",
  },
  {
    number: "4",
    title: "Export a report",
    copy: "Download a shareable report with key findings.",
    image: "workflow-report",
  },
];

const stakeholderCards = [
  {
    label: "Developers",
    title: "Size opportunities with confidence.",
    copy: "Validate feasibility, yield, and risk before you buy.",
    image: "stakeholder-developers",
  },
  {
    label: "Brokers",
    title: "Strengthen listings with insights.",
    copy: "Add zoning clarity and upside to every deal.",
    image: "stakeholder-brokers",
  },
  {
    label: "Architects",
    title: "Explore concepts faster.",
    copy: "Test massing, setbacks, and code in real time.",
    image: "stakeholder-architects",
  },
  {
    label: "Municipal teams",
    title: "Review projects with clarity.",
    copy: "Standardize analysis and communicate with confidence.",
    image: "stakeholder-municipal",
  },
];

const pricingPlans = [
  {
    name: "Starter",
    copy: "Explore with confidence.",
    price: "$0",
    note: "Free forever",
    href: "/sign-up?plan=starter",
    cta: "Get started",
    features: ["3 lot analyses / month", "Standard reports", "Community support"],
  },
  {
    name: "Pro",
    copy: "For professionals who move fast.",
    price: "$49",
    note: "Billed monthly",
    href: "/sign-up?plan=pro",
    cta: "Start Pro",
    featured: true,
    features: ["Unlimited lot analyses", "Advanced reports", "Export & data layers", "Priority support"],
  },
  {
    name: "Team",
    copy: "Scale insights across your team.",
    price: "$199",
    note: "Billed monthly",
    href: "/sign-up?plan=team",
    cta: "Contact sales",
    features: ["Everything in Pro", "Team collaboration", "Shared workspaces", "Dedicated support"],
  },
];

function Logo() {
  return (
    <Link className="coded-logo" href="/" aria-label="Plotlot home">
      <span className="coded-logo-mark" aria-hidden="true">
        <svg viewBox="0 0 48 48" aria-hidden="true">
          <rect width="48" height="48" rx="4" fill="#3f8a2f" />
          <path d="M2 18L20 24M20 24L35 2M20 24L8 48M20 24L46 15M20 24L44 42" stroke="#fff" strokeWidth="4.3" />
          <circle cx="20" cy="24" r="6.3" fill="#3f8a2f" stroke="#fff" strokeWidth="3.8" />
        </svg>
      </span>
      <span className="coded-logo-word">Plotlot</span>
    </Link>
  );
}

function Arrow() {
  return <ArrowRight className="h-4 w-4" strokeWidth={2.4} aria-hidden="true" />;
}

function Button({
  children,
  href,
  variant = "primary",
}: {
  children: ReactNode;
  href: string;
  variant?: "primary" | "secondary" | "quiet";
}) {
  return (
    <Link className={`coded-button coded-button-${variant}`} href={href}>
      <span>{children}</span>
      {variant !== "secondary" && <Arrow />}
    </Link>
  );
}

function SectionKicker({ children, number }: { children: string; number?: string }) {
  return (
    <p className="coded-kicker">
      {number && <span>{number}</span>}
      <span>{children}</span>
    </p>
  );
}

function MediaImage({
  name,
  alt,
  className,
  priority,
}: {
  name: string;
  alt: string;
  className?: string;
  priority?: boolean;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        role="img"
        aria-label={alt}
        className={`${className ?? ""} bg-gradient-to-br from-amber-100 to-[var(--bg-surface-raised)] dark:from-amber-950/30 dark:to-[var(--bg-surface-raised)]`}
        style={{ aspectRatio: "1 / 1" }}
      />
    );
  }

  return (
    <Image
      alt={alt}
      className={className}
      height={900}
      onError={() => setFailed(true)}
      priority={priority}
      sizes="(max-width: 768px) 100vw, 50vw"
      src={asset(name)}
      unoptimized
      width={900}
    />
  );
}

function Header() {
  return (
    <header className="coded-header">
      <div className="coded-container coded-header-inner">
        <Logo />
        <nav className="coded-nav" aria-label="Primary navigation">
          {navItems.map((item) => (
            <a href={item.href} key={item.label}>
              {item.label}
              {["Product", "Solutions", "Resources"].includes(item.label) && <ChevronDown className="h-3.5 w-3.5" strokeWidth={2.5} aria-hidden="true" />}
            </a>
          ))}
        </nav>
        <div className="coded-header-actions">
          <Link href="/sign-in">Log in</Link>
          <Button href="/workspace">Analyze a Lot</Button>
        </div>
      </div>
    </header>
  );
}

export default function Home() {
  useEffect(() => {
    const nodes = document.querySelectorAll<HTMLElement>(".reveal");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) entry.target.classList.add("is-visible");
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.12 },
    );

    nodes.forEach((node) => {
      observer.observe(node);
    });
    return () => observer.disconnect();
  }, []);

  return (
    <main className="coded-site" data-testid="public-homepage">
      <Header />

      <section className="coded-hero reveal is-visible" id="hero">
        <div className="coded-grid-bg" aria-hidden="true" />
        <div className="coded-container coded-hero-grid">
          <div className="coded-hero-copy">
            <SectionKicker>Land intelligence platform</SectionKicker>
            <h1>See What Fits<span>.</span></h1>
            <p>Understand zoning potential, parcel constraints, and development possibilities in minutes.</p>
            <div className="coded-actions">
              <Button href="/workspace">Analyze a Lot</Button>
              <Button href="#product" variant="secondary">View Demo</Button>
            </div>
            <div className="coded-trust-line">
              <span>Trusted by developers, architects, and municipal teams</span>
              <div>
                {proofLogos.map((logo) => (
                  <b key={logo}>{logo}</b>
                ))}
              </div>
            </div>
          </div>

          <div className="coded-hero-visual" role="img" aria-label="Plotlot product preview">
            <div className="hero-aerial-panel">
              <MediaImage name="hero-aerial-clean" alt="Aerial parcel map with lot boundary" priority />
            </div>
            <article className="floating-card site-summary-card">
              <div className="mini-card-head">
                <strong>Site Summary</strong>
                <X className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden="true" />
              </div>
              {[
                ["Address", "123 Glenwood Ave"],
                ["Lot Area", "8,250 sf"],
                ["Zoning", "SF-3-NP"],
                ["Max Height", "50 ft"],
                ["Max FAR", "2.0:1"],
                ["Max Units", "4 du"],
              ].map(([label, value]) => (
                <div className="data-row" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
              <Link href="/sign-up?intent=report">View Full Report <Arrow /></Link>
            </article>
            <article className="visual-card hero-massing-card">
              <MediaImage name="hero-massing-clean" alt="White massing study model" />
              <div>
                <strong>Massing Study</strong>
                <span className="cube-icon" aria-hidden="true">
                  <Square className="h-4 w-4" strokeWidth={2.4} />
                </span>
              </div>
            </article>
            <article className="floating-card zoning-layer-card">
              <div className="mini-card-head">
                <strong>Zoning Layers</strong>
                <X className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden="true" />
              </div>
              {["Zoning Districts", "Height Limits", "Overlays", "Setbacks", "Floodplain"].map((item, index) => (
                <div className="layer-row" key={item}>
                  <span className={index === 4 ? "layer-dot muted" : "layer-dot"} />
                  <span>{item}</span>
                  <span className={index === 4 ? "eye muted" : "eye"} />
                </div>
              ))}
              <div className="opacity-row">
                <span>Layer Opacity</span>
                <i />
              </div>
            </article>
            <div className="zoning-map-card">
              <MediaImage name="hero-zoning-map" alt="Color coded zoning map" />
            </div>
          </div>
        </div>
      </section>

      <section className="coded-section reveal" id="proof">
        <div className="coded-container trust-layout">
          <div>
            <SectionKicker>Trust & proof</SectionKicker>
            <h2>Trusted for faster diligence.</h2>
            <p>Built for real estate, design, and municipal teams who move projects forward.</p>
            <div className="logo-wall">
              {["CBRE", "Eastdil Secured", "Gensler", "Skidmore Owings & Merrill", "Related", "Clayco", "Toronto"].map((logo) => (
                <b key={logo}>{logo}</b>
              ))}
            </div>
          </div>
          <div className="stacked-media" aria-hidden="true">
            <MediaImage name="trust-massing-card" alt="" />
            <MediaImage name="trust-zoning-card" alt="" />
            <MediaImage name="trust-aerial-card" alt="" />
          </div>
        </div>
        <div className="coded-container metrics-strip">
          <article><span>10x</span><strong>faster site review</strong><p>Automated discovery and surface what matters instantly.</p></article>
          <article>
            <span className="metric-badge" aria-hidden="true">
              <CheckCircle2 className="h-5 w-5" strokeWidth={2.4} />
            </span>
            <strong>Parcel + zoning + overlays</strong>
            <p>All key layers in one place. Always up to date.</p>
          </article>
          <article>
            <span className="metric-badge" aria-hidden="true">
              <CheckCircle2 className="h-5 w-5" strokeWidth={2.4} />
            </span>
            <strong>Minutes, not days.</strong>
            <p>From search to site summary in just a few clicks.</p>
          </article>
        </div>
      </section>

      <section className="coded-section reveal" id="solutions">
        <div className="coded-container section-heading-row">
          <div>
            <SectionKicker>Capabilities</SectionKicker>
            <h2>Everything needed to evaluate a lot.</h2>
          </div>
          <p>All the context, constraints, and tools you need in one place.</p>
        </div>
        <div className="coded-container capability-grid">
          {capabilityCards.map((card) => (
            <Link href={card.href} className="capability-card" key={card.title}>
              <div className="capability-top">
                <span className="line-icon" aria-hidden="true" />
                <strong>{card.title}</strong>
                <Arrow />
              </div>
              <p>{card.copy}</p>
              <MediaImage name={card.image} alt="" />
            </Link>
          ))}
        </div>
      </section>

      <section className="coded-section product-section reveal" id="product">
        <div className="coded-container product-layout">
          <div className="product-copy">
            <SectionKicker>Product showcase</SectionKicker>
            <h2>A clearer view of the site.</h2>
            <p>From zoning and constraints to massing and compliance, everything lives in one place.</p>
            <Button href="/workspace">Explore the Product</Button>
          </div>
          <div className="product-visual">
            <div className="product-aerial-card">
              <MediaImage name="product-aerial-clean" alt="Aerial parcel product view" />
            </div>
            <article className="floating-card product-summary-card">
              <div className="mini-card-head">
                <strong>Site Summary</strong>
                <X className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden="true" />
              </div>
              {[
                ["Address", "123 Glenwood Ave"],
                ["Lot Area", "10,019 sf"],
                ["Zoning", "SF-3-NP"],
                ["Overlays", "NPB, COA"],
                ["Max FAR", "2.0:1"],
              ].map(([label, value]) => (
                <div className="data-row" key={label}><span>{label}</span><strong>{value}</strong></div>
              ))}
              <Link href="/sign-up?intent=report">View Full Report <Arrow /></Link>
            </article>
            <article className="visual-card product-massing-card">
              <MediaImage name="product-massing-clean" alt="Massing study interface" />
              <div>
                <strong>Massing Study</strong>
                <span className="cube-icon" aria-hidden="true">
                  <Square className="h-4 w-4" strokeWidth={2.4} />
                </span>
              </div>
            </article>
            <article className="floating-card compliance-card">
              <div className="mini-card-head">
                <strong>Compliance</strong>
                <X className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden="true" />
              </div>
              {["Height Limit", "Setbacks", "FAR"].map((item) => (
                <div className="compliance-row" key={item}>
                  <span className="inline-flex items-center gap-2">
                    <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={2.4} />
                    {item}
                  </span>
                  <strong>Compliant</strong>
                </div>
              ))}
              <div className="compliance-row warn"><span>! Open Space</span><strong>Review</strong></div>
              <Link href="/sign-up?intent=compliance">View Full Compliance <Arrow /></Link>
            </article>
          </div>
        </div>
      </section>

      <section className="coded-section reveal" id="workflow">
        <div className="coded-container workflow-heading">
          <SectionKicker number="05">How it works</SectionKicker>
          <h2>From address to answer.</h2>
          <p>Plotlot turns complexity into clarity. Our workflow gives you faster insights, so you can move with confidence.</p>
        </div>
        <div className="coded-container workflow-grid">
          {workflowSteps.map((step, index) => (
            <article className="workflow-card" key={step.title}>
              <div className="step-line">
                <span>{step.number}</span>
                {index < workflowSteps.length - 1 && <i />}
              </div>
              <h3>{step.title}</h3>
              <p>{step.copy}</p>
              <MediaImage name={step.image} alt="" />
            </article>
          ))}
        </div>
      </section>

      <section className="coded-section reveal" id="stakeholders">
        <div className="coded-container stakeholder-heading">
          <div>
            <SectionKicker number="06">Built for every stakeholder</SectionKicker>
            <h2>Built for land decisions.</h2>
          </div>
          <p>Plotlot brings clarity to every stage of the land lifecycle for the people who move projects forward.</p>
        </div>
        <div className="coded-container stakeholder-grid">
          {stakeholderCards.map((card) => (
            <article className="stakeholder-card" key={card.label}>
              <p>{card.label}</p>
              <h3>{card.title}</h3>
              <span>{card.copy}</span>
              <MediaImage name={card.image} alt="" />
            </article>
          ))}
        </div>
      </section>

      <section className="coded-section testimonial-section reveal" id="testimonials">
        <div className="coded-container testimonial-layout">
          <div className="testimonial-copy">
            <SectionKicker number="07">Proof in practice</SectionKicker>
            <h2>What teams say.</h2>
            <p>Plotlot helps real estate and planning teams move faster with confidence.</p>
            <blockquote>
              <span>&quot;</span>
              Plotlot helped us go from a napkin sketch to a feasible plan in minutes. It is now part of every early conversation.
            </blockquote>
            <cite><b>Sarah Thompson</b><span>VP of Development, Gensler</span></cite>
          </div>
          <div className="testimonial-media">
            <MediaImage name="testimonial-building" alt="Completed urban development" />
            <div className="parcel-popout">
              <MediaImage name="testimonial-parcel" alt="Parcel analysis map" />
            </div>
            <div className="quote-pair">
              <article><span>&quot;</span><p>The zoning and massing insights are incredibly accurate and save us days of back-and-forth.</p><b>Michael Lee</b></article>
              <article><span>&quot;</span><p>We use Plotlot to test more scenarios, earlier. It helps us design smarter and de-risk every site.</p><b>Alicia Morgan</b></article>
            </div>
          </div>
        </div>
      </section>

      <section className="coded-section pricing-section reveal" id="pricing">
        <div className="coded-container pricing-layout">
          <div className="pricing-copy">
            <SectionKicker number="8">Pricing & get started</SectionKicker>
            <h2>Start with one lot.</h2>
            <p>Plans built for every stage of land intelligence.</p>
            <Button href="/workspace">Start analyzing</Button>
            <Button href="/sign-up?intent=team" variant="quiet">Talk to our team</Button>
          </div>
          <div className="pricing-grid">
            {pricingPlans.map((plan) => (
              <article className={plan.featured ? "price-card featured" : "price-card"} key={plan.name}>
                {plan.featured && <div className="popular-ribbon">Most popular</div>}
                <h3>{plan.name}</h3>
                <p>{plan.copy}</p>
                <div className="price-line"><strong>{plan.price}</strong>{plan.price !== "$0" && <span>/ month</span>}</div>
                <small>{plan.note}</small>
                <ul>
                  {plan.features.map((feature) => (
                    <li key={feature} className="inline-flex items-center gap-2">
                      <CheckCircle2 className="h-3.5 w-3.5" strokeWidth={2.4} />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
                <Button href={plan.href} variant={plan.featured ? "secondary" : "quiet"}>{plan.cta}</Button>
              </article>
            ))}
          </div>
        </div>
      </section>

      <footer className="coded-footer">
        <div className="topo-lines" aria-hidden="true" />
        <div className="coded-container coded-footer-inner">
          <div>
            <Logo />
            <p>Land intelligence, made simple.</p>
          </div>
          <p>(c) 2026 Plotlot. All rights reserved.</p>
        </div>
      </footer>
    </main>
  );
}
