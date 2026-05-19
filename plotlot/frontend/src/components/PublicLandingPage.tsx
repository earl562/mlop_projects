import Image from "next/image";
import Link from "next/link";

type MarketingAsset = {
  src: string;
  width: number;
  height: number;
  alt: string;
};

const assets = {
  heroAerial: {
    src: "/plotlot-assets/hero-aerial-clean.png",
    width: 449,
    height: 497,
    alt: "Parcel aerial with development context",
  },
  heroMassing: {
    src: "/plotlot-assets/hero-massing-clean.png",
    width: 450,
    height: 350,
    alt: "Early massing study generated from a parcel",
  },
  heroZoning: {
    src: "/plotlot-assets/hero-zoning-map.png",
    width: 355,
    height: 277,
    alt: "Zoning overlay view for a target parcel",
  },
  productAerial: {
    src: "/plotlot-assets/product-aerial-clean.png",
    width: 572,
    height: 520,
    alt: "Aerial parcel intelligence view",
  },
  productMassing: {
    src: "/plotlot-assets/product-massing-clean.png",
    width: 506,
    height: 335,
    alt: "Buildable massing concept",
  },
  trustMassing: {
    src: "/plotlot-assets/trust-massing-card.png",
    width: 174,
    height: 595,
    alt: "Massing proof card",
  },
  trustZoning: {
    src: "/plotlot-assets/trust-zoning-card.png",
    width: 206,
    height: 630,
    alt: "Zoning proof card",
  },
  trustAerial: {
    src: "/plotlot-assets/trust-aerial-card.png",
    width: 353,
    height: 674,
    alt: "Aerial proof card",
  },
} satisfies Record<string, MarketingAsset>;

const capabilityCards = [
  {
    title: "Zoning context",
    body: "Resolve the district, dimensional standards, uses, and cited ordinance context before a deal moves forward.",
    asset: { src: "/plotlot-assets/cap-zoning.png", width: 396, height: 254, alt: "Zoning capability preview" },
  },
  {
    title: "Setbacks and controls",
    body: "Surface setbacks, frontage, height, lot coverage, and the constraint that actually governs unit count.",
    asset: { src: "/plotlot-assets/cap-setbacks.png", width: 351, height: 254, alt: "Setback capability preview" },
  },
  {
    title: "Massing previews",
    body: "Translate parcel rules into early buildable-envelope views so teams can see fit before they spend.",
    asset: { src: "/plotlot-assets/cap-massing.png", width: 400, height: 254, alt: "Massing capability preview" },
  },
  {
    title: "Parcel intelligence",
    body: "Combine aerial, parcel, and location context into one acquisition-ready screen instead of scattered tabs.",
    asset: { src: "/plotlot-assets/cap-parcel.png", width: 396, height: 295, alt: "Parcel capability preview" },
  },
  {
    title: "Decision-ready reports",
    body: "Package feasibility outputs into summaries your team can review, save, and continue inside the workspace.",
    asset: { src: "/plotlot-assets/cap-report.png", width: 351, height: 315, alt: "Report capability preview" },
  },
  {
    title: "Review workflow",
    body: "Move from fast lookup to deeper agent-guided follow-up without losing parcel context or prior analysis state.",
    asset: { src: "/plotlot-assets/cap-review.png", width: 400, height: 295, alt: "Review capability preview" },
  },
];

const workflowSteps = [
  {
    step: "01",
    title: "Search the parcel",
    body: "Start with an address and let PlotLot resolve the parcel, municipality, and county context.",
    asset: { src: "/plotlot-assets/workflow-search.png", width: 269, height: 443, alt: "Search workflow preview" },
  },
  {
    step: "02",
    title: "Read the zoning summary",
    body: "Review the governing standards, cited zoning context, and feasibility constraints in one stream.",
    asset: { src: "/plotlot-assets/workflow-summary.png", width: 279, height: 443, alt: "Summary workflow preview" },
  },
  {
    step: "03",
    title: "Check fit and massing",
    body: "Use parcel geometry and rule extraction to pressure-test what can actually fit on the lot.",
    asset: { src: "/plotlot-assets/workflow-massing.png", width: 251, height: 441, alt: "Massing workflow preview" },
  },
  {
    step: "04",
    title: "Carry the deal forward",
    body: "Move the result into the workspace for follow-up questions, reports, comps, and deeper underwriting.",
    asset: { src: "/plotlot-assets/workflow-report.png", width: 289, height: 442, alt: "Report workflow preview" },
  },
];

