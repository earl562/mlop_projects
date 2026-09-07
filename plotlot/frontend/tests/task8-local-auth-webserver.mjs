import { createHash, randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { chmod, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";

import { SignJWT, exportJWK, generateKeyPair } from "jose";

const LOOPBACK_HOST = "127.0.0.1";
const JWKS_PORT = 58765;
const DEFAULT_FRONTEND_PORT = 3003;
const AUDIENCE = "plotlot-local";
const AUTHORIZED_PARTY = "http://127.0.0.1:3000";
const ISSUER = `http://${LOOPBACK_HOST}:${JWKS_PORT}`;
const FRONTEND_PORT = Number(process.env.PLAYWRIGHT_PORT ?? DEFAULT_FRONTEND_PORT);
const FRONTEND_URL = `http://${LOOPBACK_HOST}:${FRONTEND_PORT}`;
const BACKEND_URL = process.env.PLOTLOT_TASK8_BACKEND_URL ?? "http://127.0.0.1:58766";
const RUNTIME_DIRECTORY = join(
  tmpdir(),
  `plotlot-task8-${createHash("sha256").update(resolve(process.cwd())).digest("hex").slice(0, 16)}`,
);

const IDENTITIES = [
  ["tenant_a_owner", "tenant-a-owner", "tenant-a", "owner"],
  ["tenant_a_admin", "tenant-a-admin", "tenant-a", "admin"],
  ["tenant_a_analyst", "tenant-a-analyst", "tenant-a", "analyst"],
  ["tenant_a_reviewer", "tenant-a-reviewer", "tenant-a", "reviewer"],
  ["tenant_a_viewer", "tenant-a-viewer", "tenant-a", "viewer"],
  ["tenant_b_analyst", "tenant-b-analyst", "tenant-b", "analyst"],
];

function parsePort(value) {
  if (!Number.isInteger(value) || value < 1 || value > 65535) {
    throw new Error("The Playwright frontend port must be a valid TCP port");
  }
  return value;
}

function listen(server, port) {
  return new Promise((resolveListen, reject) => {
    server.once("error", reject);
    server.listen(port, LOOPBACK_HOST, () => {
      server.off("error", reject);
      resolveListen();
    });
  });
}

function close(server) {
  return new Promise((resolveClose) => server.close(resolveClose));
}

async function createFixture() {
  await rm(RUNTIME_DIRECTORY, { force: true, recursive: true });
  await mkdir(RUNTIME_DIRECTORY, { mode: 0o700, recursive: true });

  const { privateKey, publicKey } = await generateKeyPair("RS256");
  const kid = `plotlot-task8-${randomUUID()}`;
  const jwk = await exportJWK(publicKey);
  const now = Math.floor(Date.now() / 1000);
  const tokens = {};

  for (const [name, userId, tenantId, role] of IDENTITIES) {
    tokens[name] = await new SignJWT({
      azp: AUTHORIZED_PARTY,
      org_id: tenantId,
      org_role: `org:${role}`,
    })
      .setAudience(AUDIENCE)
      .setExpirationTime(now + 900)
      .setIssuedAt(now)
      .setIssuer(ISSUER)
      .setJti(`${name}-${randomUUID()}`)
      .setNotBefore(now - 5)
      .setProtectedHeader({ alg: "RS256", kid })
      .setSubject(userId)
      .sign(privateKey);
  }

  await writeFile(join(RUNTIME_DIRECTORY, "tokens.json"), `${JSON.stringify(tokens)}\n`, "utf8");
  await chmod(join(RUNTIME_DIRECTORY, "tokens.json"), 0o600);
  return { keys: [{ ...jwk, alg: "RS256", kid, use: "sig" }] };
}

async function main() {
  parsePort(FRONTEND_PORT);
  const jwks = await createFixture();
  const jwksPayload = JSON.stringify(jwks);
  const jwksServer = createServer((request, response) => {
    if (request.method === "GET" && request.url === "/jwks.json") {
      response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" });
      response.end(jwksPayload);
      return;
    }
    response.writeHead(404);
    response.end();
  });
  await listen(jwksServer, JWKS_PORT);

  const frontend = spawn(
    "npm",
    ["run", "dev", "--", "--hostname", LOOPBACK_HOST, "--port", String(FRONTEND_PORT)],
    {
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: `${FRONTEND_URL}/api/local-auth/backend`,
        NODE_ENV: "development",
        PLOTLOT_LOCAL_AUTH_AUDIENCE: AUDIENCE,
        PLOTLOT_LOCAL_AUTH_AUTHORIZED_PARTY: AUTHORIZED_PARTY,
        PLOTLOT_LOCAL_AUTH_BACKEND_URL: BACKEND_URL,
        PLOTLOT_LOCAL_AUTH_INTEGRATION: "1",
        PLOTLOT_LOCAL_AUTH_ISSUER: ISSUER,
        PLOTLOT_LOCAL_AUTH_JWKS_URL: `${ISSUER}/jwks.json`,
        PLOTLOT_LOCAL_AUTH_TEST_ONLY: "1",
        PLOTLOT_TEST_AUTH_BYPASS: "0",
      },
      stdio: "inherit",
    },
  );

  let shuttingDown = false;
  const shutdown = async (exitCode) => {
    if (shuttingDown) return;
    shuttingDown = true;
    frontend.kill("SIGTERM");
    await close(jwksServer);
    await rm(RUNTIME_DIRECTORY, { force: true, recursive: true });
    process.exit(exitCode);
  };
  frontend.once("exit", (code) => void shutdown(code ?? 1));
  process.once("SIGINT", () => void shutdown(0));
  process.once("SIGTERM", () => void shutdown(0));
}

main().catch(async (error) => {
  await rm(RUNTIME_DIRECTORY, { force: true, recursive: true });
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
