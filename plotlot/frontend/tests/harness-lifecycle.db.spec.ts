import { test, expect, requireHealthyBackend } from "./helpers";

let dbPreflight = {
  healthy: true,
  reason: "",
};

function backendBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
}

test.describe("Harness lifecycle db lane", () => {
  test.beforeAll(async ({ request }) => {
    dbPreflight = await requireHealthyBackend(request);
  });

  test.beforeEach(() => {
    test.skip(!dbPreflight.healthy, dbPreflight.reason);
  });

  test("workspace → project → site → analysis → tool → evidence → artifacts", async ({ request }) => {
    const base = backendBaseUrl();
    const slug = `pw-harness-${Date.now()}`;

    const wsResp = await request.post(`${base}/api/v1/workspaces`, {
      data: { name: "Playwright Harness", slug },
    });
    expect(wsResp.ok()).toBeTruthy();
    const workspace = (await wsResp.json()) as { id: string };
    expect(workspace.id).toBeTruthy();

    const projectResp = await request.post(
      `${base}/api/v1/workspaces/${workspace.id}/projects`,
      {
        data: { name: "PW Project", description: "Playwright db e2e" },
      },
    );
    expect(projectResp.ok()).toBeTruthy();
    const project = (await projectResp.json()) as { id: string };
    expect(project.id).toBeTruthy();

    const siteResp = await request.post(`${base}/api/v1/projects/${project.id}/sites`, {
      data: {
        address: "1600 Pennsylvania Ave NW, Washington, DC 20500",
        parcel_id: null,
      },
    });
    expect(siteResp.ok()).toBeTruthy();
    const site = (await siteResp.json()) as { id: string; address: string };
    expect(site.id).toBeTruthy();

    const analysisResp = await request.post(`${base}/api/v1/analyses`, {
      data: {
        workspace_id: workspace.id,
        project_id: project.id,
        site_id: site.id,
        name: "PW Analysis",
        skill_name: "zoning_research",
        metadata_json: { kind: "playwright" },
      },
    });
    expect(analysisResp.ok()).toBeTruthy();
    const analysis = (await analysisResp.json()) as { id: string };
    expect(analysis.id).toBeTruthy();

    const runResp = await request.post(`${base}/api/v1/analyses/${analysis.id}/runs`, {
      data: { input_json: { address: site.address } },
    });
    expect(runResp.ok()).toBeTruthy();
    const run = (await runResp.json()) as { id: string };
    expect(run.id).toBeTruthy();

    const toolResp = await request.post(`${base}/api/v1/tools/call`, {
      data: {
        tool_name: "geocode_address",
        arguments: { address: site.address },
        workspace_id: workspace.id,
        project_id: project.id,
        site_id: site.id,
        analysis_id: analysis.id,
        analysis_run_id: run.id,
        run_id: `pw-tool-${Date.now()}`,
        risk_budget_cents: 0,
        live_network_allowed: true,
      },
    });
    expect(toolResp.ok()).toBeTruthy();
    const tool = (await toolResp.json()) as {
      status: string;
      evidence_ids: string[];
      result?: { status?: string };
    };
    expect(tool.status).toBe("ok");
    expect(tool.result?.status).toBe("success");
    expect(tool.evidence_ids.length).toBeGreaterThan(0);

    const evidenceResp = await request.get(
      `${base}/api/v1/evidence?workspace_id=${encodeURIComponent(workspace.id)}&analysis_run_id=${encodeURIComponent(run.id)}`,
    );
    expect(evidenceResp.ok()).toBeTruthy();
    const evidence = (await evidenceResp.json()) as Array<{ id: string }>;
    expect(evidence.length).toBeGreaterThan(0);

    const documentRunId = `pw-doc-${Date.now()}`;
    const documentRequest = {
      tool_name: "generate_document",
      arguments: { title: "PW Evidence Report", evidence_ids: tool.evidence_ids },
      workspace_id: workspace.id,
      project_id: project.id,
      site_id: site.id,
      analysis_id: analysis.id,
      analysis_run_id: run.id,
      run_id: documentRunId,
    };
    const pendingDocResp = await request.post(`${base}/api/v1/tools/call`, {
      data: {
        ...documentRequest,
      },
    });
    expect(pendingDocResp.ok()).toBeTruthy();
    const pendingDocTool = (await pendingDocResp.json()) as {
      status: string;
      decision: { approval_id?: string };
    };
    expect(pendingDocTool.status).toBe("pending_approval");
    expect(pendingDocTool.decision.approval_id).toBeTruthy();

    const approvalId = pendingDocTool.decision.approval_id as string;
    const approvalResp = await request.post(
      `${base}/api/v1/approvals/${encodeURIComponent(approvalId)}/approve`,
      { data: { decided_by: "playwright" } },
    );
    expect(approvalResp.ok()).toBeTruthy();

    const docResp = await request.post(`${base}/api/v1/tools/call`, {
      data: {
        ...documentRequest,
        approval_id: approvalId,
        approved_approval_ids: [approvalId],
      },
    });
    expect(docResp.ok()).toBeTruthy();
    const docTool = (await docResp.json()) as {
      status: string;
      artifact_ids: { report_id?: string; document_id?: string };
    };
    expect(docTool.status).toBe("ok");
    expect(docTool.artifact_ids.report_id).toBeTruthy();
    expect(docTool.artifact_ids.document_id).toBeTruthy();

    const reportsResp = await request.get(
      `${base}/api/v1/artifacts/reports?workspace_id=${encodeURIComponent(workspace.id)}&project_id=${encodeURIComponent(project.id)}`,
    );
    expect(reportsResp.ok()).toBeTruthy();
    const reports = (await reportsResp.json()) as Array<{ id: string }>;
    expect(reports.map((r) => r.id)).toContain(docTool.artifact_ids.report_id);

    const docsResp = await request.get(
      `${base}/api/v1/artifacts/documents?workspace_id=${encodeURIComponent(workspace.id)}&project_id=${encodeURIComponent(project.id)}`,
    );
    expect(docsResp.ok()).toBeTruthy();
    const documents = (await docsResp.json()) as Array<{ id: string }>;
    expect(documents.map((d) => d.id)).toContain(docTool.artifact_ids.document_id);
  });
});
