#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$repo_root"

node <<'NODE'
const fs = require("fs");

const selectionRoot = "plotlot/artifacts/design/selection";
const scoring = JSON.parse(fs.readFileSync(`${selectionRoot}/scoring.json`, "utf8"));
const packet = JSON.parse(fs.readFileSync(`${selectionRoot}/packet-audit.json`, "utf8"));
const matrix = JSON.parse(fs.readFileSync(`${selectionRoot}/acceptance-matrix.json`, "utf8"));
const ledger = JSON.parse(fs.readFileSync(`${selectionRoot}/iteration-ledger.json`, "utf8"));

const weightTotal = Object.values(scoring.method.weights).reduce((sum, value) => sum + value, 0);
if (weightTotal !== 100) throw new Error(`weight total ${weightTotal}`);

for (const direction of scoring.directions) {
  const total = Object.entries(scoring.method.weights).reduce(
    (sum, [criterion, weight]) => sum + (direction.scores[criterion] / 5) * weight,
    0,
  );
  if (Math.abs(total - direction.weighted_total) > 0.0001) {
    throw new Error(`score mismatch for ${direction.direction_id}: ${total}`);
  }
}

const ranked = [...scoring.directions].sort(
  (left, right) => right.weighted_total - left.weighted_total,
);
if (ranked[0].direction_id !== scoring.selected_direction_id) {
  throw new Error("selected direction is not the scoring winner");
}
if (ranked[0].blockers.length !== 0) throw new Error("winner has a blocker");

const expectedCoverage = {
  miami_dade: "private_beta",
  broward: "municipality_conditional",
  palm_beach: "municipality_conditional",
  san_diego: "planned_not_enabled",
};
if (JSON.stringify(matrix.coverage_assertions) !== JSON.stringify(expectedCoverage)) {
  throw new Error("coverage assertions differ from contract");
}

const expectedViewports = ["1440x900", "768x1024", "390x844", "375x844"];
const actualViewports = matrix.viewports.map(({ width, height }) => `${width}x${height}`);
for (const viewport of expectedViewports) {
  if (!actualViewports.includes(viewport)) throw new Error(`missing viewport ${viewport}`);
}

for (const state of ["verified", "missing", "stale", "conflict", "conditional", "abstained", "error", "focus_visible", "reduced_motion"]) {
  if (!matrix.required_states.includes(state)) throw new Error(`missing state ${state}`);
}

if (packet.radical_difference.result !== "pass") throw new Error("radical difference failed");
if (packet.generation_policy.new_image_calls !== 1) throw new Error("privacy correction must record exactly one fresh ImageGen call");
if (packet.generation_policy.current_privacy_correction_calls !== 1) {
  throw new Error("Direction A privacy correction must bind exactly one fresh ImageGen call");
}
if (packet.generation_policy.direction_a_total_recorded_calls !== 3) {
  throw new Error("Direction A generation history must truthfully record v2, v3, and v4 calls");
}
if (packet.generation_policy.one_call_claims.direction_a_v4_privacy_correction !== 1) {
  throw new Error("Direction A v4 must bind exactly one privacy-correction ImageGen call");
}
const directionAMetadata = JSON.parse(
  fs.readFileSync("plotlot/artifacts/design/direction-a/imagegen.metadata.json", "utf8"),
);
const truthContract = JSON.parse(
  fs.readFileSync("plotlot/artifacts/design/direction-a/design-truth-contract.json", "utf8"),
);
if (directionAMetadata.asset !== "reference-direction-a-v4.png") {
  throw new Error("Direction A selected asset mismatch");
}
if (directionAMetadata.generation.mode !== "built-in image_gen.imagegen") {
  throw new Error("Direction A generation mode mismatch");
}
if (directionAMetadata.generation.invocation_count_for_privacy_correction !== 1) {
  throw new Error("Direction A privacy-correction invocation count mismatch");
}
if (directionAMetadata.generation.total_recorded_direction_a_calls !== 3) {
  throw new Error("Direction A total generation history mismatch");
}
if (directionAMetadata.generation.prompt_sha256 !== "5a719e1b805562486e691a6a65310fce135fbf2a4dfe4101ede276d4ab9fc510") {
  throw new Error("Direction A prompt binding mismatch");
}
if (directionAMetadata.output.sha256 !== "07ea1dd9a5d42a9d3060f7f8197878cc578d89be586b4335b164135a960f2c7b") {
  throw new Error("Direction A output binding mismatch");
}
if (directionAMetadata.generation.tool_call_binding.tool_scoped_output !== "call_rvzv9UecapZkYRet64S9f95J.png") {
  throw new Error("Direction A tool-scoped output mismatch");
}
if (packet.directions.a.selected_asset !== "reference-direction-a-v4.png") {
  throw new Error("selection packet does not select Direction A v4");
}
if (!packet.directions.a.decision_rail_truth.startsWith("pass:") || !packet.directions.a.privacy_truth.startsWith("pass:")) {
  throw new Error("selection packet does not record decision-rail and privacy truth passes");
}

