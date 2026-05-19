export const heroReference = {
  src: "/plotlot-ref/hero-v2.png",
  alt: "Plotlot hero design reference showing a parcel analysis dashboard with aerial imagery, site summary, massing study, and zoning layers.",
  aspectRatio: "148 / 96",
  objectPosition: "76% 58%",
} as const;

export const logoReference = {
  image: "/plotlot-ref/logo-sheet.png",
  alt: "Plotlot logo design reference showing the green parcel mark beside the Plotlot wordmark and an isolated mark.",
  aspectRatio: "1 / 1",
  objectPosition: "50% 50%",
} as const;

export const designReferenceSections = [
  {
    id: "solutions",
    title: "Trust & Proof",
    description: "Plotlot trust reference showing diligence proof, logos, and metrics.",
    image: "/plotlot-ref/trust-v2.png",
    alt: "Plotlot trust and proof design reference with parcel imagery, zoning overlays, client logos, and diligence metrics.",
    aspectRatio: "145 / 96",
    objectPosition: "50% 57%",
  },
  {
    id: "resources",
    title: "Capabilities",
    description: "Plotlot capabilities reference showing the product card grid.",
    image: "/plotlot-ref/capabilities.png",
    alt: "Plotlot capabilities design reference showing six feature cards for zoning intelligence, overlays, massing, parcel insights, reports, and collaboration.",
    aspectRatio: "145 / 98",
    objectPosition: "50% 55%",
  },
  {
    id: "product",
    title: "Product Showcase",
    description: "Plotlot product showcase reference with parcel, massing, and compliance layers.",
    image: "/plotlot-ref/product-v2.png",
    alt: "Plotlot product showcase design reference with site summary, aerial parcel view, zoning layers, massing study, and compliance card.",
    aspectRatio: "145 / 98",
    objectPosition: "57% 58%",
  },
  {
    id: "workflow",
    title: "How It Works",
    description: "Plotlot workflow reference showing the address to answer journey.",
    image: "/plotlot-ref/workflow.png",
    alt: "Plotlot workflow design reference showing four steps from address search to exported report.",
    aspectRatio: "145 / 94",
    objectPosition: "50% 54%",
  },
  {
    id: "about",
    title: "Built For Every Stakeholder",
    description: "Plotlot use case reference for developers, brokers, architects, and municipal teams.",
    image: "/plotlot-ref/use-cases.png",
    alt: "Plotlot use-case design reference showing stakeholder cards for developers, brokers, architects, and municipal teams.",
    aspectRatio: "145 / 100",
    objectPosition: "50% 56%",
  },
  {
    id: "testimonials",
    title: "Proof In Practice",
    description: "Plotlot testimonial reference showing customer proof and quotes.",
    image: "/plotlot-ref/testimonials-v2.png",
    alt: "Plotlot testimonial design reference showing a building render, parcel inset, and customer quote cards.",
    aspectRatio: "145 / 97",
    objectPosition: "50% 57%",
  },
  {
    id: "pricing",
    title: "Pricing & Get Started",
    description: "Plotlot pricing reference showing starter, pro, and team plans.",
    image: "/plotlot-ref/pricing.png",
    alt: "Plotlot pricing design reference showing starter, pro, and team pricing cards with a get started call to action.",
    aspectRatio: "145 / 88",
    objectPosition: "50% 46%",
  },
] as const;

export const designReferenceAlts = [heroReference.alt, ...designReferenceSections.map((section) => section.alt)] as const;
