"use client";

import { safeExternalHref } from "@/lib/safeExternalUrl";

type SafeExternalLinkProps = {
  readonly href: string;
  readonly className: string;
  readonly children: React.ReactNode;
};

export default function SafeExternalLink({
  href,
  className,
  children,
}: SafeExternalLinkProps) {
  const safeHref = safeExternalHref(href);
  if (safeHref === null) {
    return (
      <span className={className} title={href}>
        {children}
      </span>
    );
  }

  return (
    <a
      className={className}
      href={safeHref}
      rel="noopener noreferrer"
      target="_blank"
    >
      {children}
    </a>
  );
}
