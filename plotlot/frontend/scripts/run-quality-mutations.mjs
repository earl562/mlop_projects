import { spawnSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";

const OUTPUT_DIR = ".quality-matrix/mutations";
const cases = [
  {
    id: "analyses-label-mapped",
    mutation: "analyses-label",
    port: "3040",
    expectedExit: 1,
    args: [
      "playwright",
      "test",
      "tests/sidebar-navigation.spec.ts",
      "--project=no-db",
      "--reporter=list",
    ],
  },
  {
    id: "analyses-label-unmapped",
    mutation: "analyses-label",
    port: "3041",
    expectedExit: 0,
    args: [
      "playwright",
      "test",
      "tests/lookup-uat.spec.ts",
      "--project=chromium",
      "--grep=miami completes",
      "--reporter=list",
    ],
  },
  {
    id: "missing-terminal-sse-mapped",
    mutation: "missing-terminal-sse",
    port: "3042",
    expectedExit: 1,
    args: [
      "playwright",
      "test",
      "tests/lookup-uat.spec.ts",
      "--project=chromium",
      "--grep=miami completes",
      "--reporter=list",
    ],
  },
  {
    id: "missing-terminal-sse-unmapped",
    mutation: "missing-terminal-sse",
    port: "3043",
    expectedExit: 0,
    args: [
      "playwright",
      "test",
      "tests/sidebar-navigation.spec.ts",
      "--project=no-db",
      "--reporter=list",
    ],
  },
  {
    id: "unhealthy-db-mapped",
    mutation: "unhealthy-db",
    port: "3044",
    expectedExit: 1,
    args: [
      "playwright",
      "test",
      "tests/lookup.db.spec.ts",
      "--project=db-backed",
      "--grep=lookup renders",
      "--reporter=list",
    ],
  },
  {
    id: "unhealthy-db-unmapped",
    mutation: "unhealthy-db",
    port: "3045",
    expectedExit: 0,
    args: [
      "playwright",
      "test",
      "tests/lookup-uat.spec.ts",
      "--project=chromium",
      "--grep=miami completes",
      "--reporter=list",
    ],
  },
];

await mkdir(OUTPUT_DIR, { recursive: true });
const results = [];

for (const mutationCase of cases) {
  const startedAt = Date.now();
  const result = spawnSync("npx", mutationCase.args, {
    cwd: process.cwd(),
    encoding: "utf8",
    env: {
      ...process.env,
      PLAYWRIGHT_PORT: mutationCase.port,
      PLOTLOT_MATRIX_LANE: `mutation-${mutationCase.id}`,
      PLOTLOT_QUALITY_MUTATION: mutationCase.mutation,
      PLOTLOT_RELEASE_GATE: "1",
    },
    maxBuffer: 10 * 1024 * 1024,
    timeout: 180_000,
  });
  const exitCode = result.status ?? 124;
  const logPath = `${OUTPUT_DIR}/${mutationCase.id}.log`;
  await writeFile(
    logPath,
    `${result.stdout ?? ""}${result.stderr ?? ""}`,
    "utf8",
  );
  results.push({
    id: mutationCase.id,
    mutation: mutationCase.mutation,
    mapped: mutationCase.expectedExit === 1,
    expectedExit: mutationCase.expectedExit,
    exitCode,
    passed: exitCode === mutationCase.expectedExit,
    durationMilliseconds: Date.now() - startedAt,
    evidence: logPath,
  });
}

const summary = {
  schemaVersion: "PlotLotFrontendQualityMutationMatrixV1",
  results,
};
await writeFile(
  `${OUTPUT_DIR}/mutation-matrix.json`,
  `${JSON.stringify(summary, null, 2)}\n`,
  "utf8",
);

const failures = results.filter((result) => !result.passed);
if (failures.length > 0) {
  console.error(JSON.stringify(failures, null, 2));
  process.exitCode = 1;
} else {
  console.log(`${results.length} mutation controls behaved as mapped`);
}
