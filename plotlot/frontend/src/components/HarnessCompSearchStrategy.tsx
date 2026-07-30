"use client";

type CompSearchAttempt = {
  readonly months: number;
  readonly radiusMiles: number;
  readonly landCompCount: number;
  readonly unitCompCount: number;
  readonly estimatedLandValue: number;
  readonly advPerUnit: number;
  readonly confidence: number;
  readonly selected: boolean;
  readonly selectionReason: string;
};

type CompSearchStrategy = {
  readonly selectedMonths: number | null;
  readonly selectedReason: string;
  readonly attempts: readonly CompSearchAttempt[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toStringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function parseCompSearchStrategy(
  artifacts: Record<string, unknown>,
): CompSearchStrategy | null {
  const raw = artifacts.comp_search_strategy;
  if (!isRecord(raw)) return null;
  const attemptsRaw = raw.attempts;
  if (!Array.isArray(attemptsRaw)) return null;

  const attempts = attemptsRaw
    .map((attempt): CompSearchAttempt | null => {
      if (!isRecord(attempt)) return null;
      const months = toNumber(attempt.months);
      const radiusMiles = toNumber(attempt.radius_miles);
      const landCompCount = toNumber(attempt.land_comp_count);
      const unitCompCount = toNumber(attempt.unit_comp_count);
      const estimatedLandValue = toNumber(attempt.estimated_land_value);
      const advPerUnit = toNumber(attempt.adv_per_unit);
      const confidence = toNumber(attempt.confidence);
      const selected = typeof attempt.selected === "boolean" ? attempt.selected : false;
      const selectionReason = toStringValue(attempt.selection_reason) ?? "not_selected";
      if (
        months === null
        || radiusMiles === null
        || landCompCount === null
        || unitCompCount === null
        || estimatedLandValue === null
        || advPerUnit === null
        || confidence === null
      ) {
        return null;
      }
      return {
        months,
        radiusMiles,
        landCompCount,
        unitCompCount,
        estimatedLandValue,
        advPerUnit,
        confidence,
        selected,
        selectionReason,
      };
    })
    .filter((attempt): attempt is CompSearchAttempt => attempt !== null);

  if (attempts.length === 0) return null;

  return {
    selectedMonths: toNumber(raw.selected_months),
    selectedReason: toStringValue(raw.selected_reason) ?? "unqualified_first_attempt",
    attempts,
  };
}

type Props = {
  artifacts: Record<string, unknown>;
};

export default function HarnessCompSearchStrategy({ artifacts }: Props) {
  const compSearchStrategy = parseCompSearchStrategy(artifacts);
  if (!compSearchStrategy) return null;

  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Comparable sales strategy</h2>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Selected via{" "}
            <span className="font-medium text-[var(--text-primary)]">
              {compSearchStrategy.selectedReason.replaceAll("_", " ")}
            </span>
            {compSearchStrategy.selectedMonths !== null ? ` at ${compSearchStrategy.selectedMonths} months.` : "."}
          </p>
        </div>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {compSearchStrategy.attempts.map((attempt) => (
          <article
            key={`${attempt.months}-${attempt.radiusMiles}`}
            className={`rounded-xl border p-4 ${
              attempt.selected
                ? "border-[var(--brand)] bg-[var(--bg-surface-raised)]"
                : "border-[var(--border)] bg-[var(--bg-surface-raised)]"
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-medium text-[var(--text-primary)]">
                {attempt.months} mo • {attempt.radiusMiles.toFixed(1)} mi
              </p>
              {attempt.selected ? (
                <span className="rounded-full bg-[var(--brand)]/10 px-2 py-1 text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--brand)]">
                  Selected
                </span>
              ) : null}
            </div>
            <dl className="mt-3 space-y-2 text-sm text-[var(--text-secondary)]">
              <div className="flex items-center justify-between gap-3">
                <dt>Land comps</dt>
                <dd className="font-medium text-[var(--text-primary)]">{attempt.landCompCount}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt>Exit comps</dt>
                <dd className="font-medium text-[var(--text-primary)]">{attempt.unitCompCount}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt>Land value</dt>
                <dd className="font-medium text-[var(--text-primary)]">
                  ${attempt.estimatedLandValue.toLocaleString()}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt>ADV per unit</dt>
                <dd className="font-medium text-[var(--text-primary)]">
                  ${attempt.advPerUnit.toLocaleString()}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt>Confidence</dt>
                <dd className="font-medium text-[var(--text-primary)]">
                  {Math.round(attempt.confidence * 100)}%
                </dd>
              </div>
            </dl>
            <p className="mt-3 text-xs text-[var(--text-muted)]">
              {attempt.selectionReason.replaceAll("_", " ")}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
