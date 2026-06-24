import { expect, gotoHome, test } from "./helpers";

test.describe.skip("Lookup release gate workbench no-db flow", () => {
  test("shows latest lookup-correctness release blockers on the workspace", async ({
    page,
  }, testInfo) => {
    await page.route("**/api/v1/lookup-snapshots/evals/batch/release-gate**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(blockedReleaseGatePayload),
      });
    });

    await gotoHome(page);

    const panel = page.getByTestId("lookup-release-gate-panel");
    await expect(panel).toBeVisible();
    await expect(panel).toContainText("Blocked");
    await expect(panel).toContainText("latest_eval_failed");
    await expect(panel).toContainText("regression_gate_failed");
    await expect(panel).toContainText("eval_metric:pass_rate");
    await panel.scrollIntoViewIfNeeded();
    await panel.evaluate((element) =>
      element.scrollIntoView({ block: "center", inline: "nearest" }),
    );
    await expect
      .poll(async () => {
        const box = await panel.boundingBox();
        return box?.y ?? 999;
      })
      .toBeLessThan(180);
    await page.screenshot({ path: testInfo.outputPath("lookup-release-gate-page-blocked.png") });
    await panel.screenshot({ path: testInfo.outputPath("lookup-release-gate-panel-blocked.png") });

    for (const visualViewport of visualViewports) {
      await page.setViewportSize({
        width: visualViewport.width,
        height: visualViewport.height,
      });
      await panel.scrollIntoViewIfNeeded();
      await expect(panel).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(`lookup-release-gate-${visualViewport.name}.png`),
      });
    }
  });
});

const blockedReleaseGatePayload = {
  status: "success",
  suite: "lookup_correctness",
  decision: "blocked",
  release_blocked: true,
  reason: "latest_eval_failed",
  latest_run: {
    eval_run_id: "eval-e2e-regressed",
    suite: "lookup_correctness",
    status: "failed",
    created_at: "2026-06-21T14:00:00+00:00",
    completed_at: "2026-06-21T14:00:02+00:00",
    metrics: {
      pass_rate: 0.5,
      citation_coverage: 0.5,
      unsupported_claim_rate: 0,
      deterministic_calculation_reproducibility: 1,
    },
    baseline: { pass_rate: 1 },
    metric_deltas: { pass_rate: -0.5 },
    gate_failures: [
      {
        metric: "pass_rate",
        reason: "regressed",
        current: 0.5,
        baseline: 1,
      },
    ],
    improvement_log: [
      {
        source: "lookup_snapshot_eval_batch",
        researched_input: "lookup_correctness",
        changed_rule: "eval_metric:pass_rate",
        metric: "pass_rate",
        direction: "regressed",
        reason: "baseline_delta",
        affected_golden_cases: ["case-a"],
        before_score: 1,
        after_score: 0.5,
        delta: -0.5,
        gate_blocking: true,
        unresolved_risk: "baseline_regression_requires_review",
      },
    ],
    case_ids: ["case-a"],
    lookup_snapshot_ids: ["ls_case-a"],
  },
  blockers: [
    {
      code: "regression_gate_failed",
      metric: "pass_rate",
      message: "Lookup-correctness regression gate failed for pass_rate.",
      reason: "regressed",
      current: 0.5,
      baseline: 1,
    },
    {
      code: "latest_eval_failed",
      status: "failed",
      message: "Latest lookup-correctness eval run did not pass.",
    },
  ],
  evidence: [],
} as const;

const visualViewports = [
  { name: "mobile", width: 375, height: 812 },
  { name: "tablet", width: 768, height: 900 },
] as const;
