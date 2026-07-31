import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const MATRIX_DIR = ".quality-matrix";
const OUTPUT_PATH = process.env.PLOTLOT_QUALITY_MATRIX_OUTPUT ??
  `${MATRIX_DIR}/quality-matrix.json`;
const PLAYWRIGHT_LANES = [
  "lookup-uat",
  "no-db",
  "vc",
  "db-backed",
  "recorded-real",
  "live",
  "visual",
  "accessibility",
  "performance",
];

async function readJson(path) {
  if (!existsSync(path)) return null;
  return JSON.parse(await readFile(path, "utf8"));
}

function playwrightCounts(report) {
  const counts = { run: 0, pass: 0, fail: 0, skip: 0 };
  const visitSuite = (suite) => {
    for (const spec of suite.specs ?? []) {
      for (const test of spec.tests ?? []) {
        counts.run += 1;
        const results = test.results ?? [];
        const last = results.at(-1);
        if (test.status === "skipped" || last?.status === "skipped") counts.skip += 1;
        else if (test.status === "expected" && last?.status === "passed") counts.pass += 1;
        else counts.fail += 1;
      }
    }
    for (const child of suite.suites ?? []) visitSuite(child);
  };
  for (const suite of report.suites ?? []) visitSuite(suite);
  return counts;
}

const vitestPath = `${MATRIX_DIR}/vitest.json`;
const vitest = await readJson(vitestPath);
const lanes = [{
  id: "component",
  framework: "vitest",
  kind: "component",
  run: vitest?.numTotalTests ?? 0,
  pass: vitest?.numPassedTests ?? 0,
  fail: vitest?.numFailedTests ?? 0,
  skip: vitest?.numPendingTests ?? 0,
  evidence: vitestPath,
}];

for (const lane of PLAYWRIGHT_LANES) {
  const evidence = `${MATRIX_DIR}/playwright-${lane}.json`;
  const report = await readJson(evidence);
  const counts = report ? playwrightCounts(report) : { run: 0, pass: 0, fail: 0, skip: 0 };
  lanes.push({
    id: lane,
    framework: "playwright",
    kind: "browser-journey",
    ...counts,
    evidence,
  });
}

const matrix = {
  schemaVersion: "PlotLotFrontendQualityMatrixV1",
  generatedAt: new Date().toISOString(),
  releasePolicy: {
    silentSkipsAllowed: false,
    dbAndLiveRequirePassingPreflight: true,
  },
  lanes,
};

await mkdir(dirname(resolve(OUTPUT_PATH)), { recursive: true });
await writeFile(OUTPUT_PATH, `${JSON.stringify(matrix, null, 2)}\n`, "utf8");
console.log(OUTPUT_PATH);