const crypto = require("crypto");
const sha256 = (bytes) => crypto.createHash("sha256").update(bytes).digest("hex");
const promptBytes = fs.readFileSync("plotlot/artifacts/design/direction-a.prompt.md");
const truthContractBytes = fs.readFileSync("plotlot/artifacts/design/direction-a/design-truth-contract.json");
const projectAsset = fs.readFileSync("plotlot/artifacts/design/direction-a/reference-direction-a-v4.png");
const sourceAsset = fs.readFileSync(directionAMetadata.generation.tool_call_binding.generated_source_path);
if (sha256(projectAsset) !== directionAMetadata.output.sha256 || sha256(sourceAsset) !== directionAMetadata.output.sha256) {
  throw new Error("Direction A generated source and project asset are not hash-identical");
}
if (sha256(promptBytes) !== truthContract.prompt_binding.sha256 || truthContract.prompt_binding.sha256 !== directionAMetadata.generation.prompt_sha256) {
  throw new Error("Direction A prompt hash binding mismatch");
}
if (sha256(truthContractBytes) !== directionAMetadata.truth_contract.sha256) {
  throw new Error("Direction A machine truth-contract hash mismatch");
}
if (truthContract.schema_version !== "plotlot-direction-a-truth-contract/v1.0.0") {
  throw new Error("Direction A machine truth-contract schema mismatch");
}
if (truthContract.prompt_binding.role !== "hash-bound generation input; not an executable semantic contract") {
  throw new Error("Direction A prompt role must be non-executable");
}

const requiredContractStates = new Set([
  "evidence.verified",
  "evidence.not_hash_bound",
  "decision.abstained",
  "scenario.conditional_not_reliance_ready",
  "coverage.private_beta",
  "coverage.municipality_required",
  "coverage.planned_not_enabled",
]);
if (
  truthContract.required_state_ids.length !== requiredContractStates.size ||
  truthContract.required_state_ids.some((stateId) => !requiredContractStates.has(stateId))
) {
  throw new Error("Direction A machine truth-contract state IDs mismatch");
}
if (truthContract.inputs.parking_rule.state_id !== "evidence.not_hash_bound" || truthContract.inputs.parking_rule.trust_critical !== true) {
  throw new Error("Direction A parking-rule input contract mismatch");
}

const maximumUnits = truthContract.decision_outputs.maximum_units;
const purchaseCeiling = truthContract.decision_outputs.purchase_ceiling;
if (
  maximumUnits.state_id !== "decision.abstained" ||
  maximumUnits.current_value !== null ||
  JSON.stringify(maximumUnits.depends_on) !== JSON.stringify(["parking_rule"]) ||
  maximumUnits.scenario.state_id !== "scenario.conditional_not_reliance_ready"
) {
  throw new Error("Direction A maximum-units structural contract mismatch");
}
if (
  purchaseCeiling.state_id !== "decision.abstained" ||
  purchaseCeiling.current_value !== null ||
  JSON.stringify(purchaseCeiling.depends_on) !== JSON.stringify(["parking_rule", "maximum_units"]) ||
  purchaseCeiling.scenario.state_id !== "scenario.conditional_not_reliance_ready"
) {
  throw new Error("Direction A purchase-ceiling structural contract mismatch");
}

const ruleById = Object.fromEntries(truthContract.dependency_rules.map((rule) => [rule.rule_id, rule]));
for (const [ruleId, output] of [
  ["parking-not-hash-bound-abstains-capacity", "maximum_units"],
  ["parking-not-hash-bound-abstains-underwriting", "purchase_ceiling"],
]) {
  const rule = ruleById[ruleId];
  if (
    !rule ||
    rule.when.input !== "parking_rule" ||
    rule.when.state_id !== "evidence.not_hash_bound" ||
    rule.then.output !== output ||
    rule.then.state_id !== "decision.abstained" ||
    rule.then.current_value !== null
  ) {
    throw new Error(`Direction A dependency rule mismatch: ${ruleId}`);
  }
}