const stakeholders = [
  {
    title: "Developers",
    body: "Filter deals faster and know which parcels deserve immediate underwriting attention.",
    asset: { src: "/plotlot-assets/stakeholder-developers.png", width: 280, height: 505, alt: "Developer stakeholder preview" },
  },
  {
    title: "Brokers",
    body: "Give buyers a feasibility narrative that is sharper than a listing flyer and faster than manual zoning review.",
    asset: { src: "/plotlot-assets/stakeholder-brokers.png", width: 280, height: 505, alt: "Broker stakeholder preview" },
  },
  {
    title: "Architects",
    body: "Get to envelope, setbacks, and lot constraints earlier so concept work starts with cleaner assumptions.",
    asset: { src: "/plotlot-assets/stakeholder-architects.png", width: 280, height: 505, alt: "Architect stakeholder preview" },
  },
  {
    title: "Municipal-facing teams",
    body: "Bring cited context and a tractable feasibility summary into pre-application and entitlement conversations.",
    asset: { src: "/plotlot-assets/stakeholder-municipal.png", width: 285, height: 505, alt: "Municipal stakeholder preview" },
  },
];

function BrandMark() {
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--text-primary)] text-sm font-black text-[var(--bg-primary)] shadow-[var(--shadow-card)]">
      P
    </div>
  );
}

function PrimaryLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center justify-center rounded-full bg-[var(--text-primary)] px-5 py-3 text-sm font-semibold text-[var(--bg-primary)] transition hover:opacity-90"
    >
      {children}
    </Link>
  );
}

function SecondaryLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="inline-flex items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-5 py-3 text-sm font-semibold text-[var(--text-primary)] transition hover:border-[var(--border-hover)]"
    >
      {children}
    </Link>
  );
}

function SectionKicker({ children }: { children: React.ReactNode }) {
  return <p className="section-pill">{children}</p>;
}

function MarketingImage({ asset, className }: { asset: MarketingAsset; className?: string }) {
  return (
    <Image
      src={asset.src}
      alt={asset.alt}
      width={asset.width}
      height={asset.height}
      className={className}
    />
  );
}

