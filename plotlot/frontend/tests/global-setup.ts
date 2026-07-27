type HealthPayload = {
  status?: unknown;
  checks?: { database?: unknown };
  capabilities?: { agent_chat_ready?: unknown };
  capability_details?: {
    agent_chat_ready?: { ready?: unknown; reason?: unknown };
  };
};

function databaseIsHealthy(payload: HealthPayload): boolean {
  const database = payload.checks?.database;
  return (
    database === "ok" ||
    (typeof database === "object" &&
      database !== null &&
      "status" in database &&
      database.status === "ok")
  );
}

function agentChatIsReady(payload: HealthPayload): boolean {
  const detailed = payload.capability_details?.agent_chat_ready?.ready;
  if (typeof detailed === "boolean") return detailed;
  return payload.capabilities?.agent_chat_ready === true;
}

async function requireReleasePreflight(lane: string): Promise<void> {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const healthUrl = new URL("/health", apiBase).toString();
  let response: Response;

  try {
    response = await fetch(healthUrl, { signal: AbortSignal.timeout(5_000) });
  } catch (error) {
    throw new Error(
      `Release ${lane} preflight could not reach ${healthUrl}: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }

  if (!response.ok) {
    throw new Error(
      `Release ${lane} preflight received HTTP ${response.status} from ${healthUrl}`,
    );
  }

  const payload = (await response.json()) as HealthPayload;
  if (lane === "db-backed" && (payload.status !== "healthy" || !databaseIsHealthy(payload))) {
    throw new Error(
      `Release db-backed preflight requires status=healthy and checks.database=ok at ${healthUrl}`,
    );
  }
  if (lane === "live" && !agentChatIsReady(payload)) {
    const reason = payload.capability_details?.agent_chat_ready?.reason;
    throw new Error(
      `Release live preflight requires agent_chat_ready at ${healthUrl}${
        reason ? `: ${String(reason)}` : ""
      }`,
    );
  }
}

export default async function globalSetup() {
  if (process.env.PLOTLOT_TEST_AUTH_BYPASS === "1") {
    throw new Error("PLOTLOT_TEST_AUTH_BYPASS is forbidden; tests must exercise authentication");
  }

  const lane = process.env.PLOTLOT_MATRIX_LANE;
  if (
    process.env.PLOTLOT_RELEASE_GATE === "1" &&
    (lane === "db-backed" || lane === "live")
  ) {
    await requireReleasePreflight(lane);
  }
}
