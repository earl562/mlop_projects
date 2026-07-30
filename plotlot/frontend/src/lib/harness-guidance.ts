function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toStringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

type RecommendationConfidence = "high" | "medium" | "low" | "none";

export interface CompSupportSummary {
  readonly status: string;
  readonly reason: string;
  readonly recommendationConfidence: RecommendationConfidence;
  readonly recommendedAction: string;
  readonly requiresMarketSignalValidation: boolean;
  readonly landSignalTier: string;
  readonly publicListingSignalTier: string;
}

export interface AcquisitionGuidanceSummary {
  readonly recommendedAction: string;
  readonly basis: string;
  readonly landSignalStrength: string;
  readonly marketSignalVerificationStatus: string;
  readonly recommendationConfidence: RecommendationConfidence;
  readonly requiresMarketSignalValidation: boolean;
}

export function parseAcquisitionGuidance(
  artifacts: Record<string, unknown>,
): AcquisitionGuidanceSummary | null {
  const raw = artifacts.acquisition_guidance;
  if (!isRecord(raw)) return null;

  const recommendedAction = toStringValue(raw.recommended_action);
  const basis = toStringValue(raw.basis);
  const landSignalStrength = toStringValue(raw.land_signal_strength);
  const marketSignalVerificationStatus = toStringValue(raw.market_signal_verification_status);
  const recommendationConfidenceRaw = toStringValue(raw.recommendation_confidence);
  const requiresMarketSignalValidation =
    typeof raw.requires_market_signal_validation === "boolean"
      ? raw.requires_market_signal_validation
      : null;

  if (
    recommendedAction === null
    || basis === null
    || landSignalStrength === null
    || marketSignalVerificationStatus === null
    || recommendationConfidenceRaw === null
    || requiresMarketSignalValidation === null
  ) {
    return null;
  }

  const recommendationConfidence: RecommendationConfidence =
    recommendationConfidenceRaw === "high"
    || recommendationConfidenceRaw === "medium"
    || recommendationConfidenceRaw === "low"
    || recommendationConfidenceRaw === "none"
      ? recommendationConfidenceRaw
      : "none";

  return {
    recommendedAction,
    basis,
    landSignalStrength,
    marketSignalVerificationStatus,
    recommendationConfidence,
    requiresMarketSignalValidation,
  };
}

export function parseCompSupportSummary(
  artifacts: Record<string, unknown>,
): CompSupportSummary | null {
  const raw = artifacts.comp_support_summary;
  if (!isRecord(raw)) return null;

  const status = toStringValue(raw.status);
  const reason = toStringValue(raw.reason);
  const recommendationConfidenceRaw = toStringValue(raw.recommendation_confidence);
  const recommendedAction = toStringValue(raw.recommended_action);
  const landSignalTier = toStringValue(raw.land_signal_tier);
  const publicListingSignalTier = toStringValue(raw.public_listing_signal_tier);
  const requiresMarketSignalValidation =
    typeof raw.requires_market_signal_validation === "boolean"
      ? raw.requires_market_signal_validation
      : null;

  if (
    status === null
    || reason === null
    || recommendationConfidenceRaw === null
    || recommendedAction === null
    || landSignalTier === null
    || publicListingSignalTier === null
    || requiresMarketSignalValidation === null
  ) {
    return null;
  }

  const recommendationConfidence: RecommendationConfidence =
    recommendationConfidenceRaw === "high"
    || recommendationConfidenceRaw === "medium"
    || recommendationConfidenceRaw === "low"
    || recommendationConfidenceRaw === "none"
      ? recommendationConfidenceRaw
      : "none";

  return {
    status,
    reason,
    recommendationConfidence,
    recommendedAction,
    requiresMarketSignalValidation,
    landSignalTier,
    publicListingSignalTier,
  };
}

export function prettifyHarnessValue(value: string): string {
  return value.replaceAll("_", " ");
}