const allowedDealIds = [
  "DEAL-MIA-0420",
  "DEAL-MIA-0150",
  "DEAL-BRW-0010",
  "DEAL-PBC-1234",
  "DEAL-SD-0000",
];
if (
  truthContract.privacy.display_identifier_policy !== "opaque_synthetic_only" ||
  JSON.stringify(truthContract.privacy.allowed_deal_ids) !== JSON.stringify(allowedDealIds) ||
  directionAMetadata.visual_validation.address_like_strings_observed.length !== 0 ||
  JSON.stringify(directionAMetadata.visual_validation.visible_deal_ids) !== JSON.stringify(allowedDealIds)
) {
  throw new Error("Direction A opaque synthetic identifier contract mismatch");
}
for (const dealId of truthContract.privacy.allowed_deal_ids) {
  if (!new RegExp(truthContract.privacy.allowed_deal_id_pattern).test(dealId)) {
    throw new Error(`Direction A deal ID does not match contract: ${dealId}`);
  }
}
for (const dataClass of ["street_number", "street_name", "full_or_partial_address", "folio", "apn", "owner_name", "coordinates", "source_url"]) {
  if (!truthContract.privacy.prohibited_visible_data_classes.includes(dataClass)) {
    throw new Error(`Direction A privacy contract missing prohibited class: ${dataClass}`);
  }
}

const expectedContractCoverage = {
  miami_dade: "coverage.private_beta",
  broward: "coverage.municipality_required",
  palm_beach: "coverage.municipality_required",
  san_diego: "coverage.planned_not_enabled",
};
if (JSON.stringify(truthContract.coverage) !== JSON.stringify(expectedContractCoverage)) {
  throw new Error("Direction A machine truth-contract coverage mismatch");
}
if (ledger.baseline_commit !== "719e3179a77722e74df3ced161b350f60b5e6ad7") {
  throw new Error("iteration ledger is not bound to the audited baseline commit");
}
if (ledger.defects.length !== 9) throw new Error("unexpected baseline defect count");

if (fs.statSync("plotlot/DESIGN.md").size === 0) throw new Error("DESIGN.md is empty");

console.log(JSON.stringify({
  result: "pass",
  selected: scoring.selected_name,
  totals: Object.fromEntries(scoring.directions.map((direction) => [direction.direction_id, direction.weighted_total])),
  coverage: matrix.coverage_assertions,
  viewports: actualViewports,
  requiredStateCount: matrix.required_states.length,
  baselineDefectCount: ledger.defects.length,
  newImageCalls: packet.generation_policy.new_image_calls,
  selectedDirectionAAsset: packet.directions.a.selected_asset,
  decisionRailTruth: packet.directions.a.decision_rail_truth,
  privacyTruth: packet.directions.a.privacy_truth,
  truthContractSchema: truthContract.schema_version,
}, null, 2));
NODE

(cd plotlot/artifacts/design/direction-a && shasum -a 256 -c checksums.sha256)
(cd plotlot/artifacts/design/direction-a && shasum -a 256 -c design-truth-contract.sha256)
(cd plotlot && shasum -a 256 -c artifacts/design/direction-b/checksums.sha256)
(cd plotlot/artifacts/design/direction-c && shasum -a 256 -c checksums.sha256)

file plotlot/artifacts/design/direction-a/reference-direction-a-v4.png
file plotlot/artifacts/design/direction-b/reference-direction-b-v1.png
file plotlot/artifacts/design/direction-c/reference-direction-c-v1.png

test "$(find .omo/evidence/todo5-design-selection/browser-baseline -name '*.png' -size +0c | wc -l | tr -d ' ')" = "13"
test "$(find .omo/evidence/todo5-design-selection/browser-baseline -name '*.aria.txt' -size +0c | wc -l | tr -d ' ')" = "12"
test "$(find .omo/evidence/todo5-design-selection/browser-baseline -name '*.json' -size +0c | wc -l | tr -d ' ')" = "14"

echo "BROWSER_ARTIFACT_COUNTS: screenshots=13 aria=12 json=14"
echo "TODO5_VERIFICATION: PASS"
