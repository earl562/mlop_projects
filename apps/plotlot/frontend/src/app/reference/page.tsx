import Image from "next/image";
import type { CSSProperties } from "react";

import { Footer, Header, SectionLabel } from "../plotlot-marketing";
import { designReferenceSections, heroReference, logoReference } from "../plotlot-reference-data";

function ReferenceFigure({
  src,
  alt,
  aspectRatio,
  objectPosition,
  priority = false,
  className = "",
}: {
  src: string;
  alt: string;
  aspectRatio: string;
  objectPosition: string;
  priority?: boolean;
  className?: string;
}) {
  const shellStyle = { aspectRatio } as CSSProperties;

  return (
    <div className={`reference-frame ${className}`.trim()} style={shellStyle}>
      <Image
        src={src}
        alt={alt}
        fill
        priority={priority}
        loading={priority ? undefined : "eager"}
        sizes="(max-width: 760px) 100vw, (max-width: 1180px) 94vw, 1320px"
        className="reference-image"
        style={{ objectPosition }}
      />
    </div>
  );
}

export default function ReferencePage() {
  return (
    <main className="plotlot-page plotlot-reference-page">
      <Header />

      <section className="hero-reference-section">
        <div className="container">
          <div className="hero-reference-stage">
            <ReferenceFigure
              src={heroReference.src}
              alt={heroReference.alt}
              aspectRatio={heroReference.aspectRatio}
              objectPosition={heroReference.objectPosition}
              priority
              className="hero-reference-figure"
            />
            <div className="hero-copy hero-copy-overlay">
              <SectionLabel>Land Intelligence Platform</SectionLabel>
              <h1>See What Fits<span className="green-dot">.</span></h1>
              <p>Understand zoning potential, parcel constraints, and development possibilities in minutes.</p>
            </div>
          </div>
        </div>
      </section>

      <div className="container reference-stage">
        {designReferenceSections.map((section, index) => (
          <section
            key={section.id}
            id={section.id}
            className="reference-section"
            aria-labelledby={`reference-title-${section.id}`}
          >
            <div className="sr-only">
              <SectionLabel number={index > 2 ? String(index + 2).padStart(2, "0") : undefined}>
                {section.title}
              </SectionLabel>
              <h2 id={`reference-title-${section.id}`}>{section.title}</h2>
              <p>{section.description}</p>
            </div>
            <ReferenceFigure
              src={section.image}
              alt={section.alt}
              aspectRatio={section.aspectRatio}
              objectPosition={section.objectPosition}
            />
          </section>
        ))}

        <section className="reference-section" aria-labelledby="reference-title-logo">
          <div className="sr-only">
            <SectionLabel>Logo System</SectionLabel>
            <h2 id="reference-title-logo">Logo System</h2>
            <p>Plotlot logo reference for wordmark and icon treatment.</p>
          </div>
          <ReferenceFigure
            src={logoReference.image}
            alt={logoReference.alt}
            aspectRatio={logoReference.aspectRatio}
            objectPosition={logoReference.objectPosition}
          />
        </section>
      </div>

      <Footer />
    </main>
  );
}