export default function PublicLandingPage() {
  return (
    <main className="min-h-[100dvh] bg-[var(--bg-primary)] text-[var(--text-primary)]" data-testid="public-homepage">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <header className="flex items-center justify-between gap-4 py-6">
          <Link href="/" className="flex items-center gap-3">
            <BrandMark />
            <div>
              <p className="font-display text-xl tracking-tight text-[var(--text-primary)]">PlotLot</p>
              <p className="text-xs uppercase tracking-[0.18em] text-[var(--text-muted)]">Land feasibility intelligence</p>
            </div>
          </Link>

          <nav className="hidden items-center gap-6 text-sm text-[var(--text-secondary)] md:flex">
            <a href="#capabilities" className="transition hover:text-[var(--text-primary)]">Capabilities</a>
            <a href="#workflow" className="transition hover:text-[var(--text-primary)]">Workflow</a>
            <a href="#stakeholders" className="transition hover:text-[var(--text-primary)]">Who it serves</a>
          </nav>

          <div className="flex items-center gap-3">
            <SecondaryLink href="/workspace?mode=agent">Open workspace</SecondaryLink>
          </div>
        </header>

        <section className="grid gap-10 py-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:py-16">
          <div>
            <SectionKicker>Public homepage restored</SectionKicker>
            <h1 className="mt-5 max-w-3xl font-display text-[clamp(3rem,7vw,5.6rem)] leading-[0.95] tracking-tight text-[var(--text-primary)]">
              PlotLot turns parcel uncertainty into buildable answers.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-[var(--text-secondary)]">
              Start with an address and move from zoning context to density, setbacks, massing, and next-step deal work without dropping into a generic chat shell.
            </p>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <PrimaryLink href="/workspace?mode=lookup">Start a lookup</PrimaryLink>
              <SecondaryLink href="/workspace?mode=agent">Open agent workspace</SecondaryLink>
            </div>

            <dl className="mt-10 grid gap-4 sm:grid-cols-3">
              <div className="rounded-[1.5rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
                <dt className="text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">Coverage</dt>
                <dd className="mt-2 text-3xl font-semibold">104</dd>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">municipalities available for fast feasibility review</p>
              </div>
              <div className="rounded-[1.5rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
                <dt className="text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">Core outputs</dt>
                <dd className="mt-2 text-3xl font-semibold">4</dd>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">zoning, density, parcel fit, and saved workspace follow-up</p>
              </div>
              <div className="rounded-[1.5rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
                <dt className="text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">Product flow</dt>
                <dd className="mt-2 text-3xl font-semibold">1</dd>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">public front door with an explicit workspace route behind it</p>
              </div>
            </dl>
          </div>

          <div className="relative">
            <div className="absolute -right-8 -top-8 h-40 w-40 rounded-full bg-[radial-gradient(circle,rgba(180,83,9,0.18),transparent_68%)]" />
            <div className="grid gap-4 rounded-[2rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-elevated)] sm:grid-cols-[1.15fr_0.85fr]">
              <div className="overflow-hidden rounded-[1.5rem] bg-[var(--bg-inset)]">
                <MarketingImage asset={assets.heroAerial} className="h-full w-full object-cover" />
              </div>
              <div className="grid gap-4">
                <div className="overflow-hidden rounded-[1.5rem] bg-[var(--bg-inset)]">
                  <MarketingImage asset={assets.heroMassing} className="h-full w-full object-cover" />
                </div>
                <div className="overflow-hidden rounded-[1.5rem] bg-[var(--bg-inset)]">
                  <MarketingImage asset={assets.heroZoning} className="h-full w-full object-cover" />
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="capabilities" className="py-12 lg:py-16">
          <div className="max-w-3xl">
            <SectionKicker>Capabilities</SectionKicker>
            <h2 className="mt-4 font-display text-4xl tracking-tight sm:text-5xl">A public front door that still leads into real analysis.</h2>
            <p className="mt-4 text-base leading-7 text-[var(--text-secondary)]">
              The PI concept preserved an asset-backed product story: show what PlotLot does publicly, then move into the workspace only when the user is ready to analyze a site.
            </p>
          </div>

          <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {capabilityCards.map((card) => (
              <article
                key={card.title}
                className="overflow-hidden rounded-[1.75rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] shadow-[var(--shadow-card)]"
              >
                <div className="aspect-[4/3] bg-[var(--bg-inset)]">
                  <Image src={card.asset.src} alt={card.asset.alt} width={card.asset.width} height={card.asset.height} className="h-full w-full object-cover" />
                </div>
                <div className="p-6">
                  <h3 className="text-xl font-semibold tracking-tight">{card.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{card.body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="grid gap-8 py-12 lg:grid-cols-[0.9fr_1.1fr] lg:items-center lg:py-16">
          <div>
            <SectionKicker>Trust and proof</SectionKicker>
            <h2 className="mt-4 font-display text-4xl tracking-tight sm:text-5xl">Show the parcel, the rule, and the implication side by side.</h2>
            <p className="mt-4 text-base leading-7 text-[var(--text-secondary)]">
              The restored homepage uses the recovered PI media set to explain PlotLot the same way the product works: aerial context, zoning context, then feasibility context.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <div className="overflow-hidden rounded-[1.75rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-3 shadow-[var(--shadow-card)]">
              <MarketingImage asset={assets.trustMassing} className="h-full w-full rounded-[1.1rem] object-cover" />
            </div>
            <div className="overflow-hidden rounded-[1.75rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-3 shadow-[var(--shadow-card)]">
              <MarketingImage asset={assets.trustZoning} className="h-full w-full rounded-[1.1rem] object-cover" />
            </div>
            <div className="overflow-hidden rounded-[1.75rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-3 shadow-[var(--shadow-card)]">
              <MarketingImage asset={assets.trustAerial} className="h-full w-full rounded-[1.1rem] object-cover" />
            </div>
          </div>
        </section>

        <section className="grid gap-8 py-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:py-16">
          <div className="rounded-[2rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-card)]">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="overflow-hidden rounded-[1.5rem] bg-[var(--bg-inset)]">
                <MarketingImage asset={assets.productAerial} className="h-full w-full object-cover" />
              </div>
              <div className="overflow-hidden rounded-[1.5rem] bg-[var(--bg-inset)]">
                <MarketingImage asset={assets.productMassing} className="h-full w-full object-cover" />
              </div>
            </div>
          </div>

          <div>
            <SectionKicker>Product</SectionKicker>
            <h2 className="mt-4 font-display text-4xl tracking-tight sm:text-5xl">Preserve the workspace, but stop making it the public homepage.</h2>
            <p className="mt-4 text-base leading-7 text-[var(--text-secondary)]">
              The analysis experience still lives in the canonical frontend. It now has an explicit route, so the landing page can explain the product while the internal shell remains focused on doing the work.
            </p>
            <ul className="mt-6 space-y-3 text-sm leading-6 text-[var(--text-secondary)]">
              <li>• Public visitors land on the product story instead of the app chrome.</li>
              <li>• Analysts still get the same lookup and agent experience on a dedicated workspace route.</li>
              <li>• Sidebar navigation stays local to workspace pages, not the marketing surface.</li>
            </ul>
          </div>
        </section>

        <section id="workflow" className="py-12 lg:py-16">
          <div className="max-w-3xl">
            <SectionKicker>Workflow</SectionKicker>
            <h2 className="mt-4 font-display text-4xl tracking-tight sm:text-5xl">Go from address to next action in a deliberate sequence.</h2>
          </div>

          <div className="mt-8 grid gap-5 lg:grid-cols-4">
            {workflowSteps.map((step) => (
              <article
                key={step.step}
                className="overflow-hidden rounded-[1.75rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] shadow-[var(--shadow-card)]"
              >
                <div className="aspect-[4/5] bg-[var(--bg-inset)] p-3">
                  <Image src={step.asset.src} alt={step.asset.alt} width={step.asset.width} height={step.asset.height} className="h-full w-full rounded-[1.2rem] object-cover" />
                </div>
                <div className="p-6">
                  <p className="text-xs uppercase tracking-[0.22em] text-[var(--brand)]">{step.step}</p>
                  <h3 className="mt-3 text-xl font-semibold tracking-tight">{step.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{step.body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section id="stakeholders" className="py-12 lg:py-16">
          <div className="max-w-3xl">
            <SectionKicker>Who it serves</SectionKicker>
            <h2 className="mt-4 font-display text-4xl tracking-tight sm:text-5xl">Built for acquisition-minded teams that need fast, explainable feasibility.</h2>
          </div>

          <div className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            {stakeholders.map((stakeholder) => (
              <article
                key={stakeholder.title}
                className="overflow-hidden rounded-[1.75rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] shadow-[var(--shadow-card)]"
              >
                <div className="aspect-[9/14] bg-[var(--bg-inset)]">
                  <Image src={stakeholder.asset.src} alt={stakeholder.asset.alt} width={stakeholder.asset.width} height={stakeholder.asset.height} className="h-full w-full object-cover" />
                </div>
                <div className="p-6">
                  <h3 className="text-xl font-semibold tracking-tight">{stakeholder.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{stakeholder.body}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="py-12 pb-16 lg:py-16 lg:pb-24">
          <div className="rounded-[2rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-8 shadow-[var(--shadow-elevated)] sm:p-10 lg:flex lg:items-end lg:justify-between">
            <div className="max-w-2xl">
              <SectionKicker>Workspace ready</SectionKicker>
              <h2 className="mt-4 font-display text-4xl tracking-tight sm:text-5xl">Public homepage up front. Analysis shell where it belongs.</h2>
              <p className="mt-4 text-base leading-7 text-[var(--text-secondary)]">
                Open the dedicated workspace when you are ready to analyze a parcel, continue an agent thread, or review saved feasibility work.
              </p>
            </div>

            <div className="mt-8 flex flex-col gap-3 sm:flex-row lg:mt-0">
              <PrimaryLink href="/workspace?mode=lookup">Launch workspace</PrimaryLink>
              <SecondaryLink href="/connectors">View connectors</SecondaryLink>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
