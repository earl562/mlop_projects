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
if (packet.generation_policy.new_image_calls !== 1) throw new Error("provenance correction must record exactly one new ImageGen call");
if (packet.generation_policy.one_call_claims.direction_a !== 1) {
  throw new Error("Direction A must bind exactly one corrective ImageGen call");
}
const directionAMetadata = JSON.parse(
  fs.readFileSync("plotlot/artifacts/design/direction-a/imagegen.metadata.json", "utf8"),
);
if (directionAMetadata.asset !== "reference-direction-a-v2.png") {
  throw new Error("Direction A selected asset mismatch");
}
if (directionAMetadata.generation.mode !== "built-in image_gen.imagegen") {
  throw new Error("Direction A generation mode mismatch");
}
if (directionAMetadata.generation.invocation_count_for_provenance_correction !== 1) {
  throw new Error("Direction A provenance invocation count mismatch");
}
if (directionAMetadata.generation.prompt_sha256 !== "2b24a583d2aa2e45e27befa37b2f970b700a859026a15394bcfbbbc1df3b6078") {
  throw new Error("Direction A prompt binding mismatch");
}
if (directionAMetadata.output.sha256 !== "4100a9de594e486ed03054a959247e8be70f29742f8b84d111873c40ec829cc7") {
  throw new Error("Direction A output binding mismatch");
}
if (ledger.baseline_commit !== "719e3179a77722e74df3ced161b350f60b5e6ad7") {
  throw new Error("iteration ledger is not bound to the audited baseline commit");
}
if (ledger.defects.length !== 9) throw new Error("unexpected baseline defect count");

const design = fs.readFileSync("plotlot/DESIGN.md", "utf8");
for (const term of [
  "Foundation tokens",
  "Route and component anatomy",
  "Semantic state contract",
  "Responsive behavior",
  "Interaction, focus, and motion",
  "Accessibility and content grounding",
  "Coverage and release readiness",
  "Token migration map",
  "raster",
]) {
  if (!design.includes(term)) throw new Error(`DESIGN.md missing ${term}`);
}

console.log(JSON.stringify({
  result: "pass",
  selected: scoring.selected_name,
  totals: Object.fromEntries(scoring.directions.map((direction) => [direction.direction_id, direction.weighted_total])),
  coverage: matrix.coverage_assertions,
  viewports: actualViewports,
  requiredStateCount: matrix.required_states.length,
  baselineDefectCount: ledger.defects.length,
  newImageCalls: packet.generation_policy.new_image_calls,
}, null, 2));
NODE

(cd plotlot/artifacts/design/direction-a && shasum -a 256 -c checksums.sha256)
(cd plotlot && shasum -a 256 -c artifacts/design/direction-b/checksums.sha256)
(cd plotlot/artifacts/design/direction-c && shasum -a 256 -c checksums.sha256)

file plotlot/artifacts/design/direction-a/reference-direction-a-v2.png
file plotlot/artifacts/design/direction-b/reference-direction-b-v1.png
file plotlot/artifacts/design/direction-c/reference-direction-c-v1.png

test "$(find .omo/evidence/todo5-design-selection/browser-baseline -name '*.png' -size +0c | wc -l | tr -d ' ')" = "13"
test "$(find .omo/evidence/todo5-design-selection/browser-baseline -name '*.aria.txt' -size +0c | wc -l | tr -d ' ')" = "12"
test "$(find .omo/evidence/todo5-design-selection/browser-baseline -name '*.json' -size +0c | wc -l | tr -d ' ')" = "14"

echo "BROWSER_ARTIFACT_COUNTS: screenshots=13 aria=12 json=14"
echo "TODO5_VERIFICATION: PASS"
