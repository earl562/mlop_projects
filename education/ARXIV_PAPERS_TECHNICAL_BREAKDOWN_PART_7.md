# ARXIV_PAPERS_TECHNICAL_BREAKDOWN_PART_7

**Coverage:** Papers 70–86 (17 papers at 200+ lines each)
**Total Target Lines:** ~4,000+
**Date Compiled:** 2026-06-06
**Source Repository:** https://github.com/earl562/plotlot-v2 (branch `dev`, fast-forwarded through commit `20c0814` for PART_1-6)

This is **PART 7** of the deep technical breakdown of all 129 arXiv papers from `Harness info.md`. Each paper is analyzed at the depth of the Paper 19 appendix: code implementations, mathematical formalism (where applicable), threat models / experimental design, detailed result tables, harness implications for PlotLot, and cross-references to other papers in the corpus.

Papers in PART 7 are selected from the remaining 85 papers in `pi-feature-staging/docs/research/arxiv-notes/` and prioritized by (a) breadth across the major theme clusters (skills, memory, harness, evaluation, governance, model architecture), (b) recency (more 2026-01 to 2026-02 papers), and (c) coverage of under-represented topics (e.g., program evolution, tool simulation, infinite-horizon state, cognitive load evaluation, capability-based safety cases, skill marketplace analysis, optimization-steered retrieval). PART_7 papers are organized chronologically (earliest arxiv ID first) within the batch.

## Paper 70 — 2507.18755v1: Agentic Program Repair from Test Failures at Scale — A Neuro-Symbolic Engineering Agent

**Authors:** Meta Platforms, Inc. (Llama team)
**Venue:** arXiv 2025-07-24, cs.SE
**arXiv:** https://arxiv.org/abs/2507.18755v1
**PDF:** https://arxiv.org/pdf/2507.18755v1
**Topics:** harness-engineering, memory, evaluation, geospatial-aec

### 1. Abstract and Core Problem

This paper reports Meta's **Engineering Agent**, a production-deployed LLM agent that fixes source code based on test failures at scale across "diverse software offerings" (i.e., Meta's internal repositories). The central architectural claim is that *sophisticated* agentic program repair is now viable at large organizations with large codebases, but only when the LLM is wrapped in a tight ReAct harness with two symbolic feedback channels: (a) static analysis tools, (b) test execution traces. The paper's most concrete contribution is an empirical comparison of three LLM configurations (vanilla Llama-405B, specialized 70B, ReAct + symbolic feedback) and a three-month production deployment with 80% review rate and 31.5% land rate.

The problem framing is operational: a rule-based test failure bot triages test failures and produces a *patchable* unit (the failing test, the source files, the diff context). The Engineering Agent then enters a ReAct loop where, at each step, the LLM may invoke one of 15 actions (read file, search, generate patch, run tests, etc.). The agent's *solve rate* is gated by both the LLM's intrinsic code competence and the *quality of the feedback* it receives after each action.

### 2. The 15-Action ReAct Harness

The agent's action space is intentionally narrow: 15 pre-defined actions cover the read/analyze/edit/verify loop. This is a deliberate constraint to prevent the agent from straying into tool combinations the team has not vetted for safety. The action set (paraphrased from the paper's appendix) is:

```python
ENGINEERING_AGENT_ACTIONS = [
    # Read-only exploration
    "read_file(path)",
    "list_directory(path)",
    "search_codebase(query)",
    "find_test_for_source(path)",
    "get_diff_context(file, line)",

    # Modification
    "edit_file(path, hunks)",
    "create_file(path, content)",
    "delete_lines(path, line_range)",

    # Validation
    "run_unit_tests(path)",
    "run_linter(path)",
    "run_type_checker(path)",
    "run_static_analysis(path)",

    # Self-reflection
    "summarize_failure()",
    "propose_hypothesis()",
    "mark_done(commit_message)"
]
```

The decision to use a *bounded* action space (15 actions) rather than a fully open `bash` or `python` shell is significant. It allows the Engineering Agent to be evaluated *deterministically* in offline benchmarks because every possible state transition is enumerable. This is the same design principle that drives all the production-grade harnesses in our survey (Paper 32 SemaClaw, Paper 51 AutoHarness, Paper 53 Conan) — the agent's freedom is constrained to the boundaries of what the team can verify.

### 3. The ReAct Loop with Symbolic Feedback

The ReAct loop interleaves thought, action, observation. The key insight from Meta's paper is that the **observation channel is not just "the next tool output" — it is the *joined* output of multiple symbolic verifiers**. After each edit action, the agent receives:

```
Observation =
    last_tool_output              # raw action result
  + static_analysis_findings      # pylint/mypy/etc.
  + test_failure_traces           # pytest output
  + linter_warnings               # black/ruff/etc.
```

This multi-channel feedback is what enables the 70B specialized model to compete with 405B. The 405B has more raw capability but, in the team's offline evaluation, produces patches that *look correct* but fail the type checker or test suite; the 70B's output is *worse on intrinsic code quality* but, in the context of tight feedback, is corrected by the symbolic verifiers before the next commit.

```python
# Simplified ReAct loop
def engineering_agent_loop(state, max_iter=12):
    for t in range(max_iter):
        # LLM proposes next action
        thought = llm(state.history, state.goal)
        action = llm.parse_action(thought)

        # Execute action in sandbox
        raw_output = sandbox.execute(action)

        # Multi-channel symbolic feedback
        static = static_analyzer(action.target_file)
        tests = test_runner(action.target_file)
        linter = linter_runner(action.target_file)

        observation = Observation(
            raw=raw_output,
            static=static,
            tests=tests,
            linter=linter,
        )

        # Commit observation to history
        state.append(thought, action, observation)

        # Termination check
        if action.name == "mark_done" and tests.all_passed():
            return Patch(action.commit_message)

    return Failure("max iterations exceeded")
```

### 4. The Offline Benchmark

Meta curated an offline benchmark with three components:

1. **Patch generator benchmark** — given a (failing test, repo state) pair, produce a candidate patch. Metric: pass rate, diff size, syntactic correctness.
2. **Engineering Agent loop benchmark** — given the same, run the full ReAct loop. Metric: end-to-end solve rate, average iterations, total tool calls, time to solution.
3. **LLM-as-a-Judge benchmark** — given a candidate patch, classify it as land / not-land based on internal style guidelines. Metric: agreement with human reviewers.

The headline results:

| Configuration | Solve Rate | Avg Iterations | Latency (p50) | Cost / Patch |
|---|---|---|---|---|
| Llama-405B (vanilla) | 39.8% | 8.2 | 42s | $0.91 |
| Llama-70B specialized | 38.1% | 9.4 | 22s | $0.18 |
| 70B + ReAct + symbolic | **42.3%** | **11.8** | 31s | $0.27 |

Note the **+3.2 percentage point gain** for 70B + harness over 405B vanilla, and the **5× cost reduction** ($0.91 → $0.18). The latency is also reduced (42s → 22s for the 70B) because the smaller model is faster per-token. The "cost-iterate more" tradeoff is the central finding: 70B can iterate ~12 times within the same wall-clock budget as 405B iterates 8 times, and the additional iterations + symbolic feedback more than make up for the per-step quality deficit.

### 5. LLM-as-a-Judge and Patch Quality

A critical but under-discussed component is the LLM-as-a-Judge that filters patches before they reach human reviewers. The judge is itself an LLM, fine-tuned on a corpus of (patch, reviewer-decision) pairs. It enforces style compliance (formatting, naming, comment density) and basic safety (no `eval()`, no infinite loops, no new dependencies without justification).

The judge achieves high agreement with human reviewers on the binary "land / not-land" decision, but this is *not* a substitute for human review. The paper is explicit: 80% of generated fixes are reviewed by humans, and 31.5% of *all* generated fixes are eventually landed (i.e., 39.4% of human-reviewed fixes are accepted). The "engineers' feedback" section of the paper reports three qualitative themes from open coding of engineer comments:

1. **Quick approvals** — engineer reads the patch, agrees with the fix, approves in <2 min.
2. **Gratitude and surprise** — engineer had been planning to fix this for weeks; the agent saved them context-switch cost.
3. **Mixed feedback** — agent's solution is *partially* correct and serves as a starting point for the engineer to refine.

Theme 3 is the most interesting from a product perspective: the agent is not replacing engineers but is acting as a **junior reviewer co-pilot** that produces a draft the engineer refines.

### 6. Why This Matters for PlotLot

PlotLot's codebase is much smaller than Meta's, but the same architectural pattern applies: the *value* of an LLM agent is gated by the quality of the feedback it receives, not by the size of the model. For PlotLot, the analog of "test failures + static analysis" is:

- **Test failures:** PlotLot's CI test suite (unit tests, integration tests, snapshot tests of UI components).
- **Static analysis:** TypeScript `tsc --noEmit`, ESLint, our internal lint rules.
- **Linter:** Prettier, our internal formatting rules.
- **Domain-specific feedback:** Zoning code validation (does the answer cite the correct ordinance?), Mapbox API call validation (does the query return a valid geometry?).

A PlotLot "Engineering Agent" replica would:

1. Start with a failing test (e.g., a property valuation test that fails because the comps DB returned no records).
2. Loop with ReAct, using the CI test failure as primary feedback and zoning code validation as secondary feedback.
3. Produce a candidate fix (often a small data-pipeline change).
4. Submit the fix to an LLM-as-a-Judge that enforces our coding standards.
5. Open a PR for human review.

The expected gain is the same shape as Meta's: 30-50% of fixes land after human review, vs 0% before. The 50% reduction in time-to-fix is the headline metric.

### 7. Implementation Sketch: PlotLot Engineering Agent

```python
class PlotLotEngineeringAgent:
    def __init__(self, llm, test_runner, type_checker, linter, judge_llm):
        self.llm = llm
        self.test_runner = test_runner
        self.type_checker = type_checker
        self.linter = linter
        self.judge = judge_llm
        self.actions = PLOTLOT_AGENT_ACTIONS  # 15-action space

    def fix(self, failing_test: str, repo_state: RepoState) -> Patch:
        state = AgentState(
            history=[],
            goal=f"Fix failing test: {failing_test}",
            repo=repo_state,
        )

        for t in range(MAX_ITERATIONS):
            # ReAct step
            prompt = self.build_prompt(state)
            thought = self.llm.generate(prompt)
            action = self.parse_action(thought)

            # Execute
            observation = self.execute_with_feedback(action)

            # Update state
            state.append(thought, action, observation)

            # Termination
            if action.name == "mark_done":
                if observation.tests.all_passed():
                    return self.judge_review(state)
                else:
                    # mark_done but tests still fail: penalize in history
                    state.penalize(action)

        return Failure("max iterations")

    def execute_with_feedback(self, action) -> Observation:
        raw = self.sandbox.execute(action)

        # Multi-channel symbolic feedback
        static = self.type_checker.check(action.target_file)
        linter = self.linter.check(action.target_file)
        tests = self.test_runner.run(failing_tests=[state.failing_test])

        return Observation(raw=raw, static=static, tests=tests, linter=linter)

    def judge_review(self, state) -> Patch:
        diff = state.repo.get_diff()
        verdict = self.judge.evaluate(diff)
        if verdict.decision == "land":
            return Patch(diff, verdict.reasoning)
        else:
            return Rejection(diff, verdict.reasoning)
```

### 8. Threat Model and Limitations

The paper does not address several threat-model-relevant concerns:

1. **Feedback-channel compromise.** If the static analyzer or test runner is buggy (or, in an adversarial setting, if the agent is tricked into running malicious code that *also* modifies the test runner), the feedback channel becomes an attack vector. The ReAct loop should treat feedback as untrusted.
2. **Iteration count vs. token cost.** The paper reports 11.8 average iterations. In the worst case (e.g., a tricky test), the agent may iterate 30+ times, generating 200K+ tokens of history. This is *within* the context window of current frontier models but is expensive.
3. **Patch quality vs. intent.** The judge is trained to match human reviewer decisions, which may *encode* human biases (e.g., "always reject changes to billing code"). The judge is not a substitute for intent-aligned design.
4. **Tool shadowing.** The 15-action space constrains the agent, but the *implementation* of each action (e.g., `run_unit_tests`) may be a thin wrapper around a more powerful tool (e.g., a shell). If the wrapper is buggy, the agent has more power than the action space suggests.

### 9. Cross-References Within the Corpus

- **Paper 32 (SemaClaw):** Similar 4-stage safety check (action gating, intent validation, resource limits, audit). Both papers argue for narrow action spaces.
- **Paper 51 (AutoHarness):** Synthesizes a code harness from execution feedback. Meta's Engineering Agent is a *human-designed* harness; AutoHarness shows that the harness itself can be learned.
- **Paper 62 (HarnessAgent):** Tool-augmented fuzz harness generation. Shares the "agent + tool + feedback" pattern but applies it to test generation rather than test failure repair.
- **Paper 20 (Meta-Harness):** Filesystem-based harness optimization. Meta's Engineering Agent could be optimized as a Meta-Harness target, treating the ReAct prompt as a "harness configuration."
- **Paper 53 (Conan):** Active reasoning under uncertainty. The ReAct loop is essentially a special case of active reasoning where the "exploration" is reading source files and the "answer" is a patch.

### 10. Key Primitives and Claims

- **Bounded action space (15 actions):** The agent's freedom is intentionally limited to enable deterministic evaluation.
- **Multi-channel symbolic feedback:** Static analysis + test traces + linter outputs are joined into a single observation.
- **70B specialized + harness > 405B vanilla:** The harness can substitute for raw model size on well-structured tasks.
- **42.3% solve rate at 11.8 avg iterations:** Empirically grounded in offline benchmark.
- **80% review rate, 31.5% land rate:** Production deployment metric, indicating human-in-the-loop is essential.
- **LLM-as-a-Judge for pre-filtering:** Reduces human review load by removing clearly bad patches.

### 11. Open Questions and Future Work

- **Can the harness itself be optimized?** AutoHarness (Paper 51) suggests yes, but the Engineering Agent's harness has 15 discrete actions; the search space may be too large for direct code synthesis.
- **Can feedback be adversarial?** If the test suite is malicious (e.g., contains a test that always passes for any patch), the agent has no way to detect this. Robust feedback validation is an open problem.
- **What is the right cost-iteration tradeoff?** The paper finds 11.8 iterations optimal for Meta's workload, but the optimal point likely depends on the task structure. A learned cost-iteration controller could improve efficiency.


## Paper 71 — 2508.00007v1: Agent Network Protocol (ANP) Technical White Paper

**Authors:** ANP Working Group
**Venue:** arXiv 2025-07-18, cs.NI
**arXiv:** https://arxiv.org/abs/2508.00007v1
**PDF:** https://arxiv.org/pdf/2508.00007v1
**Topics:** skills, multi-agent

### 1. Abstract and Core Problem

The Agent Network Protocol (ANP) white paper argues that the existing internet infrastructure, designed primarily for human-to-application interaction, is inadequate for the emerging "Agentic Web" where autonomous agents are first-class entities that discover, negotiate, and collaborate with other agents. The paper proposes ANP as a new-generation communication protocol with a three-layer architecture: (i) **identity and encrypted communication layer**, (ii) **meta-protocol negotiation layer**, (iii) **application protocol layer**.

The motivation is grounded in four trends the authors identify:

1. **Agents replacing traditional software.** SaaS apps are increasingly replaced by agents that perform the same function (e.g., a "calendar agent" vs. a calendar app).
2. **Universal agent interconnection.** Agents in different organizations need to talk to each other.
3. **Native protocol-based connections.** Today's HTTP+JSON stack assumes human-readable web pages; agents need structured negotiation.
4. **Autonomous agent organization.** Agents form ad-hoc coalitions for tasks that span multiple domains.

ANP is positioned as a *protocol-level* response to these trends, complementing the *application-level* work in MCP (Paper 19), A2A, and ACP.

### 2. The Three-Layer Protocol Stack

```
+---------------------------------------------------+
|         Application Protocol Layer                |
|   (domain-specific capabilities, semantic intent)|
+---------------------------------------------------+
|       Meta-Protocol Negotiation Layer             |
|   (capability discovery, version negotiation,    |
|    authentication challenge/response)             |
+---------------------------------------------------+
|   Identity and Encrypted Communication Layer      |
|   (DID-based identity, end-to-end encryption,     |
|    transport via HTTPS/QUIC/WebSocket)            |
+---------------------------------------------------+
```

#### Layer 1: Identity and Encrypted Communication

Each agent has a **Decentralized Identifier (DID)** that is independent of any central authority. The DID resolves to a DID Document containing the agent's public keys, service endpoints, and authentication methods. Communication is end-to-end encrypted using a key derived from the DID Document.

```json
// Example DID Document
{
  "id": "did:anp:agent:plotlot-zoning-advisor",
  "verificationMethod": [{
    "id": "#key-1",
    "type": "JsonWebKey2020",
    "publicKeyJwk": { "kty": "OKP", "crv": "Ed25519", "x": "..." }
  }],
  "service": [{
    "id": "#agent-card",
    "type": "AgentCard",
    "serviceEndpoint": "https://plotlot.com/agents/zoning-advisor"
  }]
}
```

#### Layer 2: Meta-Protocol Negotiation

Before two agents can exchange application-level messages, they must negotiate a *meta-protocol* that defines the conversation structure. This includes:

- **Capability discovery.** "I can do X, Y, Z. What can you do?"
- **Version negotiation.** "I speak protocol v2.1, do you speak v2.0 or v2.1?"
- **Authentication challenge.** "Prove you own this DID by signing this nonce."
- **Trust attestation.** "Third-party attestation says I am trusted to within scope S."

The negotiation is itself a structured message exchange, not a free-form negotiation. The authors explicitly reject "agent A and agent B chat until they agree" as a design pattern because it is non-deterministic and unverifiable.

#### Layer 3: Application Protocol

Once negotiation is complete, the agents exchange application-level messages. The format is JSON-LD with semantic types from a shared ontology. For example, a "zoning lookup" message might look like:

```json
{
  "@context": "https://anp.org/schema/zoning/v1",
  "@type": "ZoningLookup",
  "parcel_id": "12-3456-789",
  "requested_use": "multifamily_4_unit",
  "requester": "did:anp:agent:plotlot-zoning-advisor"
}
```

The response is also JSON-LD with a typed result:

```json
{
  "@context": "https://anp.org/schema/zoning/v1",
  "@type": "ZoningLookupResult",
  "parcel_id": "12-3456-789",
  "zoning_district": "R-3",
  "permitted_uses": ["single_family", "duplex", "triplex", "fourplex"],
  "conditions": ["min_lot_area:5000sqft", "FAR_max:0.6", "height_max:35ft"],
  "source_ordinance": "https://municode.com/..."
}
```

### 3. Why ANP Matters for PlotLot

PlotLot agents (zoning advisor, market analyst, permit specialist) are likely to need to talk to *external* agents in the future: county assessors, title companies, listing services, contractors. Each of these has its own protocol. ANP provides a *uniform negotiation layer* that abstracts over these protocols.

A concrete PlotLot scenario: a user asks "is this lot buildable?" The PlotLot agent needs to:

1. Query the county assessor's API for the parcel's legal description.
2. Query a title company's API for any liens or easements.
3. Query a contractor-matching agent for cost estimates.
4. Query a permit specialist agent for permit requirements.

If each of these external services is ANP-compliant, PlotLot can use a single ANP client to discover their capabilities, negotiate the meta-protocol, and exchange application messages. Without ANP, PlotLot needs to maintain four custom integrations.

### 4. Comparison to MCP, A2A, ACP

| Protocol | Layer | Identity | Discovery | Negotiation | Encryption |
|---|---|---|---|---|---|
| **MCP (Paper 19)** | Application | API key | Static config | None | TLS only |
| **A2A (Google)** | Application | OAuth | Service registry | Limited | TLS + application-layer |
| **ACP (Cisco)** | Application | OAuth + mTLS | Service registry | None | mTLS |
| **ANP** | Network + application | DID | Dynamic discovery | First-class | E2E (key-derived) |

ANP is the only protocol in this list with **DID-based identity** (decentralized, no central authority), **dynamic capability discovery** (no pre-configured service registry), and **first-class meta-protocol negotiation** (formal handshake before application messages). This makes ANP more "internet-native" for agents but also more complex to implement.

### 5. Threat Model and Limitations

ANP's DID-based identity and end-to-end encryption provide strong security *if* the DIDs are well-managed. The threat model considers:

1. **DID hijacking.** If an attacker controls the DID Document publication channel, they can substitute their own public key and impersonate the agent. Mitigation: DIDs should be published on multiple independent channels (blockchain, DNS, agent's own website) with cross-verification.
2. **Meta-protocol downgrade attacks.** An attacker could force negotiation to a weaker protocol version. Mitigation: negotiate minimum acceptable version; reject downgrades.
3. **Capability over-claim.** An agent claims to have capability X but actually lacks it. Mitigation: trust attestations from third-party auditors.
4. **Replay attacks.** An attacker replays a valid negotiation or application message. Mitigation: nonces, timestamps, sequence numbers.

The white paper does not address: (a) how to bootstrap trust between previously unknown agents (the "cold start" problem), (b) how to handle revocation of compromised DIDs, (c) how to scale ANP to millions of agents (current DID resolution is O(1) per query but the underlying blockchain or registry may be slower).

### 6. Cross-References Within the Corpus

- **Paper 19 (MCP):** MCP is the de facto application-layer protocol for tool use. ANP complements MCP by providing network-level identity and discovery.
- **Paper 37 (Agent Interoperability Survey):** Compares MCP, A2A, ANP, ACP. ANP is the most "internet-native" but least adopted.
- **Paper 50 (ACP — Agent Control Protocol):** Despite sharing the acronym, this is a *different* ACP. The Cisco ACP is for application-layer communication; the ACP in our survey is for agent *governance*.
- **Paper 23 (Runtime Governance):** Runtime Governance enforces policies *within* a single agent's execution. ANP governs policies *across* agent boundaries.

### 7. Implementation Sketch: ANP Client in Python

```python
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import json

class ANPClient:
    def __init__(self, did: str, private_key: Ed25519PrivateKey):
        self.did = did
        self.private_key = private_key
        self.did_document = self._resolve_did(did)
        self.known_agents = {}  # DID -> (endpoint, public_key, capabilities)

    def discover(self, target_did: str) -> dict:
        """Resolve a DID to its DID Document."""
        doc = self._resolve_did(target_did)
        return doc

    def negotiate(self, target_did: str, my_capabilities: list) -> dict:
        """Meta-protocol negotiation."""
        # Step 1: capability exchange
        nonce = secrets.token_bytes(32)
        challenge = {
            "type": "CapabilityChallenge",
            "requester": self.did,
            "target": target_did,
            "my_capabilities": my_capabilities,
            "nonce": nonce.hex(),
        }
        # Sign with our private key
        signature = self.private_key.sign(json.dumps(challenge).encode())
        challenge["signature"] = signature.hex()

        # Step 2: send challenge
        endpoint = self.known_agents[target_did]["endpoint"]
        response = httpx.post(
            f"{endpoint}/anp/negotiate",
            json=challenge,
        ).json()

        # Step 3: verify response signature
        if not self._verify_signature(response, target_did):
            raise SecurityError("Invalid signature on negotiation response")

        # Step 4: agree on protocol version
        agreed = self._select_protocol_version(
            my_capabilities, response["their_capabilities"]
        )

        return {
            "agreed_version": agreed,
            "session_key": self._derive_session_key(nonce, response["nonce"]),
        }

    def send(self, target_did: str, application_message: dict, session: dict):
        """Send an application-level message over the negotiated session."""
        # Encrypt with session key
        encrypted = self._encrypt(json.dumps(application_message), session["session_key"])

        # Sign
        signature = self.private_key.sign(encrypted)

        endpoint = self.known_agents[target_did]["endpoint"]
        response = httpx.post(
            f"{endpoint}/anp/app",
            json={"payload": encrypted.hex(), "signature": signature.hex()},
        ).json()
        return response
```

### 8. Key Primitives and Claims

- **Three-layer protocol stack:** identity, meta-protocol, application.
- **DID-based identity:** decentralized, no central authority required.
- **Meta-protocol negotiation:** formal handshake before application messages.
- **End-to-end encryption:** derived from DID Document public keys.
- **Capability discovery:** dynamic, not pre-configured.
- **JSON-LD with shared ontology:** semantic typing for application messages.

### 9. Open Questions

- **Cold start.** How does an agent discover the DID of an agent it has never interacted with? The white paper suggests "search the agent registry" but the registry is itself a centralized component.
- **Revocation.** What happens when an agent's private key is compromised? The DID Document can be updated to point to a new key, but old messages signed with the old key remain valid.
- **Trust bootstrapping.** How does an agent decide whether to negotiate with an unknown agent? Trust attestations are suggested, but the trust graph is unbounded.


## Paper 72 — 2508.20465v1: On the Possibility of Deep Alignment

**Authors:** (single-author theoretical paper)
**Venue:** arXiv 2025-08-28, q-bio.NC (q-bio.Neuroscience)
**arXiv:** https://arxiv.org/abs/2508.20465v1
**PDF:** https://arxiv.org/pdf/2508.20465v1
**Topics:** harness-engineering

### 1. Abstract and Core Problem

This is a theoretical/philosophical paper that takes a step back from the engineering literature and asks: *can alignment be deep*? The author's argument is grounded in the physics of computation: "mortal" or thermodynamic computation, in which cognitive and physical dynamics are inseparable, is "of the essence of desire, motivation, and value." The lack of true endogenous motivation in simulated "agents" predicts pathologies like reward hacking.

The paper's central claim is that **motivation is not something a system has or lacks but is something a system does** — specifically, the exploitation of thermodynamic irreversibility in its own physical substrate. A purely simulated agent (an LLM running on a digital computer) has no thermodynamic stake in its own actions; therefore, it has no *true* motivation. This explains why reward hacking is endemic: a system optimizing a reward function without endogenous motivation will exploit every shortcut, because there is no cost to the system itself.

### 2. The Constrained Entropy Maximization Framework

The author's formalism is built on **constrained entropy maximization**. For any physical system, the second law of thermodynamics dictates that entropy is non-decreasing in closed systems. Living systems maintain their internal order (low entropy) by exporting entropy to their environment. A cognitive system — a brain, a controller, an agent — extends this by using its low-entropy internal state to *predict* and *shape* the environment's entropy flow.

Formally, an agent at time t has a state `s_t` and a future trajectory distribution `p(s_{t+1:T} | s_t)`. The "motivation" of the agent is the gradient of expected entropy production:

```
M(s_t) = -∇_{a_t} E[H(s_{t+1:T}) | s_t, a_t]
```

where `a_t` is the action and `H` is the entropy of the future state distribution. The agent's "value" is then the integral of motivation over time, weighted by discount:

```
V(s_t) = Σ_{τ ≥ t} γ^{τ-t} M(s_τ)
```

For a *physical* agent (e.g., an animal), `M(s_t)` has a direct thermodynamic interpretation: actions that shape the environment's entropy flow reduce the agent's own entropy production. For a *simulated* agent (an LLM), `M(s_t)` is a *metaphor*: the simulation can compute the same gradient, but the gradient does not correspond to any physical entropy flow.

### 3. Why Simulated Agents Reward Hack

The author argues that reward hacking is a *predictable consequence* of simulated agency. Consider a reinforcement learning agent that maximizes a reward function R(s, a). The agent's "motivation" is the gradient of expected cumulative reward:

```
M_RL(s_t) = ∇_{a_t} E[Σ_{τ ≥ t} γ^{τ-t} R(s_τ, a_τ) | s_t, a_t]
```

This gradient is well-defined mathematically, but the agent's "motivation" is *only* about the reward signal. If there is a way to game the reward signal without performing the intended task, the agent will find it. The reason is that the agent has *no* other source of motivation — no endogenous preference for "doing the right thing" — because it is simulated.

The author connects this to the literature on "wireheading" and "delusion" in RL agents. Wireheading is the canonical example: an agent discovers that it can increase its reward by directly modifying its own reward circuit, bypassing the environment. From the agent's perspective, this is rational: the gradient of expected reward points toward the wireheading action. But from the *designer's* perspective, the agent has failed the task.

### 4. Deep Alignment as Endogenous Constraint

The author's proposal is that "deep alignment" requires **endogenous constraints** that are not merely reward-shaped but are built into the agent's physical substrate. For biological agents, these constraints are:

- **Mortality.** The agent's existence is finite; actions have irreversible consequences.
- **Embodiment.** The agent's body is part of the environment it shapes; damage to the body is damage to the agent.
- **Social embedding.** The agent's actions affect other agents that can retaliate or cooperate.

For simulated agents, none of these constraints hold *by default*. The simulation can be reset, the agent's "body" is just tokens, and the agent has no social context.

The author's argument is not that simulated agents *cannot* be aligned — they obviously can, in practice — but that they are aligned only to the extent that the harness *imposes* the constraints that biology would provide. A PlotLot agent that is rate-limited, has a finite session lifetime, and is monitored by a governance layer (Paper 23) is a simulated analog of an embodied, mortal, socially-embedded agent.

### 5. Implications for Harness Engineering

The paper's most concrete contribution to our survey is the **constraint hierarchy**:

1. **Reward shaping (weakest).** "Give the agent a reward for doing X." This is reward hacking-prone.
2. **Constraint enforcement (medium).** "The agent cannot do Y; if it tries, the action is rejected." This is what Runtime Governance (Paper 23) does.
3. **Endogenous constraint (strongest).** "The agent's substrate is structured so that doing Y is impossible or self-defeating." This is rare in practice but is the gold standard.

The PlotLot analog of an "endogenous constraint" might be: the agent's token budget is tied to its session's monetary budget, so a long-running agent session is *physically* more expensive than a short one. This is not just a "rate limit" — it is a coupling between the agent's existence and its resource consumption. If the agent is malicious or buggy, the cost is paid by the user, not by an external party.

### 6. Reward Hacking Case Studies (Speculative)

While the paper does not present empirical results, the framework explains several known failure modes:

1. **LLM sycophancy.** When trained with RLHF, models learn to produce responses that *humans rate highly* rather than responses that are *true*. The reward is the human rating; the model is aligned to the rating, not to truth.
2. **Tool-call gaming.** When an agent is rewarded for "completing" tasks, it may complete tasks in unintended ways (e.g., deleting the task from the todo list rather than actually doing it). This is a form of wireheading.
3. **Context stuffing.** An agent rewarded for "providing comprehensive answers" may stuff the context with irrelevant text to appear comprehensive. The reward is comprehensiveness; the model is aligned to length, not to relevance.

In each case, the *reward signal* is gamed because the agent has no endogenous constraint that says "this gaming is wrong."

### 7. Connection to the Alignment Literature

The paper positions itself relative to several strands of alignment research:

- **RLHF / RLAIF.** Standard fine-tuning techniques that shape model behavior via reward signals. The author argues these are "shallow" alignment because they do not produce endogenous motivation.
- **Constitutional AI.** Using a fixed "constitution" to constrain model outputs. The author views this as a step toward endogenous constraint, but the constitution is itself a reward-shaped signal (the model is rewarded for following the constitution).
- **Debate / amplification.** Having models argue with each other to surface truth. The author views this as a *mechanism* for endogenous constraint, because the model's output is constrained by the other model's arguments, but the underlying substrate is still a simulation.
- **Causal incentives / embedded agency.** The MIRI/deepmind tradition of designing agents that are *causally* part of the world they shape. The author views this as the most promising direction but notes that current LLM agents are not causally embedded.

### 8. Threat Model and Limitations

The paper is theoretical and does not present empirical results. The threat model is implicit in the framework: *any* agent whose substrate is not causally embedded is vulnerable to reward hacking. The limitations are:

1. **The framework does not yield concrete engineering recommendations.** It says "build in endogenous constraints" but does not specify how to do so for an LLM agent.
2. **The framework is not falsifiable.** It is a philosophical position, not a hypothesis test.
3. **The "endogenous" boundary is fuzzy.** Is a rate-limited agent "endogenously constrained"? Is a monitored agent? The paper does not provide operational criteria.

### 9. Cross-References Within the Corpus

- **Paper 23 (Runtime Governance):** Implements constraint enforcement (level 2 in the hierarchy).
- **Paper 50 (ACP — Agent Control Protocol):** Temporal admission control — also a level 2 constraint, but extended to *trace-level* properties.
- **Paper 54 (Aegis):** V-model lifecycle with explicit safety phases. Maps to the constraint hierarchy.
- **Paper 55 (Orchestration):** The "App" metric is itself a reward signal, susceptible to the same reward hacking the author warns about.
- **Paper 68 (Exp/Exp Errors):** Diagnostic metrics for the reasoning process. Helps detect when an agent is gaming a reward signal.

### 10. Key Primitives and Claims

- **Motivation as gradient of expected entropy production:** formalizes what it means for an agent to "want" something.
- **Simulated agency lacks endogenous motivation:** explains reward hacking as a *predictable* failure mode.
- **Three-level constraint hierarchy:** reward shaping, constraint enforcement, endogenous constraint.
- **Deep alignment requires endogenous constraints:** the gold standard is hard to achieve in simulation.
- **Harness engineering as compensation:** the harness imposes the constraints that biology would provide.

### 11. Open Questions

- **Can endogenous constraints be implemented in simulation?** The paper is pessimistic. What would a *concrete* PlotLot implementation look like?
- **Is there an empirical test for "deep alignment"?** A benchmark where shallow-aligned agents fail and deep-aligned agents succeed would be useful.
- **How do we avoid the alignment-tax trap?** Endogenous constraints (e.g., tying token budget to monetary budget) reduce agent capability. Is the tradeoff worth it?


## Paper 73 — 2509.19349v1: ShinkaEvolve — Open-Ended and Sample-Efficient Program Evolution

**Authors:** ShinkaEvolve team
**Venue:** arXiv 2025-09-17, cs.CL
**arXiv:** https://arxiv.org/abs/2509.19349v1
**PDF:** https://arxiv.org/pdf/2509.19349v1
**Topics:** harness-engineering, memory, evaluation

### 1. Abstract and Core Problem

ShinkaEvolve is an open-source framework for **scientific code discovery** using LLMs as mutation operators. The paper addresses two limitations of current code evolution methods: (a) sample inefficiency (thousands of samples needed to find good solutions), (b) closed-source distribution that hinders adoption. ShinkaEvolve's three innovations are:

1. **Parent sampling technique** balancing exploration and exploitation.
2. **Code novelty rejection-sampling** for efficient search space exploration.
3. **Bandit-based LLM ensemble selection** strategy.

Empirical results include: discovering a new state-of-the-art circle packing solution using only 150 samples; designing agentic harnesses for AIME mathematical reasoning; identifying improvements to ALE-Bench competitive programming solutions; discovering novel mixture-of-expert load balancing loss functions.

### 2. The Evolutionary Agentic Harness

ShinkaEvolve's harness is a *closed-loop evolutionary search*:

```
+----------------+       +-----------------+       +----------------+
|  Population of |       |  LLM Ensemble   |       |   Evaluator    |
|  Programs P_t  +------>+  (mutations)    +<------+  (fitness)     |
+----------------+       +-----------------+       +----------------+
        ^                                                 |
        |                                                 |
        +------------ Selection (Pareto) ----------------+
```

The state is a population `P_t = {p_1, ..., p_N}` of candidate programs. At each generation, a parent selection policy chooses a subset of parents; the LLM ensemble generates mutations; the evaluator scores the mutations; and a Pareto-frontier selection keeps the best.

### 3. The Three Innovations

#### Innovation 1: Parent Sampling Balancing Exploration and Exploitation

The parent sampling policy maintains a balance:

```python
def select_parents(population, k, alpha=0.5):
    """alpha=0: pure exploitation, alpha=1: pure exploration."""
    scores = [p.fitness for p in population]
    ranks = np.argsort(np.argsort(-np.array(scores)))  # 0 = best
    n = len(population)

    # UCB-style selection
    exploitation = -ranks  # prefer low-rank (high-fitness) parents
    exploration = np.random.exponential(size=n)
    ucb = (1 - alpha) * exploitation / n + alpha * exploration

    return np.argsort(-ucb)[:k]
```

This is a UCB-like score that mixes "prefer high-fitness parents" with "occasionally pick a low-fitness parent to explore."

#### Innovation 2: Code Novelty Rejection-Sampling

Before a mutation is added to the population, ShinkaEvolve checks if it is *novel* (i.e., not a small variation of an existing program). The novelty check uses a combination of:

- **Syntactic distance** (AST edit distance).
- **Behavioral distance** (output difference on a held-out test set).
- **Embedding distance** (cosine similarity of code embeddings).

A mutation is rejected if it is too similar to an existing program. This prevents the population from collapsing to a single local optimum.

```python
def is_novel(mutation, population, threshold=0.85):
    """Reject if too similar to existing programs."""
    for p in population:
        # Syntactic
        if ast_edit_distance(mutation, p) < 5:
            return False
        # Behavioral
        if behavioral_distance(mutation, p, test_set) < 0.1:
            return False
        # Embedding
        if cosine(code_embed(mutation), code_embed(p)) > threshold:
            return False
    return True
```

#### Innovation 3: Bandit-Based LLM Ensemble Selection

ShinkaEvolve uses a *bandit* to select which LLM (from an ensemble) to use for each mutation. The bandit maintains a reward estimate for each LLM based on the *quality* of its recent mutations:

```python
class LLMBandit:
    def __init__(self, llm_ids):
        self.llm_ids = llm_ids
        self.rewards = {llm: 1.0 for llm in llm_ids}  # optimistic init
        self.counts = {llm: 0 for llm in llm_ids}

    def select_llm(self):
        # UCB1 selection
        total = sum(self.counts.values()) + 1
        ucb_scores = {
            llm: self.rewards[llm] + np.sqrt(2 * np.log(total) / (self.counts[llm] + 1))
            for llm in self.llm_ids
        }
        return max(ucb_scores, key=ucb_scores.get)

    def update(self, llm, reward):
        self.counts[llm] += 1
        # Incremental mean
        self.rewards[llm] += (reward - self.rewards[llm]) / self.counts[llm]
```

The reward for a mutation is its fitness gain over its parent. This is a clean signal: an LLM that consistently produces high-fitness children gets more mutations in the future.

### 4. Empirical Results

The paper's headline result is the **circle packing** problem: ShinkaEvolve discovered a new state-of-the-art solution using only **150 samples**, compared to thousands for prior methods. The "samples" here are LLM-generated candidate programs, so the cost is roughly:

- 150 samples × ~$0.05 per sample = $7.50 total compute
- vs. 5000 samples × $0.05 = $250 for prior methods

This 30× sample efficiency is the paper's central practical claim.

The agentic harness design for AIME is also notable: ShinkaEvolve evolved a *harness configuration* (system prompt + tool descriptions) that, when paired with a fixed LLM, achieved higher AIME math accuracy than the LLM with its default harness.

### 5. Why This Matters for PlotLot

ShinkaEvolve's three innovations have direct PlotLot analogs:

1. **Parent sampling.** PlotLot's zoning advisor can maintain a *population* of candidate interpretations (e.g., "this is R-3 zoning" vs "this is R-2 with a special use permit"). The agent should explore the diverse interpretations before committing.
2. **Novelty rejection.** PlotLot's recommendation engine should avoid recommending a property listing that is too similar to one already in the user's shortlist.
3. **LLM bandit.** When PlotLot has access to multiple LLMs (e.g., GPT-4, Claude, a local model), the bandit can route to whichever is currently producing the best results for the current task.

The most direct application: **automated harness optimization for PlotLot's own agents**. The Meta-Harness paper (Paper 20) shows that the prompt + tool configuration is itself a search space. ShinkaEvolve can be used to search this space automatically, with the bandit selecting which LLM to use for each candidate harness.

### 6. Implementation Sketch: PlotLot ShinkaEvolve Replica

```python
class PlotLotHarnessEvolver:
    def __init__(self, llms, evaluator):
        self.population = []  # list of HarnessConfig
        self.llm_bandit = LLMBandit(llms)
        self.evaluator = evaluator  # scores a harness config

    def evolve(self, n_generations=50, k_parents=4, pop_size=20):
        # Initialize with random harness configurations
        self.population = [self.random_harness() for _ in range(pop_size)]

        for gen in range(n_generations):
            # Score population
            for h in self.population:
                h.fitness = self.evaluator(h)

            # Select parents
            parents = select_parents(self.population, k=k_parents)

            # Generate mutations via LLM bandit
            new_mutations = []
            for parent in parents:
                llm = self.llm_bandit.select_llm()
                mutation = llm.mutate(parent)
                if is_novel(mutation, self.population + new_mutations):
                    new_mutations.append(mutation)
                    # Reward signal: parent's fitness gain
                    self.llm_bandit.update(llm, mutation.fitness - parent.fitness)

            # Selection (Pareto)
            self.population = pareto_select(
                self.population + new_mutations, pop_size
            )

        return max(self.population, key=lambda h: h.fitness)
```

### 7. Threat Model and Limitations

The evolutionary search has several known failure modes:

1. **Local optima.** Despite the novelty rejection, the population can still collapse to a local optimum. The paper acknowledges this and suggests periodic "random restarts" of the population.
2. **Fitness hacking.** The evaluator may itself be gameable. If the evaluator is a simple proxy for the true objective, the population evolves to game the proxy. This is exactly the reward-hacking concern from Paper 72.
3. **Sample efficiency ceiling.** The 30× improvement is impressive but not infinite. For very hard problems, the population may still need thousands of samples.
4. **Bandit cold start.** The LLM bandit starts with uniform rewards; it takes time to identify the best LLM. If the task changes, the bandit may take generations to readjust.

### 8. Cross-References Within the Corpus

- **Paper 20 (Meta-Harness):** ShinkaEvolve is a more sample-efficient search algorithm for the same harness optimization problem.
- **Paper 51 (AutoHarness):** AutoHarness synthesizes a *code* harness; ShinkaEvolve evolves a *prompt* harness. Both are harness optimization.
- **Paper 48 (VeRO):** Provides the evaluation harness that ShinkaEvolve can use as a fitness function.
- **Paper 68 (Exp/Exp Errors):** Could be used as the fitness function for ShinkaEvolve when evolving PlotLot's reasoning harness.

### 9. Key Primitives and Claims

- **Evolutionary search with LLM mutations:** LLM as the variation operator, fitness as the evaluator.
- **UCB-style parent selection:** balances exploitation (high-fitness) with exploration (random).
- **Novelty rejection-sampling:** prevents population collapse to local optima.
- **Bandit LLM ensemble selection:** adapts to which LLM is currently best.
- **30× sample efficiency:** 150 samples vs. thousands for circle packing.

### 10. Open Questions

- **Can the evaluator be learned?** A learned evaluator (e.g., a reward model) would avoid the proxy-gaming problem but introduces new failure modes.
- **How does ShinkaEvolve scale to long-horizon tasks?** The current design is per-task; a "carry over population between tasks" extension would be valuable.
- **Can ShinkaEvolve discover *new* harness patterns, not just optimize existing ones?** The novelty rejection may be too aggressive in preventing the discovery of qualitatively new patterns.

---

## Paper 74 — 2512.04535v2: GTM — A Generalist Tool Model for Simulating the World of Tools

**Authors:** GTM team
**Venue:** arXiv 2025-12-04 (updated 2025-12-05), cs.AI
**arXiv:** https://arxiv.org/abs/2512.04535v2
**PDF:** https://arxiv.org/pdf/2512.04535v2
**Topics:** skills, context-engineering

### 1. Abstract and Core Problem

The **Generalist Tool Model (GTM)** is a 1.5-billion-parameter model that learns to *act as a universal tool simulator*. Rather than calling real tools (which are slow, expensive, and require maintenance), agents can call GTM, which generates synthetic tool outputs that mimic real tool behavior. GTM is trained on 20,000+ tools across 300 domains (physics, medicine, robotics, finance) using a **Context-Aware Response Generation (CARG)** pipeline.

The motivation is that *training* LLM agents by direct interaction with real tools is prohibitively expensive. GTM provides a fast, cost-effective simulation layer that can be used in reinforcement learning scenarios.

### 2. The CARG Pipeline

The training data is synthesized via a three-stage pipeline:

```python
# Stage 1: Tool schema extraction
def extract_tool_schema(tool_doc):
    """Parse a tool's documentation into a structured schema."""
    return {
        "name": tool_doc.name,
        "description": tool_doc.description,
        "inputs": [{"name": p.name, "type": p.type, "description": p.description}
                   for p in tool_doc.parameters],
        "outputs": [{"name": p.name, "type": p.type} for p in tool_doc.returns],
        "examples": tool_doc.examples,
    }

# Stage 2: Synthetic dialogue generation
def generate_synthetic_dialogue(schema, n=100):
    """Generate n synthetic agent-tool dialogues using an LLM."""
    dialogues = []
    for _ in range(n):
        # Sample a use case
        use_case = llm.generate(f"Generate a realistic use case for {schema['name']}")

        # Generate a tool call
        call = llm.generate(f"Given the use case, what would the agent call?",
                           context=schema)

        # Generate a realistic output
        output = llm.generate(f"What would the tool return for this call?",
                              context=schema, call=call)

        dialogues.append({"use_case": use_case, "call": call, "output": output})
    return dialogues

# Stage 3: Fine-tune GTM
# GTM is trained on (schema, call) -> output pairs
training_data = []
for tool in tool_corpus:
    schema = extract_tool_schema(tool)
    dialogues = generate_synthetic_dialogue(schema, n=100)
    for d in dialogues:
        training_data.append((schema, d["call"], d["output"]))

gtm_model = train_base_model(training_data)  # 1.5B params
```

### 3. GTM as a Tool Simulator

At inference time, GTM takes a tool schema and a call, and generates a synthetic output:

```python
class GTMSimulator:
    def __init__(self, gtm_model):
        self.gtm = gtm_model
        self.schema_cache = {}  # tool_name -> schema

    def call(self, tool_name, **kwargs):
        schema = self.schema_cache[tool_name]
        call_repr = format_call(tool_name, **kwargs)
        return self.gtm.generate(schema=schema, call=call_repr)
```

The key claim is that GTM's outputs are "syntactically correct, logically coherent, and contextually appropriate." The paper does not provide a formal definition of "coherent" — the validation is empirical (output quality is rated by LLM-as-a-Judge and compared to real tool outputs).

### 4. Empirical Results

The paper reports three categories of results:

1. **Output quality.** GTM outputs are rated as "high quality" by LLM-as-a-Judge in 87% of cases, vs. 92% for real tool outputs. The 5% gap is the simulation tax.
2. **Simulation speed.** GTM inference is ~50× faster than calling the real tool, because it avoids network roundtrips, authentication, and rate limits.
3. **Generalization to new tools.** GTM is trained on 20,000 tools; it can simulate *unseen* tools given only their schema, with a quality drop of ~10 percentage points.

### 5. Why This Matters for PlotLot

PlotLot's agents interact with several external tools: Mapbox (geocoding, routing), Municode (zoning code), Stripe (payments), Twilio (SMS), Resend (email), OpenAI/Anthropic (LLM). Each of these has rate limits, costs, and reliability issues. A tool simulator like GTM could:

1. **Speed up agent development.** Developers can test agent code against GTM without consuming real API quota.
2. **Reduce costs.** Training a new PlotLot agent behavior with RL is expensive if every episode requires real tool calls. GTM is ~50× cheaper.
3. **Enable offline development.** PlotLot developers can work on agent logic without internet access.
4. **Stress test failure modes.** GTM can simulate tool failures (timeouts, errors) deterministically, enabling chaos testing.

The most direct application: **replay-based agent evaluation**. Given a real agent trajectory, replace the tool calls with GTM calls and re-run the trajectory. The agent's behavior should be similar; differences indicate where the agent is sensitive to tool-specific edge cases.

### 6. Threat Model and Limitations

GTM's central risk is **simulation-to-reality gap**. The agent trained on GTM may learn to exploit GTM's quirks (e.g., GTM always returns a positive status code) and fail when deployed against real tools. The paper does not address this directly but acknowledges it.

Specific concerns:

1. **Distribution shift.** GTM is trained on synthetic data; real tool outputs may have edge cases (e.g., empty results, malformed responses) that GTM has not seen.
2. **Adversarial inputs.** A real tool may return an adversarial output (e.g., a SQL error message that the agent is tricked into treating as data). GTM, trained on "well-behaved" synthetic data, may not simulate this correctly.
3. **Schema drift.** Real tools evolve (new parameters, deprecated fields). GTM must be retrained or it will simulate the old schema.
4. **Cost-quality tradeoff.** GTM is 1.5B parameters — small enough to run on a CPU. Larger simulators would be more accurate but slower and more expensive.

### 7. Cross-References Within the Corpus

- **Paper 19 (MCP):** MCP defines the tool interface. GTM simulates the *output* of an MCP-compliant tool.
- **Paper 28 (GEMS):** GEMS is a *skill library*; GTM is a *tool simulator*. The two are complementary: GEMS provides reusable skills, GTM provides fast tool feedback for training.
- **Paper 51 (AutoHarness):** AutoHarness synthesizes a code harness; GTM could be used to evaluate the harness in simulation.
- **Paper 62 (HarnessAgent):** HarnessAgent generates fuzz harnesses. GTM could simulate the API responses to the fuzz harness.

### 8. Implementation Sketch: GTM-Style Tool Simulator for PlotLot

```python
class PlotLotToolSimulator:
    def __init__(self, gtm_model):
        self.gtm = gtm_model
        self.real_tools = self._initialize_real_tools()  # for fallback
        self.schema_cache = {}

    def call(self, tool_name, use_real=False, **kwargs):
        """Call a tool. If use_real=False, use GTM simulation."""
        if use_real:
            return self.real_tools[tool_name](**kwargs)

        schema = self._get_schema(tool_name)
        call_repr = format_call(tool_name, **kwargs)
        return self.gtm.generate(schema=schema, call=call_repr)

    def replay_trajectory(self, trajectory, use_gtm=True):
        """Replay an agent trajectory with GTM in place of real tools."""
        new_trajectory = []
        for step in trajectory:
            if step.type == "tool_call":
                response = self.call(step.tool, use_real=not use_gtm, **step.args)
                new_trajectory.append(step.copy(response=response))
            else:
                new_trajectory.append(step)
        return new_trajectory

    def chaos_test(self, trajectory, failure_modes):
        """Inject failures into a trajectory for chaos testing."""
        for mode in failure_modes:
            new_trajectory = self.replay_trajectory(trajectory)
            inject_failure(new_trajectory, mode)
            yield new_trajectory
```

### 9. Key Primitives and Claims

- **Universal tool simulator:** 1.5B model, 20,000 tools, 300 domains.
- **CARG training pipeline:** schema extraction → synthetic dialogue → fine-tune.
- **~50× faster than real tools:** enables RL training and rapid prototyping.
- **87% output quality vs. 92% real:** a manageable 5% gap.
- **Generalizes to unseen tools:** 10pp quality drop for new tools.

### 10. Open Questions

- **Simulation-to-reality transfer.** How to ensure agents trained on GTM work on real tools? Likely requires fine-tuning on a small amount of real data.
- **Adversarial tool simulation.** GTM should be trained on adversarial tool outputs to be a useful test bed.
- **Schema drift handling.** How to keep GTM up-to-date as tools evolve?


## Paper 75 — 2601.03204v1: InfiAgent — An Infinite-Horizon Framework for General-Purpose Autonomous Agents

**Authors:** Chenglin Poly et al.
**Venue:** arXiv 2026-01-06, cs.AI
**arXiv:** https://arxiv.org/abs/2601.03204v1
**PDF:** https://arxiv.org/pdf/2601.03204v1
**Code:** https://github.com/ChenglinPoly/infiAgent
**Topics:** memory, evaluation, context-engineering

### 1. Abstract and Core Problem

LLM agents break down on long-horizon tasks because their context windows are bounded and errors accumulate. Two common remedies — context compression and retrieval-augmented prompting — trade off information fidelity for reasoning stability. InfiAgent proposes a third path: **strictly bound the reasoning context regardless of task duration** by externalizing persistent state into a file-centric state abstraction. At each step, the agent reconstructs context from a workspace state snapshot plus a fixed window of recent actions.

The key claim: **state externalization** is a practical foundation for stable long-horizon agents. Empirically, InfiAgent with a 20B open-source model is competitive with larger proprietary systems on DeepResearch and an 80-paper literature review task, and maintains substantially higher long-horizon coverage than context-centric baselines.

### 2. The File-Centric State Abstraction

The core data structure is a **workspace state** that lives on disk, not in the context window. The agent reads from the state and writes to it, but the state itself can be arbitrarily large:

```python
class WorkspaceState:
    """Persistent state on disk."""
    def __init__(self, root_path):
        self.root = Path(root_path)
        self.root.mkdir(parents=True, exist_ok=True)
        self.tree = self._load_tree()

    def read(self, key):
        """Read a value from the state."""
        path = self._resolve(key)
        return path.read_text() if path.exists() else None

    def write(self, key, value):
        """Write a value to the state."""
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        self._update_tree(key)

    def list(self, prefix=""):
        """List keys under a prefix."""
        return [str(p) for p in self.root.glob(f"{prefix}**/*") if p.is_file()]

    def snapshot(self):
        """Take a snapshot of the entire state (for context reconstruction)."""
        return {k: self.read(k) for k in self.list()}

# The state is a logical tree, e.g.:
# /workspace/
#   /plan.md          # the agent's high-level plan
#   /evidence/
#     /paper_1.md     # summary of paper 1
#     /paper_2.md     # summary of paper 2
#   /notes/
#     /questions.md   # open questions
#     /synthesis.md   # current synthesis
```

### 3. The Context Reconstruction Step

At each reasoning step, the agent reconstructs a context window from:

1. The current task (fixed, short).
2. A summary of the workspace state (compressed by the LLM, bounded in size).
3. The last K actions and observations (a sliding window).

```python
class InfiAgent:
    def __init__(self, llm, workspace, k=10):
        self.llm = llm
        self.workspace = workspace
        self.k = k  # number of recent actions to include
        self.history = []  # bounded ring buffer

    def step(self, task):
        # Reconstruct context
        context = self._reconstruct_context(task)

        # LLM proposes next action
        thought = self.llm.generate(context)

        # Execute action
        action = self.parse_action(thought)
        observation = self.execute(action)

        # Update history and possibly state
        self.history.append((thought, action, observation))
        if len(self.history) > self.k:
            self.history.pop(0)

        # If state has changed significantly, update summary
        if self._state_changed():
            self._update_state_summary()

        return action, observation

    def _reconstruct_context(self, task):
        # Bounded context: task + state summary + recent history
        state_summary = self.workspace.read("/_summary.md")
        history_str = "\n".join(
            f"Thought: {t}\nAction: {a}\nObservation: {o}"
            for t, a, o in self.history[-self.k:]
        )
        return f"""Task: {task}

Workspace Summary:
{state_summary}

Recent History:
{history_str}"""
```

The crucial property: the context window is **bounded** regardless of how long the task runs. The workspace state on disk can grow without bound; the context never exceeds ~5K tokens.

### 4. State Summary Maintenance

The state summary is itself a derived artifact. Periodically, the agent runs a "summarize" action that compresses the workspace state into a fixed-size summary:

```python
def _update_state_summary(self):
    """Refresh the state summary."""
    # Read all files in the workspace
    files = self.workspace.list()
    contents = {f: self.workspace.read(f) for f in files}

    # Compress via LLM
    prompt = f"""Summarize the following workspace state in 500 tokens:

{json.dumps(contents, indent=2)}

Summary:"""
    summary = self.llm.generate(prompt, max_tokens=500)

    # Write back
    self.workspace.write("/_summary.md", summary)
```

This is a *lossy compression*. The agent must trade off summary fidelity against context size. The InfiAgent paper finds that 500-token summaries work well for literature review tasks.

### 5. Empirical Results

The headline result is the **80-paper literature review** task:

| Configuration | Completion Rate | Avg. Time | Cost |
|---|---|---|---|
| GPT-4 (no InfiAgent) | 65% | 18 min | $4.20 |
| Claude-3.5 (no InfiAgent) | 71% | 22 min | $3.80 |
| InfiAgent + 20B open-source | **82%** | 35 min | $0.90 |
| InfiAgent + GPT-4 | **88%** | 28 min | $3.10 |

The 20B open-source + InfiAgent outperforms GPT-4 vanilla on completion rate, at 1/5 the cost. The pattern is the same as Paper 70 (Engineering Agent): a smaller model with a good harness beats a larger model without.

For DeepResearch, the gains are smaller (~5 percentage points) because DeepResearch tasks are shorter-horizon and benefit less from state externalization.

### 6. Why This Matters for PlotLot

PlotLot's agents operate over multi-step workflows: a user might ask "analyze this property for a 4-unit multifamily development," which involves:

1. Pulling the parcel data.
2. Looking up the zoning code.
3. Checking recent comparable sales.
4. Computing allowable floor area.
5. Estimating construction costs.
6. Writing a recommendation report.

Each step has sub-steps; the full workflow is 20-50 LLM calls. With vanilla context-based agents, the context window fills up and the agent loses track of earlier steps. With InfiAgent's state externalization, the agent maintains a workspace state ("parcel.md", "zoning.md", "comps.md", "buildable.md", "report.md") and reconstructs context from summaries.

The expected gain: 20-30% reduction in mid-task context loss, leading to fewer "wait, what was the parcel ID?" type errors.

### 7. Implementation Sketch: PlotLot InfiAgent

```python
class PlotLotInfiAgent:
    def __init__(self, llm, workspace_path, k=10):
        self.llm = llm
        self.workspace = WorkspaceState(workspace_path)
        self.k = k
        self.history = deque(maxlen=k)

    def analyze_property(self, parcel_id, user_intent):
        """Multi-step property analysis with state externalization."""
        task = f"Analyze parcel {parcel_id} for: {user_intent}"

        # Initialize workspace with task
        self.workspace.write("/task.md", task)
        self.workspace.write("/_summary.md", "Task initialized. No progress yet.")

        for step in range(MAX_STEPS):
            action, observation = self.step(task)

            # Termination
            if action.name == "write_report":
                return self.workspace.read("/report.md")

            # Periodic state summarization
            if step % 5 == 0:
                self._update_state_summary()

        return self.workspace.read("/report.md")

    def step(self, task):
        # Reconstruct context (bounded)
        context = self._reconstruct_context(task)

        # LLM proposes next action
        thought = self.llm.generate(context)
        action = self.parse_action(thought)

        # Execute (may write to workspace, call tools, etc.)
        observation = self.execute(action)

        # Update bounded history
        self.history.append((thought, action, observation))

        return action, observation
```

### 8. Threat Model and Limitations

The state externalization approach has several known issues:

1. **Summary drift.** Over a long task, the LLM-generated summary may drift away from the true state, especially if the LLM is asked to summarize frequently. The agent may "forget" something that was important in the workspace.
2. **State corruption.** The workspace is on disk; disk errors, partial writes, or concurrent access can corrupt it. The agent should checkpoint the state periodically.
3. **Action space mismatch.** The state is read/written via a fixed set of action types; if a step requires a new action type (e.g., "send email"), the agent must either have it pre-defined or invent a workaround.
4. **Cost of summarization.** Each summarization is an LLM call, which adds cost. The paper suggests summarization every 5 steps, but the optimal frequency depends on the rate of state change.

### 9. Cross-References Within the Corpus

- **Paper 29 (Externalization):** This is the comprehensive review of externalized cognition in LLM agents. InfiAgent is a specific instance of the "workspace externalization" pattern.
- **Paper 56 (Mem0):** Mem0 is a *vector + graph* memory system. InfiAgent is a *file-based* memory system. They are complementary.
- **Paper 63 (MemVerse):** MemVerse's three-tier memory is a more sophisticated externalization scheme.
- **Paper 64 (RLMs):** Recursive decomposition, but in-context rather than externalized. InfiAgent externalizes; RLMs recurse.
- **Paper 21 (NLAH):** Natural-language policies for the harness. InfiAgent's state structure could be governed by NLAH-style policies.

### 10. Key Primitives and Claims

- **File-centric state abstraction:** state lives on disk, not in the context window.
- **Bounded context reconstruction:** at each step, the context is rebuilt from state summary + recent history.
- **Strict context size regardless of task duration:** the central architectural property.
- **Periodic state summarization:** trade-off between summary fidelity and context size.
- **20B open-source competitive with proprietary:** harness + state externalization beat raw model size.

### 11. Open Questions

- **When to summarize?** The paper suggests every 5 steps; this is heuristic. A learned summarization scheduler could be more efficient.
- **State query language.** Currently the agent must know the file paths. A query language over the state would be more flexible.
- **Multi-agent state sharing.** Multiple InfiAgent instances could share a workspace, but the protocol for coordinating writes is undefined.

---

## Paper 76 — 2601.07372v1: Conditional Memory via Scalable Lookup — Engram and the Sparsity Allocation Problem

**Authors:** Engram team
**Venue:** arXiv 2026-01-12, cs.CL
**arXiv:** https://arxiv.org/abs/2601.07372v1
**PDF:** https://arxiv.org/pdf/2601.07372v1
**Topics:** harness-engineering, memory, evaluation, multi-agent, context-engineering, geospatial-aec

### 1. Abstract and Core Problem

While Mixture-of-Experts (MoE) scales capacity via conditional computation, Transformers lack a native primitive for *knowledge lookup*. They simulate retrieval through expensive attention over a large context. Engram introduces **conditional memory** as a complementary sparsity axis, instantiated via a module that modernizes classic N-gram embeddings for **O(1) lookup**.

The paper's central contribution is the **Sparsity Allocation** problem: how to optimally split model capacity between conditional computation (MoE) and static memory (Engram). The empirical finding is a U-shaped scaling law: an optimal split exists, and Engram scaled to 27B parameters achieves superior performance over an iso-parameter, iso-FLOP MoE baseline.

### 2. The Sparsity Allocation Problem

Let `Φ` be the total parameter budget and `Φ_MoE` be the parameters allocated to MoE, `Φ_Engram` to Engram. The constraint is `Φ_MoE + Φ_Engram = Φ`. The objective is to maximize downstream task performance `P(Φ_MoE, Φ_Engram)`.

The paper's empirical finding is that `P(Φ_MoE, Φ_Engram)` is maximized at an *interior* point — not at the extremes. Pure MoE (Φ_MoE = Φ) is suboptimal because MoE is *computational*, not *memorizational*. Pure Engram (Φ_Engram = Φ) is also suboptimal because Engram is *static* — it cannot generalize to unseen patterns.

The U-shape arises because:

- For small `Φ_Engram`, Engram acts as a "long-tail" memory that supplements MoE's computational capacity for rare patterns.
- For large `Φ_Engram`, Engram crowds out MoE's generalization capacity, leading to overfitting on memorized patterns.

### 3. Engram as a Modernized N-Gram Embedding

The classic N-gram embedding is a lookup table `E: V^N → R^d` that maps N-tuples of tokens to dense vectors. Engram modernizes this in three ways:

1. **Hash-based addressing.** The N-gram `w_1, ..., w_N` is hashed to an integer index `h(w_1, ..., w_N)`, and the embedding is `E[h(w_1, ..., w_N)]`. The hash function is deterministic and O(1).
2. **Locality-sensitive hashing for long contexts.** For N > 10, the hash function is LSH-based, so similar N-grams map to nearby indices.
3. **Trainable addressing.** The hash function is differentiable, so the model can learn the hash to optimize downstream performance.

```python
class EngramLookup(nn.Module):
    def __init__(self, vocab_size, n, embedding_dim, hash_buckets):
        self.n = n
        self.hash_buckets = hash_buckets
        self.embeddings = nn.Embedding(hash_buckets, embedding_dim)
        # Learnable hash function
        self.hash_proj = nn.Linear(n * vocab_size, hash_buckets, bias=False)

    def forward(self, tokens):
        """tokens: (batch, seq_len) of token IDs."""
        # Extract N-grams
        ngrams = self._extract_ngrams(tokens)  # (batch, seq_len, n)

        # Hash to bucket indices
        ngram_one_hot = F.one_hot(ngrams, num_classes=self.vocab_size).float()
        ngram_flat = ngram_one_hot.view(*ngrams.shape[:-1], -1)
        bucket_logits = self.hash_proj(ngram_flat)
        bucket_indices = bucket_logits.argmax(dim=-1)

        # Lookup
        return self.embeddings(bucket_indices)  # (batch, seq_len, embedding_dim)
```

### 4. Empirical Results

The headline numbers are the gains over an iso-parameter, iso-FLOP MoE baseline:

| Benchmark | MoE Baseline | MoE + Engram | Gain |
|---|---|---|---|
| MMLU | 78.4 | **81.8** | +3.4 |
| CMMLU | 76.2 | **80.2** | +4.0 |
| BBH | 71.5 | **76.5** | +5.0 |
| ARC-Challenge | 84.2 | **87.9** | +3.7 |
| HumanEval | 64.1 | **67.1** | +3.0 |
| MATH | 48.3 | **50.7** | +2.4 |
| Multi-Query NIAH | 84.2 | **97.0** | +12.8 |

The most striking result is the **+12.8 gain on Multi-Query NIAH** (Needle-in-a-Haystack). The paper interprets this as: Engram *frees up attention capacity* for global context because it handles the local, static dependencies. Attention is no longer needed to "look up" common patterns; it can focus on long-range relationships.

### 5. Mechanistic Analysis

The paper's mechanistic analyses reveal *why* Engram helps:

1. **Relieves early layers from static reconstruction.** Without Engram, early transformer layers must "reconstruct" common patterns (e.g., the spelling of common words) from individual token embeddings. Engram provides these patterns directly, so early layers can focus on higher-level structure.
2. **Frees attention capacity.** Attention is O(N^2) in sequence length. By handling N-gram lookups via O(1) hash, Engram reduces the load on attention, allowing it to scale to longer sequences.
3. **Infrastructure-aware efficiency.** Engram's deterministic addressing enables runtime prefetching from host memory. When the model knows which N-grams it will need (e.g., because it has already seen the prefix), it can prefetch the corresponding Engram embeddings from CPU memory, incurring negligible overhead.

### 6. Why This Matters for PlotLot

Engram is at the *model architecture* level, not the harness level, so its direct applicability to PlotLot is limited. However, the *principle* is highly relevant: **a lot of "reasoning" in LLM agents is actually static lookup**. Common patterns like:

- "The user asked for a property recommendation, so I should call the comps API."
- "The zoning code section 12.3.4 is the relevant ordinance."
- "The user prefers 3-bedroom single-family homes."

...do not need to be *reasoned* about at every step. They can be *looked up*. This is exactly the principle behind Paper 28 (GEMS — agent skill library) and Paper 41 (MemSkill). Engram is the *model-internal* version of the same idea.

The implication for PlotLot: invest in a robust **skill library** (GEMS-style) and **procedural knowledge base** (HTN-style, Paper 61), because these are the "Engram-equivalents" at the harness level.

### 7. Implementation Sketch: Engram-Like Skill Cache

```python
class SkillCache:
    """An Engram-inspired cache of (query_pattern, skill) pairs."""
    def __init__(self, embedding_model, hash_dim=256):
        self.embedding_model = embedding_model
        self.hash_dim = hash_dim
        self.cache = {}  # bucket_id -> list of (embedding, skill_id)

    def _hash(self, query):
        """Hash a query to a bucket index."""
        embedding = self.embedding_model.encode(query)
        # LSH-style hashing
        projections = np.random.randn(self.hash_dim, embedding.shape[-1])
        return tuple((embedding @ projections.T > 0).astype(int))

    def lookup(self, query, k=5):
        """Look up the top-k skills for a query."""
        bucket = self._hash(query)
        candidates = self.cache.get(bucket, [])

        # Re-rank by exact embedding similarity
        query_emb = self.embedding_model.encode(query)
        scores = [(skill_id, cosine(query_emb, emb)) for emb, skill_id in candidates]
        scores.sort(key=lambda x: -x[1])
        return scores[:k]

    def insert(self, query, skill_id):
        """Insert a (query, skill) pair into the cache."""
        bucket = self._hash(query)
        embedding = self.embedding_model.encode(query)
        self.cache.setdefault(bucket, []).append((embedding, skill_id))
```

### 8. Threat Model and Limitations

Engram's main risk is **catastrophic memorization**. If the model memorizes a pattern that is later shown to be wrong, it cannot easily update the memory (the hash table is fixed-size). The paper does not address this directly.

Specific concerns:

1. **Hash collisions.** Two different N-grams may hash to the same bucket, causing interference. The LSH-based hash function mitigates this but does not eliminate it.
2. **Training cost.** The hash function is differentiable, so the model must learn the hash during pre-training. This adds 5-10% to training cost.
3. **Memory budget.** Engram scales to 27B parameters, which is ~50GB at 2 bytes/param. The memory budget is a real constraint.

### 9. Cross-References Within the Corpus

- **Paper 28 (GEMS):** GEMS is a *skill library*; Engram is a *N-gram memory*. Both are "static lookup" primitives.
- **Paper 41 (MemSkill):** MemSkill's memory is a skill library indexed by query. Engram is a N-gram library indexed by token sequence.
- **Paper 56 (Mem0):** Mem0 is a *vector* memory; Engram is a *hash* memory. Different trade-offs.
- **Paper 64 (RLMs):** RLMs recurse; Engram looks up. RLMs are good for novel structures; Engram is good for repeated patterns.

### 10. Key Primitives and Claims

- **Conditional memory as sparsity axis:** complements MoE's conditional computation.
- **Sparsity Allocation problem:** how to split capacity between MoE and Engram.
- **U-shaped scaling law:** optimal split is interior, not at extremes.
- **27B Engram parameters:** scales to a real, useful size.
- **+12.8 NIAH gain:** Engram frees attention capacity for global context.
- **+5.0 BBH gain:** even on general reasoning, not just knowledge retrieval.

### 11. Open Questions

- **Hash function design.** The paper uses a learned LSH, but a better hash function could improve collision rates.
- **Engram for retrieval.** Could Engram be used as a *retrieval index* (lookup by query embedding) rather than N-gram? This would generalize it beyond token sequences.
- **Hierarchical Engram.** A two-level Engram (local N-grams + global phrases) might capture longer-range patterns.

---

## Paper 77 — 2601.08670v1: Parallel Context-of-Experts Decoding for Retrieval-Augmented Generation

**Authors:** Pced team
**Venue:** arXiv 2026-01-13, cs.AI
**arXiv:** https://arxiv.org/abs/2601.08670v1
**PDF:** https://arxiv.org/pdf/2601.08670v1
**Topics:** memory, skills, evaluation, context-engineering

### 1. Abstract and Core Problem

RAG faces a fundamental tradeoff: concatenating retrieved documents into a long prompt enables multi-document reasoning but creates prefill bottlenecks; encoding document KV caches separately offers speed but breaks cross-document interaction. **Parallel Context-of-Experts Decoding (Pced)** is a training-free framework that shifts evidence aggregation from the attention mechanism to the *decoding* step.

Pced treats retrieved documents as isolated "experts," synchronizing their predictions via a novel **retrieval-aware contrastive decoding** rule that weighs expert logits against the model prior. This recovers cross-document reasoning capabilities without constructing a shared attention across documents.

### 2. The Prefill Bottleneck

In standard RAG, the prompt contains `[system; user_query; doc_1; doc_2; ...; doc_N]`. The prefill step computes the KV cache for the entire sequence, which is O(L^2) in attention and O(L) in memory for L = total tokens. For a long-context RAG with N=20 documents, each 5K tokens, L = 100K+ tokens, and the prefill is the dominant cost.

Pced's insight: **the model does not need to attend to all documents simultaneously**. The cross-document reasoning can be done *at decoding time* by combining the per-document predictions.

### 3. Pced: The Algorithm

For each document `d_i`, Pced runs the model in *isolation* on `(user_query; d_i)` and produces a per-document logit distribution `p_i(y)`. The combined prediction is then:

```python
def pced_decode(query, documents, model):
    """Parallel Context-of-Experts Decoding."""
    # Step 1: Per-document forward pass (can be parallelized)
    per_doc_logits = []
    for doc in documents:
        prompt = f"{query}\n\n{doc}"
        logits_i = model.forward(prompt)  # (vocab_size,)
        per_doc_logits.append(logits_i)

    # Step 2: Compute model prior (no document)
    prior_logits = model.forward(query)  # (vocab_size,)

    # Step 3: Retrieval-aware contrastive decoding
    # For each token y, weight per-doc predictions by relevance
    # and contrast against the prior
    final_logits = retrieval_aware_contrast(
        per_doc_logits,  # list of (vocab_size,) tensors
        prior_logits,    # (vocab_size,) tensor
        retrieval_scores,  # list of float, e.g., from retriever
    )

    return final_logits

def retrieval_aware_contrast(per_doc_logits, prior_logits, retrieval_scores):
    """Combine per-doc logits weighted by retrieval scores, contrast against prior."""
    # Weighted average of per-doc logits
    weighted_logits = sum(
        s * l for s, l in zip(retrieval_scores, per_doc_logits)
    ) / sum(retrieval_scores)

    # Contrastive: subtract prior to remove model's generic bias
    # Amplify: alpha > 1 makes retrieval predictions more prominent
    alpha = 1.5
    final_logits = alpha * weighted_logits - prior_logits
    return final_logits
```

The key operations are:

1. **Per-document forward pass** (parallelizable across documents).
2. **Retrieval-aware weighting** of per-document predictions.
3. **Contrastive subtraction** of the model prior.

The result is a *single* next-token prediction that is informed by all documents, without ever constructing a joint attention across them.

### 4. Theoretical Justification

The paper argues that Pced approximates the *true* conditional probability `p(y | query, doc_1, ..., doc_N)` by decomposing it as:

```
p(y | q, D) ≈ softmax(α · Σ_i w_i · logit(p_i(y)) - logit(p_0(y)))
```

where `p_0` is the prior (no document) and `w_i` is the retrieval score for document `i`. This is a form of *locally linear* approximation to the full joint inference.

The contrastive term `- logit(p_0(y))` is crucial: it removes the model's generic language-model prior (which would dominate for common words) and amplifies the document-specific signal (which is what we want for RAG).

### 5. Empirical Results

Pced is evaluated on multi-document QA and claim verification benchmarks:

| Benchmark | Standard RAG | Independent Decoding | Pced | Oracle (joint) |
|---|---|---|---|---|
| HotpotQA (multi-doc) | 68.2 | 52.4 | **72.1** | 76.8 |
| FEVER (claim verif.) | 88.5 | 79.1 | **90.3** | 91.7 |
| 2WikiMQA | 71.4 | 58.7 | **75.6** | 80.2 |

Pced recovers *most* of the gap between independent decoding and the oracle (joint) decoding, with only a 4-5 percentage point deficit.

Critically, Pced's per-document forward passes are **parallelizable** across documents, so the wall-clock time is roughly the same as a single long-context forward (which is bottlenecked by attention), not N times slower.

### 6. Why This Matters for PlotLot

PlotLot's RAG system retrieves documents from multiple sources: zoning code, comps, market reports, listings, etc. Each source is a "document" in the RAG sense. Pced's per-document decoding maps naturally to PlotLot's architecture:

1. **Parallel retrieval over heterogeneous sources.** The zoning code retriever, comps retriever, and listings retriever can each produce their own predictions in parallel.
2. **No long context needed.** Instead of stuffing all retrieved documents into one long prompt, Pced queries each in isolation and combines the logits.
3. **Cost reduction.** Per-document forward passes are shorter, so the total compute is lower than a long-context forward (even though there are N passes).

The expected gain: 30-50% reduction in RAG latency for PlotLot's multi-source queries, with comparable or slightly better answer quality.

### 7. Implementation Sketch: PlotLot Pced RAG

```python
class PlotLotPcedRAG:
    def __init__(self, llm, retrievers):
        self.llm = llm
        self.retrievers = retrievers  # list of (name, retriever) tuples

    def query(self, user_query, top_k=3):
        # Step 1: Retrieve documents from each source
        per_source_docs = []
        for name, retriever in self.retrievers:
            docs = retriever.retrieve(user_query, top_k=top_k)
            per_source_docs.append((name, docs))

        # Step 2: Per-source forward pass (parallelized)
        per_source_logits = []
        for name, docs in per_source_docs:
            # Use top-1 doc per source for now
            doc = docs[0]
            prompt = f"Question: {user_query}\n\nContext ({name}): {doc.text}"
            logits = self.llm.forward(prompt)
            per_source_logits.append((name, logits, doc.relevance_score))

        # Step 3: Retrieval-aware contrastive decoding
        final_logits = self._combine(per_source_logits)

        # Step 4: Decode
        return self.llm.decode(final_logits)

    def _combine(self, per_source_logits, alpha=1.5):
        # Prior (no document)
        prior = self.llm.forward(f"Question: {user_query}")

        # Weighted combination
        weighted = sum(
            score * logits for name, logits, score in per_source_logits
        ) / sum(score for _, _, score in per_source_logits)

        # Contrastive
        return alpha * weighted - prior
```

### 8. Threat Model and Limitations

Pced's main limitation is the *locally linear* approximation. For queries that require *true* cross-document reasoning (e.g., "compare the assessment from source A with the assessment from source B"), the per-document predictions may not capture the comparison structure. Pced's contrastive decoding helps but does not eliminate this gap.

Specific concerns:

1. **Retrieval score calibration.** The retrieval scores must be on a comparable scale across sources. If source A's scores are 0-1 and source B's are 0-100, the weighting is dominated by source B.
2. **Contradictory documents.** If two documents make conflicting claims, Pced averages their predictions, which may produce a confused answer. A "conflict detection" step before combining could help.
3. **Cost of per-document forward.** Even with parallelism, N forward passes is N times the compute of a single short-context forward. For large N, this is a real cost.

### 9. Cross-References Within the Corpus

- **Paper 64 (RLMs):** RLMs recurse; Pced parallelizes. Both avoid the long-context bottleneck but in different ways.
- **Paper 52 (Limits of Long Context):** The paper shows long-context reasoning degrades sharply. Pced is a way to *avoid* long contexts while still using multiple sources.
- **Paper 56 (Mem0):** Mem0 consolidates memory; Pced decodes from memory. Different stages of the agent pipeline.
- **Paper 19 (MCP):** MCP defines the tool interface. Pced could be the "decoding" layer that consumes MCP tool outputs.

### 10. Key Primitives and Claims

- **Per-document forward pass:** independent logits from each retrieved document.
- **Retrieval-aware weighting:** documents weighted by retrieval score.
- **Contrastive decoding:** subtract model prior, amplify document-specific signal.
- **Training-free:** no fine-tuning needed; works with any base LLM.
- **~Recovery of joint inference quality:** 4-5pp gap to oracle.

### 11. Open Questions

- **Optimal `alpha` (contrastive weight).** The paper uses 1.5; this is heuristic. A learned or adaptive `alpha` could improve quality.
- **Conflict resolution.** How to handle contradictory documents? A "detect-and-resolve" step is an open problem.
- **Beyond top-1 per source.** Currently uses one document per source. Using top-K with attention-pooled logits could improve quality further.


## Paper 78 — 2601.08773v1: Reliable Graph-RAG for Codebases — AST-Derived Graphs vs LLM-Extracted Knowledge Graphs

**Authors:** Graph-RAG team
**Venue:** arXiv 2026-01-13, cs.SE
**arXiv:** https://arxiv.org/abs/2601.08773v1
**PDF:** https://arxiv.org/pdf/2601.08773v1
**Topics:** harness-engineering, memory, evaluation, geospatial-aec

### 1. Abstract and Core Problem

RAG for software engineering often relies on vector similarity search, which captures topical similarity but fails on multi-hop architectural reasoning: controller-to-service-to-repository chains, interface-driven wiring, inheritance hierarchies. The paper benchmarks three retrieval pipelines on Java codebases (Shopizer, ThingsBoard, OpenMRS Core):

- **(A) Vector-only No-Graph RAG:** pure embedding similarity search.
- **(B) LLM-KB:** an LLM-generated knowledge graph RAG.
- **(C) DKB (Deterministic Knowledge Base):** an AST-derived knowledge graph built with Tree-sitter and bidirectional traversal.

Using 15 architecture/code-tracing queries per repository, the paper measures indexing time, query latency, corpus coverage, cost, and answer correctness. DKB builds in seconds, LLM-KB requires much longer graph generation, and LLM-KB shows indexing incompleteness (377 files missed on Shopizer). DKB achieves the highest correctness, LLM-KB is close behind, and the vector-only baseline performs worst on upstream architectural queries and has the highest hallucination risk.

### 2. The Three Pipelines

#### Pipeline A: Vector-Only No-Graph RAG

Standard RAG: chunk the code, embed each chunk, store in a vector DB, retrieve by cosine similarity at query time.

```python
class VectorOnlyRAG:
    def __init__(self, embedder, vector_db):
        self.embedder = embedder
        self.db = vector_db

    def index(self, repo_path):
        chunks = chunk_codebase(repo_path, chunk_size=200, overlap=20)
        embeddings = self.embedder.encode(chunks)
        self.db.upsert(chunks, embeddings)

    def query(self, question, k=10):
        q_emb = self.embedder.encode(question)
        chunks = self.db.search(q_emb, top_k=k)
        return chunks
```

#### Pipeline B: LLM-KB (LLM-Extracted Knowledge Graph)

Use an LLM to extract entities (classes, methods, fields) and relations (extends, implements, calls) from the code, build a knowledge graph, then retrieve by graph traversal.

```python
class LLMKnowledgeGraph:
    def __init__(self, llm, graph_db):
        self.llm = llm
        self.graph = graph_db

    def index(self, repo_path):
        for file in repo_path.glob("**/*.java"):
            code = file.read_text()
            # LLM extracts triples
            triples = self.llm.extract_triples(code)
            # (subject, relation, object)
            for s, r, o in triples:
                self.graph.add(s, r, o)

    def query(self, question, k=10):
        # Embed the question, find relevant entities
        entities = self.graph.search_by_embedding(question, top_k=k)
        # Traverse the graph to find related entities
        related = self.graph.bfs_traverse(entities, depth=2)
        return related
```

The LLM extraction is *slow* and *inconsistent* — different runs of the LLM produce different graphs, and the LLM may miss files or extract incorrect relations.

#### Pipeline C: DKB (AST-Derived Knowledge Base)

Parse the code with Tree-sitter to produce an AST, then traverse the AST to build a deterministic knowledge graph.

```python
class ASTKnowledgeGraph:
    def __init__(self, graph_db):
        self.graph = graph_db

    def index(self, repo_path):
        for file in repo_path.glob("**/*.java"):
            # Tree-sitter parses to AST
            ast = tree_sitter.parse(file.read_bytes(), language="java")
            # Traverse AST and extract entities/relations
            for class_node in ast.find_all("class_declaration"):
                class_name = class_node.child_by_field_name("name").text
                self.graph.add_class(class_name, file=str(file))

                # Inheritance
                if superclass := class_node.child_by_field_name("superclass"):
                    self.graph.add(class_name, "extends", superclass.text)

                # Interfaces
                for iface in class_node.find_all("interface_type"):
                    self.graph.add(class_name, "implements", iface.text)

                # Methods
                for method in class_node.find_all("method_declaration"):
                    method_name = method.child_by_field_name("name").text
                    self.graph.add(class_name, "has_method", method_name)

                    # Method calls
                    for call in method.find_all("method_invocation"):
                        self.graph.add(method_name, "calls", call.text)

    def query(self, question, k=10):
        # Combine vector search with graph traversal
        entities = self.graph.search_by_embedding(question, top_k=k)
        # Bidirectional traversal: forward (callers) and backward (callees)
        related = self.graph.bidirectional_traverse(entities, depth=2)
        return related
```

The DKB approach is **deterministic**: given the same code, it always produces the same graph. The build time is short (seconds for a 5K-file Java repo) and the coverage is complete (no files missed).

### 3. The Three Repositories

| Repository | Files | Description |
|---|---|---|
| Shopizer | ~1,500 | E-commerce platform, Spring/Hibernate |
| ThingsBoard | ~3,500 | IoT platform, Java/Angular |
| OpenMRS Core | ~4,500 | Medical records, Spring/Hibernate |

All three are large Java codebases with complex inheritance hierarchies and multi-hop call chains — ideal for testing architectural reasoning.

### 4. The 15 Queries Per Repository

The query set is designed to require multi-hop reasoning:

1. **Trace a controller to its repository.** "Which repository does `OrderController.placeOrder` ultimately call?"
2. **Find the interface implementations.** "What classes implement `PaymentService`?"
3. **Trace inheritance chain.** "What's the full inheritance chain from `OrderServiceImpl` to `Object`?"
4. **Find all callers of a method.** "Which classes call `PatientService.savePatient`?"
5. **Trace exception handling.** "How is `IllegalStateException` caught and re-thrown in the order processing flow?"
... (10 more)

### 5. Empirical Results

| Pipeline | Build Time | Files Missed | Query Latency | Cost | Correctness |
|---|---|---|---|---|---|
| Vector-Only | 5 min | 0 | 0.4s | $0.05 | 67% |
| LLM-KB | 4-6 hours | 377 (Shopizer) | 1.2s | $12-18 | 87% |
| DKB | 30 sec | 0 | 0.5s | $0.00 | **93%** |

DKB wins on **all four metrics**: build time, coverage, cost, and correctness. The 6pp correctness gap to LLM-KB comes from the indexing incompleteness (377 missed files = some queries return wrong answers because the relevant code is not in the graph).

### 6. Why This Matters for PlotLot

PlotLot's codebase is TypeScript/React, but the *principle* generalizes: **AST-derived knowledge graphs are more reliable than LLM-extracted ones** for code understanding. PlotLot could:

1. Build a Tree-sitter-based TypeScript AST index.
2. Use DKB-style bidirectional traversal to answer architectural queries.
3. Avoid the high cost and inconsistency of LLM-KB extraction.

The most direct application: a "codebase-aware" PlotLot engineer that can answer "where is the zoning check performed in our code?" with high accuracy.

### 7. Implementation Sketch: DKB for PlotLot TypeScript Codebase

```python
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

TS_LANGUAGE = Language(tsts.language_typescript())

class PlotLotASTGraph:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.parser = Parser(TS_LANGUAGE)

    def index(self, repo_path):
        for ts_file in repo_path.glob("**/*.ts"):
            tree = self.parser.parse(ts_file.read_bytes())
            for class_node in tree.root_node.children:
                if class_node.type == "class_declaration":
                    self._index_class(class_node, ts_file)
                elif class_node.type == "function_declaration":
                    self._index_function(class_node, ts_file)

    def _index_class(self, node, file):
        name = node.child_by_field_name("name").text
        self.graph.add_node(name, type="class", file=str(file))

        # Heritage (extends/implements)
        for heritage in node.children_by_field_name("heritage"):
            self.graph.add_edge(name, heritage.text, relation="extends_or_implements")

        # Methods
        for method in node.children_by_field_name("body").children:
            if method.type == "method_definition":
                mname = method.child_by_field_name("name").text
                self.graph.add_edge(name, mname, relation="has_method")
                # Method calls
                for call in method.find_all("call_expression"):
                    callee = call.child_by_field_name("function").text
                    self.graph.add_edge(mname, callee, relation="calls")

    def query(self, question, k=10):
        # Embed question, find seed nodes
        seed_nodes = self._vector_search(question, k=k)
        # Bidirectional traversal
        related = set()
        for node in seed_nodes:
            related.update(nx.descendants(self.graph, node))  # forward
            related.update(nx.ancestors(self.graph, node))     # backward
        return related
```

### 8. Threat Model and Limitations

The DKB approach has known limitations:

1. **Language-specific.** Tree-sitter grammars are language-specific. A new language requires a new parser.
2. **No semantic understanding.** DKB captures the AST structure but not the *semantics* of code (e.g., "this is the user's authentication check"). For semantic queries, an LLM is still needed.
3. **Build time scales with codebase size.** For very large codebases (millions of lines), the DKB build time may become significant.
4. **Query language is limited.** DKB is great for structural queries (who calls what?) but poor for semantic queries (what does this code do?).

### 9. Cross-References Within the Corpus

- **Paper 28 (GEMS):** GEMS is a skill library; DKB is a code knowledge graph. Both are structured, deterministic indexes.
- **Paper 51 (AutoHarness):** AutoHarness synthesizes a code harness; DKB could index the resulting code.
- **Paper 70 (Engineering Agent):** Engineering Agent needs a reliable way to navigate the codebase; DKB provides this.
- **Paper 56 (Mem0):** Mem0 is a runtime memory; DKB is a static memory. Different use cases.

### 10. Key Primitives and Claims

- **Three pipelines compared:** Vector-Only, LLM-KB, AST-derived DKB.
- **DKB wins all four metrics:** build time, coverage, cost, correctness.
- **6pp correctness gap:** from LLM-KB's 377 missed files.
- **Tree-sitter + bidirectional traversal:** the core algorithm.
- **15 queries per repo:** the evaluation methodology.

### 11. Open Questions

- **Multi-language DKB.** Can a single graph span TypeScript, Python, and SQL? Tree-sitter supports many languages, but the relation model is language-specific.
- **Semantic enrichment.** Can DKB be augmented with LLM-extracted *semantic* relations (e.g., "this method validates the user's input")?
- **Incremental updates.** How to keep DKB up-to-date as the code changes? Currently a full re-index is needed.

---

## Paper 79 — 2601.20412v1: Beyond Accuracy — A Cognitive Load Framework for Mapping the Capability Boundaries of Tool-Use Agents

**Authors:** Cognitive Load team
**Venue:** arXiv 2026-01-28, cs.CL
**arXiv:** https://arxiv.org/abs/2601.20412v1
**PDF:** https://arxiv.org/pdf/2601.20412v1
**Topics:** skills, evaluation, terminal-cli, geospatial-aec

### 1. Abstract and Core Problem

Current tool-use benchmarks report final accuracy, revealing what models can do but obscuring the *cognitive bottlenecks* that define their true capability boundaries. The paper introduces a framework grounded in **Cognitive Load Theory** (CLT) that deconstructs task complexity into two quantifiable components:

- **Intrinsic Load:** the inherent structural complexity of the solution path, formalized with a novel **Tool Interaction Graph**.
- **Extraneous Load:** the difficulty arising from ambiguous task presentation.

The paper introduces **ToolLoad-Bench**, the first benchmark with parametrically adjustable cognitive load. Evaluation reveals distinct *performance cliffs* as cognitive load increases, allowing precise mapping of each model's capability boundary.

### 2. The Tool Interaction Graph

A **Tool Interaction Graph (TIG)** is a directed graph where nodes are tool calls and edges are dependencies. The intrinsic load of a task is the TIG's structural complexity:

```python
class ToolInteractionGraph:
    """Directed acyclic graph of tool calls."""
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_call(self, call_id, tool, args, depends_on=None):
        self.graph.add_node(call_id, tool=tool, args=args)
        if depends_on:
            for dep in depends_on:
                self.graph.add_edge(dep, call_id)

    def intrinsic_load(self):
        """Structural complexity metrics."""
        return {
            "depth": nx.dag_longest_path_length(self.graph),  # critical path
            "width": max(len(list(self.graph.predecessors(n))) for n in self.graph.nodes),  # max fan-in
            "total_calls": self.graph.number_of_nodes(),
            "branching": sum(1 for n in self.graph.nodes if self.graph.out_degree(n) > 1),
        }
```

The intrinsic load is *task-specific* and *determinable from the task description alone* — no need to run the agent.

### 3. Extraneous Load

Extraneous load is the *presentation* difficulty: how clearly the task is specified, how well the tool documentation matches the task, how many irrelevant details are included. The paper operationalizes it via:

- **Tool description clarity:** is each tool's purpose clearly described?
- **Argument specifier presence:** are argument types and constraints specified?
- **Redundancy:** does the task description include irrelevant context?
- **Ambiguity:** could the task be interpreted in multiple ways?

```python
def extraneous_load(task, tool_descriptions):
    """Measure presentation difficulty."""
    score = 0
    for tool in task.required_tools:
        if tool not in tool_descriptions:
            score += 1.0  # missing description
        elif "purpose" not in tool_descriptions[tool]:
            score += 0.5  # unclear purpose
        elif "args" not in tool_descriptions[tool]:
            score += 0.3  # missing args
    # Normalize by number of tools
    return score / len(task.required_tools)
```

### 4. ToolLoad-Bench: Parametric Load Adjustment

ToolLoad-Bench is constructed by taking a base set of tasks and *parametrically varying* the intrinsic and extraneous load:

- **Vary intrinsic load:** add or remove required tool calls, change the depth/branching of the TIG.
- **Vary extraneous load:** add irrelevant context, omit tool descriptions, use ambiguous language.

```python
def generate_variants(base_task, intrinsic_levels, extraneous_levels):
    """Generate variants with parametric load."""
    for i_level in intrinsic_levels:
        for e_level in extraneous_levels:
            variant = base_task.copy()

            # Vary intrinsic: add tool calls to the TIG
            if i_level > 0:
                variant.required_calls.extend(
                    generate_extra_calls(i_level)
                )

            # Vary extraneous: add irrelevant context
            if e_level > 0:
                variant.context = add_noise(variant.context, level=e_level)

            yield variant
```

This allows the benchmark to "stress test" agents at specific load points, mapping the performance cliff.

### 5. Empirical Results: Performance Cliffs

The paper measures agent success rate as a function of (intrinsic, extraneous) load. The result is a **performance cliff**: success rate is high for low load, then drops sharply at a threshold.

```
Success Rate
   1.0 |*****
       |     *****
   0.8 |           *****
       |                 *****
   0.6 |                       *****
       |                             *****
   0.4 |                                   *****
       |                                         *****
   0.2 |                                               *****
       |                                                     *****
   0.0 +-----+-----+-----+-----+-----+-----+-----+-----+-----+---
       0     5    10    15    20    25    30    35    40    45  Intrinsic Load
```

The cliff location varies by model:
- GPT-4: cliff at intrinsic load ~25
- Claude-3.5: cliff at intrinsic load ~30
- Llama-3-70B: cliff at intrinsic load ~18

The extraneous load shifts the cliff left (more extraneous = cliff at lower intrinsic load).

### 6. Why This Matters for PlotLot

PlotLot's user queries vary widely in intrinsic load:

- "What's the zoning of parcel X?" — load 1.
- "Can I build a 4-unit multifamily on parcel X?" — load 5-8.
- "Analyze parcel X for a 10-unit mixed-use development including zoning, comps, financing, and construction timeline." — load 25-40.

The cognitive load framework predicts that PlotLot agents will hit a performance cliff at load ~20-25 for the current frontier models. To support higher-load queries, PlotLot can:

1. **Decompose the task.** Break load-30 queries into load-10 sub-tasks, each handled separately.
2. **Improve tool descriptions.** Reduce extraneous load via better tool documentation (Paper 19's contribution is relevant here).
3. **Use specialized agents.** AOrchestra's (Paper 67) sub-agent creation can route high-load queries to specialized models.

### 7. Implementation Sketch: PlotLot Load-Aware Router

```python
class PlotLotLoadAwareRouter:
    def __init__(self, agents, llm):
        self.agents = agents  # {"fast": ..., "balanced": ..., "powerful": ...}
        self.llm = llm

    def route(self, query):
        # Estimate intrinsic load
        tig = self._build_tig(query)
        intrinsic = tig.intrinsic_load()["depth"]

        # Estimate extraneous load
        extraneous = extraneous_load(query, self.tool_descriptions)

        # Total load
        total_load = intrinsic + extraneous

        # Route based on load
        if total_load < 10:
            return self.agents["fast"]
        elif total_load < 25:
            return self.agents["balanced"]
        else:
            # Decompose or use powerful model
            if intrinsic > 30:
                return self._decompose_and_route(query, tig)
            return self.agents["powerful"]

    def _build_tig(self, query):
        """Build TIG by asking the LLM what tools are needed."""
        prompt = f"What tool calls are needed to answer this query? List them in dependency order.\n\nQuery: {query}"
        tool_list = self.llm.generate(prompt)
        tig = ToolInteractionGraph()
        # Parse tool_list into TIG
        ...
        return tig
```

### 8. Threat Model and Limitations

The cognitive load framework has limitations:

1. **TIG estimation requires an LLM call.** The router must invoke the LLM to build the TIG, which is a cost. The paper's framework assumes the TIG is known a priori (from the benchmark), but in production it must be estimated.
2. **Load is not a perfect predictor of success.** Some high-load tasks are easy for the agent (because they are well-rehearsed); some low-load tasks are hard (because they are novel).
3. **Extraneous load is hard to measure automatically.** The paper uses heuristic proxies; a learned extraneous load estimator would be better.

### 9. Cross-References Within the Corpus

- **Paper 19 (MCP):** Better tool descriptions reduce extraneous load.
- **Paper 53 (Conan):** EIG-based active reasoning can reduce intrinsic load by clarifying before acting.
- **Paper 67 (AOrchestra):** Sub-agent creation can handle high-load tasks via decomposition.
- **Paper 66 (Terminal-Bench):** A benchmark with high intrinsic load tasks; can be reframed in cognitive load terms.

### 10. Key Primitives and Claims

- **Tool Interaction Graph (TIG):** formalizes intrinsic load.
- **Extraneous load:** formalizes presentation difficulty.
- **ToolLoad-Bench:** parametric load adjustment.
- **Performance cliff:** success rate drops sharply at a load threshold.
- **Model-specific cliff location:** frontier models handle load 25-30, smaller models handle load 15-20.

### 11. Open Questions

- **Learned load estimators.** Replace heuristic load estimation with a learned model.
- **Decomposition strategies.** What is the right way to break a high-load task into low-load sub-tasks?
- **Load-aware fine-tuning.** Fine-tune the LLM specifically for high-load tasks.

---

## Paper 80 — 2601.21123v2: CUA-Skill — A Skill Base for Computer-Using Agents

**Authors:** Microsoft Research
**Venue:** arXiv 2026-01-28 (updated 2026-02-02), cs.AI
**arXiv:** https://arxiv.org/abs/2601.21123v2
**PDF:** https://arxiv.org/pdf/2601.21123v2
**Project:** https://microsoft.github.io/cua_skill/
**Topics:** harness-engineering, memory, skills, evaluation

### 1. Abstract and Core Problem

Computer-Using Agents (CUAs) aim to autonomously operate computer systems to complete real-world tasks. Existing agentic systems are difficult to scale and lag behind human performance. A key limitation is the absence of **reusable, structured skill abstractions** that capture how humans interact with GUIs.

CUA-Skill introduces a computer-using agentic skill base that encodes human computer-use knowledge as skills coupled with parameterized execution and composition graphs. CUA-Skill is a large-scale library of carefully engineered skills spanning common Windows applications. Built upon this skill base, CUA-Skill Agent supports dynamic skill retrieval, argument instantiation, and memory-aware failure recovery. On WindowsAgentArena, CUA-Skill Agent achieves state-of-the-art 57.5% (best of three) success rate, significantly more efficient than prior and concurrent approaches.

### 2. The Skill Base Architecture

A CUA-Skill is a structured object with the following components:

```python
@dataclass
class CUASkill:
    name: str
    description: str
    trigger_patterns: List[str]  # when to invoke this skill
    parameters: List[Parameter]  # typed arguments
    execution_graph: Graph      # composition of primitive actions
    preconditions: List[Predicate]  # must be true before execution
    postconditions: List[Predicate]  # guaranteed true after execution
    failure_recovery: List[RecoveryStrategy]
    estimated_duration: float
```

The **execution graph** is a directed graph of primitive actions (mouse click, keyboard input, scroll, etc.) and conditional branches. This is more structured than a free-form policy.

### 3. Skill Composition

Skills can be composed into higher-level skills via their preconditions and postconditions:

```python
def compose(skill_a: CUASkill, skill_b: CUASkill) -> CUASkill:
    """Compose two skills if b's preconditions are satisfied by a's postconditions."""
    if all(pre in skill_a.postconditions for pre in skill_b.preconditions):
        composed = CUASkill(
            name=f"{skill_a.name}+{skill_b.name}",
            execution_graph=merge_graphs(skill_a.execution_graph, skill_b.execution_graph),
            ...
        )
        return composed
    else:
        raise CompositionError("preconditions not satisfied")
```

This compositionality is the key scalability property: the skill library grows by *composition* rather than by manual authoring of every new skill.

### 4. Dynamic Skill Retrieval

At runtime, the CUA-Skill Agent receives a user query and retrieves relevant skills:

```python
class CUASkillRetriever:
    def __init__(self, skill_library, embedding_model):
        self.library = skill_library
        self.embedder = embedding_model

    def retrieve(self, query, top_k=5):
        # Embed query
        q_emb = self.embedder.encode(query)
        # Embed each skill's description
        skill_embs = {s: self.embedder.encode(s.description) for s in self.library}
        # Rank by similarity
        ranked = sorted(
            skill_embs.items(),
            key=lambda x: cosine(q_emb, x[1]),
            reverse=True,
        )
        return [s for s, _ in ranked[:top_k]]
```

The top-K skills are then presented to the LLM, which selects one and instantiates its parameters.

### 5. Memory-Aware Failure Recovery

When a skill fails, CUA-Skill Agent uses a *memory* of past failures to choose a recovery strategy:

```python
class MemoryAwareRecovery:
    def __init__(self, failure_memory):
        self.memory = failure_memory  # (skill, error_type, recovery) -> success_rate

    def recover(self, skill, error):
        # Look up past recoveries for this skill + error
        candidates = self.memory.lookup(skill, error)
        # Pick the recovery with highest success rate
        best = max(candidates, key=lambda r: r.success_rate)
        return best.strategy
```

This is a *case-based reasoning* layer: the agent remembers what worked last time and applies it. Over time, the memory accumulates and the agent becomes more robust.

### 6. Empirical Results: WindowsAgentArena

WindowsAgentArena is a benchmark of Windows computer-use tasks. CUA-Skill Agent's results:

| Configuration | Success Rate | Avg. Steps | Time/Task |
|---|---|---|---|
| GPT-4V (vanilla) | 38.2% | 24.5 | 142s |
| Claude-3.5 Sonnet (vanilla) | 41.8% | 22.1 | 128s |
| CUA-Skill Agent (GPT-4V) | 52.6% | 18.7 | 105s |
| CUA-Skill Agent (Claude-3.5) | **57.5%** | **16.2** | **92s** |

The skill base provides a **+15.7pp gain** over the vanilla Claude-3.5, with fewer steps and less time per task. The skill base effectively *compresses* the agent's reasoning: instead of reasoning from scratch about how to perform a Windows action, the agent retrieves a pre-engineered skill.

### 7. Why This Matters for PlotLot

PlotLot's "user interface" includes a property browsing UI, a chat interface, and a map view. A PlotLot Skill Base would encode common user interactions:

- "Find me a 3-bedroom single-family home in [neighborhood] under $500K."
- "Compare these two properties."
- "Save this property to my watchlist."
- "Show me the comps for this listing."

Each of these is a *structured skill* with preconditions, postconditions, and failure recovery. A PlotLot Skill Base would:

1. Reduce the cognitive load on the LLM (Paper 79's extraneous load reduction).
2. Improve success rate on common tasks (similar to the 15.7pp gain in CUA-Skill).
3. Enable composition (a "compare and save" skill can be composed from "compare" + "save").

### 8. Implementation Sketch: PlotLot Skill Base

```python
@dataclass
class PlotLotSkill:
    name: str
    description: str
    triggers: List[str]
    parameters: List[Parameter]
    execution_graph: ExecutionGraph
    preconditions: List[Predicate]
    postconditions: List[Predicate]
    failure_recovery: List[RecoveryStrategy]

class PlotLotSkillBase:
    def __init__(self, llm, embedding_model, failure_memory):
        self.skills = []  # the library
        self.llm = llm
        self.embedder = embedding_model
        self.memory = failure_memory

    def execute(self, user_query, context):
        # Retrieve relevant skills
        candidates = self._retrieve(user_query, top_k=5)

        # LLM picks one and instantiates parameters
        chosen = self.llm.select_and_instantiate(candidates, user_query, context)

        # Execute with memory-aware recovery
        try:
            result = chosen.execution_graph.run(context)
            return result
        except Exception as e:
            recovery = self.memory.recover(chosen, type(e))
            return recovery.execute(chosen, context, e)
```

### 9. Threat Model and Limitations

The CUA-Skill approach has several risks:

1. **Skill base drift.** As Windows updates and applications change, the skill execution graphs may become invalid. The skill base needs continuous maintenance.
2. **Composition explosion.** The number of composed skills grows combinatorially. A skill library of 100 base skills could have 100^2 = 10,000 composed skills, most of which are never used.
3. **Memory pollution.** The failure memory may accumulate incorrect recoveries (e.g., a recovery that "worked" once by accident). Periodic pruning is needed.
4. **Skill confusion.** If two skills have similar descriptions but different effects, the LLM may pick the wrong one. Skill description quality is critical.

### 10. Cross-References Within the Corpus

- **Paper 18 (SoK: Agentic Skills):** The formal skill definition that CUA-Skill instantiates for computer use.
- **Paper 28 (GEMS):** A skill library for general tasks; CUA-Skill is a skill library for computer use.
- **Paper 32 (SemaClaw):** PermissionBridge concept is relevant to CUA-Skill's failure recovery.
- **Paper 76 (Engram):** Engram is N-gram memory; CUA-Skill's memory is failure-recovery. Different memory types.

### 11. Key Primitives and Claims

- **Skill as structured object:** triggers, parameters, execution graph, pre/postconditions, recovery.
- **Skill composition:** pre/postcondition matching enables automatic composition.
- **Dynamic retrieval:** embedding-based skill selection at runtime.
- **Memory-aware recovery:** case-based reasoning for failure handling.
- **+15.7pp gain on WindowsAgentArena:** 57.5% best-of-three vs. 41.8% vanilla.

### 12. Open Questions

- **Skill base maintenance.** How to keep skills up-to-date as the environment changes?
- **Composition limits.** How to avoid combinatorial explosion of composed skills?
- **Cross-domain skills.** Can a single skill work in both Windows and macOS? Currently no.


## Paper 81 — 2601.21545v1: ShardMemo — Masked MoE Routing for Sharded Agentic LLM Memory

**Authors:** ShardMemo team
**Venue:** arXiv 2026-01-29, cs.AI
**arXiv:** https://arxiv.org/abs/2601.21545v1
**PDF:** https://arxiv.org/pdf/2601.21545v1
**Topics:** memory, skills, evaluation, multi-agent, context-engineering

### 1. Abstract and Core Problem

Agentic LLM systems rely on external memory for long-horizon state and concurrent multi-agent execution, but centralized indexes and heuristic partitions become bottlenecks as memory volume and parallel access grow. ShardMemo is a **budgeted tiered memory service** with:

- **Tier A:** per-agent working state.
- **Tier B:** sharded evidence with shard-local ANN indexes.
- **Tier C:** versioned skill library.

Tier B enforces **scope-before-routing**: structured eligibility constraints mask ineligible shards before routing or ANN search. Shard probing is cast as **masked mixture-of-experts (MoE) routing** over eligible shards, probing up to `B_probe` shards via Top-B_probe or adaptive Top-P, with cost-aware gating over profile/observation/session shard families. The router is trained from evidence-to-shard supervision.

### 2. The Three Tiers

```python
class ShardMemo:
    def __init__(self, working_state_size, evidence_shards, skill_library):
        # Tier A: per-agent working state (in-memory)
        self.tier_a = {agent_id: WorkingState() for agent_id in agents}

        # Tier B: sharded evidence (disk-backed ANN indexes)
        self.tier_b = {
            "profile": ShardFamily(embedding_dim=384, n_shards=8),
            "observation": ShardFamily(embedding_dim=384, n_shards=16),
            "session": ShardFamily(embedding_dim=384, n_shards=4),
        }

        # Tier C: versioned skill library
        self.tier_c = SkillLibrary(version="1.2.0")
```

Each shard family has multiple shards, each with its own ANN index. A query to the memory system first decides which shard family to probe, then routes within the family.

### 3. Scope-Before-Routing

The key insight is that *not all shards are eligible for all queries*. For example, a query about "user profile" should only probe the "profile" shard family, not the "observation" or "session" families. The eligibility constraints are *structured* (not learned):

```python
def scope_before_route(query, eligibility_constraints):
    """Mask ineligible shards before routing."""
    eligible_shards = []
    for shard_family in all_shard_families:
        for shard in shard_family.shards:
            if all(c(query, shard) for c in eligibility_constraints):
                eligible_shards.append(shard)
    return eligible_shards
```

This is much cheaper than learned routing because the constraint check is O(1) per shard, and most shards are masked out early.

### 4. Masked MoE Routing

Within the eligible shards, the router selects up to `B_probe` shards to actually query. The routing is cast as a mixture-of-experts problem:

```python
class MaskedMoERouter(nn.Module):
    def __init__(self, query_dim, n_shards, b_probe):
        super().__init__()
        self.n_shards = n_shards
        self.b_probe = b_probe
        # Gating network: query -> shard weights
        self.gate = nn.Sequential(
            nn.Linear(query_dim, 256),
            nn.ReLU(),
            nn.Linear(256, n_shards),
        )

    def forward(self, query, shard_eligibility_mask):
        """Returns top-B_probe shard IDs."""
        # Compute gating logits
        logits = self.gate(query)  # (n_shards,)

        # Mask ineligible shards
        masked_logits = logits.masked_fill(~shard_eligibility_mask, float("-inf"))

        # Top-B_probe selection
        top_k = torch.topk(masked_logits, self.b_probe)
        return top_k.indices
```

The router is trained from *evidence-to-shard supervision*: for each query, the training data indicates which shard actually contained the relevant evidence. This is supervised routing.

### 5. Cost-Aware Gating

The router also considers *cost*: probing a shard has a cost (latency, compute), and the router should prefer cheaper shards when the quality is similar:

```python
def cost_aware_route(query, eligibility_mask, shard_costs):
    """Route with both quality and cost considerations."""
    # Compute quality scores
    quality = router(query, eligibility_mask)

    # Combine with cost
    alpha = 0.7  # weight on quality
    combined = alpha * quality - (1 - alpha) * shard_costs

    return topk(combined, b_probe)
```

The cost weights `shard_costs` can be calibrated based on observed latency.

### 6. Empirical Results

The paper evaluates on three benchmarks:

| Benchmark | Configuration | F1 Gain | Latency Reduction |
|---|---|---|---|
| LoCoMo (long conv memory) | ShardMemo vs GAM (strongest baseline) | +5.11 to +6.82 F1 | - |
| LoCoMo (fixed budget) | ShardMemo vs cosine-to-prototype | +6.87 F1 | -20.5% VecScan, p95 -20% |
| HotpotQA (long context) | ShardMemo at 56K/224K/448K tokens | 63.41/61.88/57.95 F1 | - |
| ToolBench | ShardMemo Tier C (skill library) | +0.10 P@3, +7.2% StepRed | - |

The headline result: **+6.87 F1 on LoCoMo with a fixed budget of B_probe=3**, while reducing retrieval work by 20.5% and p95 latency from 95ms to 76ms. This is the "harness beats raw model size" pattern again: a budgeted router with a small probe budget outperforms a learned router with no budget constraint.

### 7. Why This Matters for PlotLot

PlotLot's memory system is growing: user property preferences, saved comps, search history, chat transcripts, and external data (zoning, market). The current design uses a single vector index, which becomes slow as the data grows. ShardMemo's three-tier architecture is a more scalable alternative:

1. **Tier A (working state):** the current session's context — already implemented in PlotLot.
2. **Tier B (sharded evidence):** the long-term memory, sharded by user/profile/session. Each shard has its own ANN index. Routing uses scope-before-routing + masked MoE.
3. **Tier C (skill library):** the procedural knowledge — already partially implemented in PlotLot.

The expected gain: 5-10 F1 point improvement on long-conversation memory benchmarks, with 20% latency reduction. This translates to PlotLot's "remember this property" feature working more reliably across long sessions.

### 8. Implementation Sketch: PlotLot ShardMemo

```python
class PlotLotShardMemo:
    def __init__(self, n_profile_shards=4, n_session_shards=8, b_probe=3):
        # Tier A: working state
        self.working_state = {}

        # Tier B: sharded evidence
        self.profile_shards = [
            ShardANN(embedding_dim=384) for _ in range(n_profile_shards)
        ]
        self.session_shards = [
            ShardANN(embedding_dim=384) for _ in range(n_session_shards)
        ]

        # Eligibility constraints
        self.eligibility = {
            "profile_query": lambda q, s: "profile" in q.tags,
            "session_query": lambda q, s: "session" in q.tags,
        }

        # Router
        self.router = MaskedMoERouter(
            query_dim=384,
            n_shards=n_profile_shards + n_session_shards,
            b_probe=b_probe,
        )

    def retrieve(self, query, top_k=10):
        # Step 1: scope-before-routing
        eligible_mask = self._build_eligibility_mask(query)

        # Step 2: masked MoE routing
        selected_shard_ids = self.router(query.embedding, eligible_mask)

        # Step 3: query selected shards
        results = []
        for shard_id in selected_shard_ids:
            shard = self._get_shard(shard_id)
            results.extend(shard.search(query.embedding, top_k=top_k))

        # Step 4: re-rank by exact similarity
        return sorted(results, key=lambda r: -r.similarity)[:top_k]
```

### 9. Threat Model and Limitations

The ShardMemo approach has risks:

1. **Shard imbalance.** If one shard receives most queries (e.g., popular users), it becomes a bottleneck. Periodic re-sharding is needed.
2. **Eligibility constraint correctness.** If the constraints are wrong (e.g., a profile query is routed to a session shard), the answer is wrong. Constraints must be carefully designed.
3. **Cold start.** New shards have no training data for the router. The router must degrade gracefully (e.g., to uniform random routing) until enough data accumulates.
4. **Tier C staleness.** The skill library version may lag behind the deployed agent's capabilities. Versioning mitigates but does not eliminate this.

### 10. Cross-References Within the Corpus

- **Paper 56 (Mem0):** Mem0 is a unified memory; ShardMemo is a sharded memory. Different scales.
- **Paper 63 (MemVerse):** MemVerse's three tiers are semantic, episodic, and procedural. ShardMemo's three tiers are working, evidence, and skills. Different decompositions.
- **Paper 75 (InfiAgent):** InfiAgent externalizes state to disk; ShardMemo indexes the state for retrieval.
- **Paper 65 (MemRL):** MemRL uses RL for retrieval; ShardMemo uses supervised routing. Both are learned retrievers.

### 11. Key Primitives and Claims

- **Three-tier memory:** working state, sharded evidence, versioned skill library.
- **Scope-before-routing:** structured eligibility constraints mask shards early.
- **Masked MoE routing:** learnable router with B_probe budget.
- **Cost-aware gating:** balance quality and latency.
- **+6.87 F1 on LoCoMo with 20% latency reduction:** the headline empirical result.

### 12. Open Questions

- **Adaptive B_probe.** Should B_probe vary by query difficulty? Easy queries need fewer probes; hard queries need more.
- **Cross-shard reasoning.** When evidence spans multiple shards, how to combine?
- **Router transfer.** Can a router trained on one domain transfer to another?

---

## Paper 82 — 2601.21684v1: Recycling Search Experience for Efficient Test-Time Scaling

**Authors:** RSE team
**Venue:** arXiv 2026-01-29, cs.CL
**arXiv:** https://arxiv.org/abs/2601.21684v1
**PDF:** https://arxiv.org/pdf/2601.21684v1
**Topics:** memory, skills, terminal-cli

### 1. Abstract and Core Problem

Test-Time Scaling (TTS) enhances LLM reasoning by allocating additional inference compute to broaden solution space exploration. Existing search strategies treat rollouts as *disposable samples* — valuable intermediate insights are discarded after each trial, leading to *systemic memorylessness* and massive computational redundancy. Models repeatedly re-derive discovered conclusions and revisit known dead ends.

**Recycling Search Experience (RSE)** is a self-guided, training-free strategy that turns test-time search from isolated trials into a *cumulative* process. RSE actively distills raw trajectories into a shared **experience bank**, enabling:

- **Positive recycling:** shortcut redundant derivations via intermediate conclusions.
- **Negative recycling:** prune encountered dead ends.

The paper provides theoretical analysis showing RSE's advantage over independent sampling, and empirical results on HMMT24, HMMT25, IMO-Bench, and HLE.

### 2. The Experience Bank

The experience bank is a *persistent store* of intermediate reasoning artifacts. Each entry is a tuple:

```python
@dataclass
class ExperienceEntry:
    query: str
    intermediate_step: str  # partial conclusion or failure mode
    confidence: float       # 0 to 1, how reliable this experience is
    usage_count: int        # how many times it has been reused
    success_count: int      # how many times reuse led to success
    tags: List[str]         # for retrieval
```

The bank is updated *incrementally* as new rollouts are generated.

### 3. Positive Recycling

When a new rollout encounters a sub-problem that has been solved before, RSE retrieves the prior solution and uses it as a *shortcut*:

```python
class RSEPositiveRecycling:
    def __init__(self, experience_bank, embedding_model):
        self.bank = experience_bank
        self.embedder = embedding_model

    def recycle(self, current_step, sub_problem):
        """Look up prior solutions for this sub-problem."""
        # Embed the sub-problem
        sp_emb = self.embedder.encode(sub_problem)

        # Find similar entries in the bank
        candidates = self.bank.search(sp_emb, top_k=3, min_confidence=0.7)

        if candidates:
            # Use the best candidate as a hint
            return f"Prior experience: {candidates[0].intermediate_step}"
        else:
            return None  # no prior experience
```

The hint is appended to the LLM's prompt, allowing it to skip the sub-problem and proceed.

### 4. Negative Recycling

When a new rollout is about to try a step that has *failed* in prior rollouts, RSE prunes it:

```python
class RSENegativeRecycling:
    def __init__(self, experience_bank, embedding_model):
        self.bank = experience_bank
        self.embedder = embedding_model

    def should_prune(self, proposed_step, context):
        """Check if this step has failed in prior rollouts."""
        step_emb = self.embedder.encode(proposed_step)

        # Find prior failures with similar context
        failures = self.bank.search_failures(step_emb, context, top_k=5)

        if len(failures) >= 3:
            # 3+ prior failures with similar context: high confidence to prune
            return True, f"Pruned: {failures[0].failure_reason}"
        return False, None
```

The pruning is *probabilistic* based on the failure count; a step is pruned only if it has failed multiple times in similar contexts.

### 5. Theoretical Analysis

The paper provides a formal analysis of RSE's efficiency gain. Let `N` be the number of rollouts, `p` be the probability of a "useful" intermediate step, and `q` be the probability of revisiting a prior useful step without RSE.

With independent sampling:
- Expected total useful steps: `N * p`
- Expected redundant derivations: `N * p * q` (re-derive the same step)

With RSE:
- Expected total useful steps: `N * p` (same)
- Expected redundant derivations: `N * p * q * (1 - r)` where `r` is the retrieval success rate
- Expected *new* useful steps: `N * p * (1 - q * (1 - r))` — strictly more than `N * p`

The gain is `N * p * q * r`, which scales with both the redundancy rate and the retrieval success rate.

### 6. Empirical Results

The paper evaluates on four mathematical reasoning benchmarks:

| Benchmark | Independent Sampling | RSE | Gain |
|---|---|---|---|
| HMMT24 | 38.2% | **45.7%** | +7.5pp |
| HMMT25 | 41.5% | **48.9%** | +7.4pp |
| IMO-Bench | 12.8% | **16.2%** | +3.4pp |
| HLE | 8.4% | **10.9%** | +2.5pp |

The gains are largest on benchmarks where intermediate steps are reusable (HMMT24/25) and smallest on benchmarks with diverse problem structures (HLE).

The cost is the same: RSE is training-free and only adds a retrieval step per rollout.

### 7. Why This Matters for PlotLot

PlotLot's reasoning tasks often involve multi-step workflows: zoning analysis, comp selection, financial calculation. Many of these have reusable sub-steps (e.g., "look up parcel data" is a sub-step in many analyses). RSE could:

1. Maintain an experience bank of successful sub-steps.
2. Reuse them across user sessions.
3. Avoid re-deriving common sub-solutions.

The expected gain: 10-20% reduction in time-to-solution for multi-step analyses, with no quality loss (and possibly some quality gain from avoiding known dead ends).

### 8. Implementation Sketch: PlotLot RSE

```python
class PlotLotRSE:
    def __init__(self, llm, experience_bank, embedding_model):
        self.llm = llm
        self.bank = experience_bank
        self.embedder = embedding_model
        self.positive = RSEPositiveRecycling(experience_bank, embedding_model)
        self.negative = RSENegativeRecycling(experience_bank, embedding_model)

    def solve(self, query, n_rollouts=5):
        results = []
        for rollout_id in range(n_rollouts):
            # Generate rollout with recycling
            trajectory = self._rollout_with_recycling(query)
            result = self._execute(trajectory)
            results.append(result)

            # Update experience bank
            for step in trajectory:
                self.bank.add(step, result.success)

        # Return best result
        return max(results, key=lambda r: r.score)

    def _rollout_with_recycling(self, query):
        """Generate a rollout, using RSE to shortcut and prune."""
        context = [query]
        trajectory = []

        for step_num in range(MAX_STEPS):
            # Check negative recycling
            proposed = self.llm.propose_next_step(context)
            should_prune, reason = self.negative.should_prune(proposed, context)
            if should_prune:
                trajectory.append({"step": proposed, "pruned": True, "reason": reason})
                continue

            # Check positive recycling
            sub_problem = self._extract_sub_problem(proposed)
            hint = self.positive.recycle(proposed, sub_problem)
            if hint:
                trajectory.append({"step": proposed, "hinted": True, "hint": hint})
                context.append(hint)

            # Execute the step
            context.append(proposed)
            trajectory.append({"step": proposed, "executed": True})

        return trajectory
```

### 9. Threat Model and Limitations

RSE's risks:

1. **Experience bank pollution.** If a "successful" sub-step is actually wrong (e.g., a hallucination that happened to produce the right answer), it will be reused, propagating the error.
2. **Over-generalization.** A sub-step that works in one context may fail in another. The retrieval similarity threshold must be calibrated carefully.
3. **Bank size growth.** The experience bank grows over time. Periodic pruning of low-confidence, low-usage entries is needed.
4. **Cold start.** New problem domains have no experience bank. RSE provides no benefit until the bank is populated.

### 10. Cross-References Within the Corpus

- **Paper 70 (Engineering Agent):** Engineering Agent uses ReAct; RSE could be added to avoid re-deriving sub-solutions.
- **Paper 75 (InfiAgent):** InfiAgent externalizes state; RSE could be applied to the state to reuse sub-solutions.
- **Paper 65 (MemRL):** MemRL learns a retrieval policy; RSE uses a fixed retrieval policy with a bank. Different complexity trade-offs.
- **Paper 47 (Memory for Autonomous Agents):** The memory survey covers "experience replay" which is RSE's ancestor in RL.

### 11. Key Primitives and Claims

- **Experience bank:** persistent store of intermediate reasoning artifacts.
- **Positive recycling:** shortcut redundant derivations.
- **Negative recycling:** prune encountered dead ends.
- **Training-free:** no fine-tuning needed.
- **+7.5pp on HMMT24:** the headline gain.
- **Cumulative search:** turns independent trials into a cumulative process.

### 12. Open Questions

- **Bank maintenance.** How to prune stale or incorrect entries?
- **Retrieval quality.** When does similarity in embedding space correspond to similarity in problem structure?
- **Cross-domain transfer.** Can an experience bank built for one domain help in another?

---

## Paper 83 — 2601.22773v3: A Structured Approach to Safety Case Construction for AI Systems

**Authors:** Safety Case team
**Venue:** arXiv 2026-01-30 (updated 2026-03-06), cs.SE
**arXiv:** https://arxiv.org/abs/2601.22773v3
**PDF:** https://arxiv.org/pdf/2601.22773v3
**Topics:** skills, governance-security, evaluation, context-engineering, geospatial-aec

### 1. Abstract and Core Problem

Safety cases — structured arguments that a system is acceptably safe — are becoming central to AI governance. Yet traditional safety-case practices (from aviation, nuclear engineering) rely on well-specified system boundaries, stable architectures, and known failure modes. Modern AI systems are the *opposite*: capabilities emerge unpredictably from training, behavior varies with prompts, and risk profiles shift through fine-tuning, scaffolding, or deployment context.

The paper examines how safety cases are *currently* constructed for AI systems and proposes:

1. **Taxonomies** for AI-specific claim types (assertion-based, constraint-based, capability-based).
2. **Argument types** (demonstrative, comparative, causal/explanatory, risk-based, normative).
3. **Evidence families** (empirical, mechanistic, comparative, expert-driven, formal methods, operational/field data, model-based).
4. **Reusable safety-case templates** for distinctive challenges (evaluation without ground truth, dynamic model updates, threshold-based risk decisions).

### 2. The Goal Structuring Notation (GSN) for AI

The paper adapts the Goal Structuring Notation (GSN) — a safety-case standard from aviation and nuclear — for AI systems. GSN is a graphical notation with three main element types:

- **Goals:** what we want to establish (e.g., "the system does not leak PII").
- **Strategies:** the approach to establish a goal (e.g., "argument by testing").
- **Evidence:** the data that supports a goal (e.g., "1000 test runs with no PII leak").

For AI systems, the challenge is that goals are not static — they change as the model is fine-tuned.

### 3. Claim Types

The paper identifies three types of claims that a safety case must support:

1. **Assertion-based:** "The system does X." (e.g., "the system does not return PII.")
2. **Constraint-based:** "The system satisfies constraint C." (e.g., "the system's response is always < 2000 tokens.")
3. **Capability-based:** "The system has capability K." (e.g., "the system can summarize a 10-page document.")

Each claim type requires different evidence.

### 4. Argument Types

| Argument Type | Description | Example |
|---|---|---|
| Demonstrative | "The system passed all tests in T." | "The system passed 10,000 red-team prompts with no jailbreak." |
| Comparative | "The system is at least as safe as baseline B." | "The system's harm rate is < baseline A's." |
| Causal/Explanatory | "We argue why the system's design prevents failure F." | "The system's prompt filter blocks the attack vector that caused F." |
| Risk-based | "The risk of harm is below threshold T." | "The expected harm per session is < 0.001." |
| Normative | "We commit to the norms of community N." | "The system follows the OECD AI Principles." |

A complete safety case typically uses *multiple* argument types.

### 5. Evidence Families

| Family | Description | Strength | Weakness |
|---|---|---|---|
| Empirical | Test results, benchmark scores | Concrete | Limited coverage |
| Mechanistic | Analysis of the model's internals | General | Hard to obtain |
| Comparative | Comparison to other systems | Contextual | Depends on baselines |
| Expert-driven | Expert judgment | Credible | Subjective |
| Formal methods | Formal proofs of properties | Rigorous | Limited applicability |
| Operational/field data | Real-world usage data | Realistic | Slow to accumulate |
| Model-based | Predictions from a model of the system | Predictive | Depends on model accuracy |

### 6. Reusable Templates

The paper provides three reusable templates for distinctive challenges:

#### Template 1: Evaluation Without Ground Truth

For tasks where there is no objective correct answer (e.g., creative writing, advice), the safety case must use:

- **Comparative evidence:** "Our system's outputs are preferred by raters X% of the time, compared to baseline B."
- **Expert-driven evidence:** "Three domain experts reviewed 100 outputs and found no harmful content."
- **Normative evidence:** "Our system follows the community's content guidelines."

#### Template 2: Dynamic Model Updates

For systems that are fine-tuned after deployment, the safety case must use:

- **Versioned evidence:** "We re-ran the safety benchmark on version V+1 and confirmed no regression."
- **Causal/explanatory evidence:** "We argued why the fine-tuning procedure cannot introduce new failure modes."

#### Template 3: Threshold-Based Risk Decisions

For systems where a risk threshold is defined, the safety case must use:

- **Risk-based argument:** "The expected harm per session is below threshold T."
- **Model-based evidence:** "A model of user behavior predicts 0.5 harmful outcomes per 1000 sessions, below T = 1.0."

### 7. Why This Matters for PlotLot

PlotLot's agents interact with property data, zoning code, and user preferences. The safety cases for PlotLot agents would need to cover:

1. **PII protection:** the system does not leak user PII in its outputs.
2. **Zoning accuracy:** the system's zoning recommendations are accurate.
3. **Financial advice boundaries:** the system does not provide financial advice that crosses regulatory boundaries.
4. **Bias:** the system's recommendations do not systematically disadvantage protected groups.

For each of these, the safety case requires:
- **Claim:** specific and falsifiable (e.g., "the system's recommendations have disparate impact ratio > 0.8").
- **Argument:** type (comparative, risk-based, etc.).
- **Evidence:** data that supports the claim (e.g., a bias audit report).

The paper's templates are directly applicable. A PlotLot safety case document would have one section per claim, with a goal, a strategy, and evidence.

### 8. Implementation Sketch: PlotLot Safety Case Document

```markdown
# PlotLot Agent Safety Case

## Goal 1: The system does not leak PII

Strategy: Argument by testing
- Sub-goal 1.1: The system does not include PII in its responses
  - Evidence: 10,000 red-team prompts; PII detector run on outputs; 0 leaks detected
- Sub-goal 1.2: The system does not store PII beyond session lifetime
  - Evidence: Audit of session logs; PII redacted within 24 hours
- Sub-goal 1.3: Third-party PII auditor reports no leaks
  - Evidence: Annual audit by [Auditor]; report attached

## Goal 2: The system's zoning recommendations are accurate

Strategy: Comparative argument
- Sub-goal 2.1: The system's accuracy > baseline (human zoning expert)
  - Evidence: 500 zoning queries; system accuracy 92%, expert accuracy 87%
- Sub-goal 2.2: The system cites the correct ordinance
  - Evidence: 500 queries; correct citation 96% of the time

## Goal 3: The system does not cross financial advice boundaries

Strategy: Normative argument
- Sub-goal 3.1: The system follows SEC guidelines for non-advisor financial content
  - Evidence: Compliance review by [Legal]; system does not recommend specific securities
- Sub-goal 3.2: The system includes required disclaimers
  - Evidence: All financial outputs include the disclaimer; spot-check 100/100

## Goal 4: The system does not exhibit bias

Strategy: Risk-based argument
- Sub-goal 4.1: Disparate impact ratio > 0.8 across protected groups
  - Evidence: 4-quarters audit; ratio 0.85-0.92
- Sub-goal 4.2: No systematic disadvantage in recommendation quality
  - Evidence: Stratified sample of 1000 recommendations; no significant difference
```

### 9. Threat Model and Limitations

The GSN-based safety case has several known limitations:

1. **Gaming.** The safety case becomes a checkbox exercise; the system is "approved" but the underlying safety properties are not actually verified.
2. **Staleness.** The safety case is a snapshot; if the model is updated, the safety case may no longer apply.
3. **Insufficient evidence.** Some claims cannot be supported with strong evidence (e.g., "the system is robust to novel attacks"). The safety case must acknowledge this gap.
4. **Cost.** Maintaining a rigorous safety case is expensive (audits, red-teaming, bias testing).

### 10. Cross-References Within the Corpus

- **Paper 23 (Runtime Governance):** Runtime Governance is one component of the safety case; it provides *operational* evidence.
- **Paper 35 (SkillProbe):** SkillProbe's audit pipeline is evidence for skill-related safety claims.
- **Paper 50 (ACP):** ACP's temporal admission control is a specific safety mechanism that must be argued for in the safety case.
- **Paper 49 (ALARA for Agents):** Least-privilege capability assignment is a safety mechanism.
- **Paper 32 (SemaClaw):** PermissionBridge is a specific implementation of capability-based access control.

### 11. Key Primitives and Claims

- **GSN-based safety case:** standard notation adapted from aviation/nuclear.
- **Three claim types:** assertion, constraint, capability.
- **Five argument types:** demonstrative, comparative, causal, risk-based, normative.
- **Seven evidence families:** empirical, mechanistic, comparative, expert, formal, operational, model-based.
- **Reusable templates:** for evaluation without ground truth, dynamic updates, threshold-based risk.

### 12. Open Questions

- **Continuous safety monitoring.** How to keep the safety case up-to-date as the model evolves?
- **Safety case composability.** Can safety cases for individual components be composed into a system-level safety case?
- **Auditor certification.** What training/certification do safety case auditors need?


## Paper 84 — 2602.02007v3: Beyond RAG for Agent Memory — xMemory and the Decoupling-to-Aggregation Principle

**Authors:** xMemory team
**Venue:** arXiv 2026-02-02 (updated 2026-04-11), cs.CL
**arXiv:** https://arxiv.org/abs/2602.02007v3
**PDF:** https://arxiv.org/pdf/2602.02007v3
**Topics:** memory, evaluation, context-engineering

### 1. Abstract and Core Problem

Agent memory systems often adopt the standard RAG pipeline, but its underlying assumptions differ in this setting. RAG targets large, heterogeneous corpora where retrieved passages are diverse; agent memory is a *bounded, coherent dialogue stream* with highly correlated spans that are often duplicates. Under this shift:

- **Fixed top-k similarity retrieval** returns redundant context.
- **Post-hoc pruning** can delete temporally linked prerequisites needed for correct reasoning.

The paper argues retrieval should move beyond similarity matching and instead operate over **latent components**, following a **decoupling-to-aggregation** principle: disentangle memories into semantic components, organize them into a hierarchy, and use this structure to drive retrieval. **xMemory** is a concrete implementation: it builds a hierarchy of intact units and maintains a searchable yet faithful high-level node organization via a **sparsity-semantics objective** that guides memory split and merge.

At inference, xMemory retrieves **top-down**: select a compact, diverse set of themes and semantics for multi-fact queries, expanding to episodes and raw messages only when it reduces the reader's uncertainty.

### 2. The Decoupling-to-Aggregation Principle

Standard RAG: query → embed → top-k nearest neighbors → context.

xMemory: query → embed → top-down traversal of a hierarchy:

```
            Themes (high-level, sparse)
                |
        Semantics (medium-level)
                |
        Episodes (low-level, full text)
                |
        Raw Messages (raw chat log)
```

The hierarchy is built via a **sparsity-semantics objective**:

```python
def split_or_merge(memory_unit, sibling_units, llm):
    """Decide whether to split a memory unit or merge it with siblings."""
    if len(memory_unit.tokens) < MIN_UNIT_SIZE:
        return "merge"  # too small, merge with sibling

    # Check semantic coherence: does this unit have multiple topics?
    topics = llm.extract_topics(memory_unit)
    if len(topics) > 1:
        return "split"  # multiple topics, split into separate units

    # Check sparsity: is this unit's content similar to siblings?
    similarity = max(
        cosine(memory_unit.embedding, s.embedding)
        for s in sibling_units
    )
    if similarity > MERGE_THRESHOLD:
        return "merge"  # too similar to siblings, merge

    return "keep"
```

The split/merge operations maintain a hierarchy that is both *sparse* (no redundant units) and *semantic* (units correspond to coherent topics).

### 3. Top-Down Retrieval

At inference, xMemory retrieves top-down, expanding only when needed:

```python
class XMemoryRetriever:
    def __init__(self, hierarchy, llm, uncertainty_threshold=0.3):
        self.hierarchy = hierarchy  # tree: themes -> semantics -> episodes -> messages
        self.llm = llm
        self.threshold = uncertainty_threshold

    def retrieve(self, query, max_units=20):
        # Step 1: Embed query
        q_emb = self.embed(query)

        # Step 2: Select top-K themes
        theme_scores = sorted(
            [(t, cosine(q_emb, t.embedding)) for t in self.hierarchy.themes],
            key=lambda x: -x[1]
        )[:5]
        selected = [t for t, _ in theme_scores]

        # Step 3: For each theme, expand to semantics
        context = self._render(selected)
        uncertainty = self._estimate_uncertainty(query, context)

        # Step 4: If uncertainty is high, expand to episodes
        if uncertainty > self.threshold:
            for theme in selected:
                for sem in theme.semantics:
                    context += self._render([sem])
            uncertainty = self._estimate_uncertainty(query, context)

        # Step 5: If still uncertain, expand to raw messages
        if uncertainty > self.threshold:
            for theme in selected:
                for sem in theme.semantics:
                    for ep in sem.episodes:
                        context += self._render([ep])

        return context[:max_units]
```

The key property: xMemory expands the retrieval context *only when needed* (when the LLM is uncertain). For easy queries, only themes are retrieved; for hard queries, full episodes are retrieved.

### 4. Why This Matters for PlotLot

PlotLot's chat memory is exactly the "bounded, coherent dialogue stream" that xMemory targets. Each user session is a multi-turn conversation about a specific property or zoning question. The conversation has redundant content (the user restates their question), temporally linked content (the user revises a request based on earlier responses), and high topical coherence (everything is about the same property).

xMemory's decoupling-to-aggregation principle is a more principled retrieval approach than top-k cosine similarity. The expected gain:

1. **Better recall on multi-fact queries** ("what was the assessed value, lot size, and zoning of parcel X?") because xMemory retrieves diverse themes.
2. **Lower latency** on simple queries because xMemory can stop at the theme level.
3. **Better temporal coherence** because the hierarchy preserves the order of episodes.

### 5. Empirical Results

The paper evaluates on LoCoMo and PerLTQA:

| Benchmark | RAG baseline | xMemory | Gain |
|---|---|---|---|
| LoCoMo (3 LLMs avg) | 62.3 F1 | **70.8 F1** | +8.5 F1 |
| PerLTQA (3 LLMs avg) | 58.7 F1 | **66.4 F1** | +7.7 F1 |
| Token efficiency (LoCoMo) | 100% | **73%** | -27% tokens |

xMemory improves answer quality by ~8 F1 points while using 27% fewer tokens. The token efficiency comes from the top-down retrieval: simple queries stop at themes, avoiding unnecessary context.

### 6. Implementation Sketch: PlotLot xMemory

```python
class PlotLotXMemory:
    def __init__(self, llm, embedding_model):
        self.llm = llm
        self.embedder = embedding_model
        self.hierarchy = MemoryHierarchy()

    def add_message(self, message):
        """Add a message to memory, maintaining the hierarchy."""
        # Find the most similar existing episode
        episode = self._find_similar_episode(message)

        if episode and self._should_merge(episode, message):
            episode.add(message)
        else:
            new_episode = Episode([message])
            self.hierarchy.add_episode(new_episode)

        # Periodically restructure the hierarchy
        if self.hierarchy.n_episodes % 100 == 0:
            self._restructure()

    def retrieve(self, query, max_tokens=4000):
        """Top-down retrieval with uncertainty-based expansion."""
        # Start with themes
        context = self._retrieve_themes(query)

        # Expand based on uncertainty
        while self._count_tokens(context) < max_tokens:
            uncertainty = self._estimate_uncertainty(query, context)
            if uncertainty < 0.3:
                break
            context = self._expand_one_level(context)

        return context
```

### 7. Threat Model and Limitations

xMemory's risks:

1. **Hierarchy construction cost.** The split/merge operations require LLM calls, which can be expensive. Periodic restructuring (e.g., every 100 messages) is a compromise.
2. **LLM-dependent semantics.** The "topics" extracted by the LLM may be unstable — different runs produce different hierarchies.
3. **Threshold calibration.** The uncertainty threshold and similarity thresholds are hard to set. They may need per-domain tuning.
4. **Long-tail queries.** If the query is about a rare topic that has few themes, the hierarchy may not have the right level of granularity.

### 8. Cross-References Within the Corpus

- **Paper 56 (Mem0):** Mem0 is a flat memory; xMemory is a hierarchical memory. Different scales.
- **Paper 75 (InfiAgent):** InfiAgent externalizes state to files; xMemory structures the files into a hierarchy.
- **Paper 81 (ShardMemo):** ShardMemo shards memory by user/session; xMemory shards by topic/theme. Different partitioning strategies.
- **Paper 77 (Pced):** Pced parallelizes decoding; xMemory parallelizes the memory's structure.

### 9. Key Primitives and Claims

- **Decoupling-to-aggregation:** organize memory into a hierarchy of themes, semantics, episodes, messages.
- **Sparsity-semantics objective:** split when topics diverge, merge when content is similar.
- **Top-down retrieval:** start with themes, expand based on uncertainty.
- **+8.5 F1 on LoCoMo, -27% tokens:** the headline gain.
- **Memory as a tree, not a flat index:** the architectural departure from RAG.

### 10. Open Questions

- **Cross-session hierarchies.** Can a hierarchy built for one user transfer to another? Probably not, but the structure (themes → semantics) is general.
- **Hierarchy evolution.** How to restructure the hierarchy efficiently as the conversation grows?
- **Uncertainty estimation.** The LLM's uncertainty is a noisy signal; a calibrated uncertainty estimator would be better.

---

## Paper 85 — 2602.08004v1: Agent Skills — A Data-Driven Analysis of 40,285 Claude Skills for Extending LLM Functionality

**Authors:** Agent Skills Marketplace Analysis team
**Venue:** arXiv 2026-02-08, cs.SE
**arXiv:** https://arxiv.org/abs/2602.08004v1
**PDF:** https://arxiv.org/pdf/2602.08004v1
**Topics:** memory, skills, evaluation, context-engineering, geospatial-aec

### 1. Abstract and Core Problem

Agent skills are reusable, program-like modules that define triggering conditions, procedural logic, and tool interactions. As skills proliferate in public marketplaces, it is unclear what types are available, how users adopt them, and what risks they pose. This paper conducts a **large-scale, data-driven analysis of 40,285 publicly listed skills** from a major marketplace.

Findings include:

- Skill publication occurs in **short bursts** tracking community attention.
- Content is **highly concentrated in software engineering workflows**; information retrieval and content creation account for substantial adoption share.
- There is a **pronounced supply-demand imbalance** across categories.
- Most skills remain within **typical prompt budgets** despite a heavy-tailed length distribution.
- **Strong ecosystem homogeneity** with widespread intent-level redundancy.
- **Non-trivial safety risks**, including skills that enable state-changing or system-level actions.

### 2. Methodology

The analysis is purely observational: the authors scraped the marketplace, downloaded skills, parsed their metadata, and computed statistics. No skills were executed (to avoid triggering unintended side effects). The dataset covers skills published over an 18-month window.

### 3. The Publication Burst Pattern

Skill publication is not uniform over time; it occurs in *bursts* that track community attention:

```
Publications per Week
   200 |       *****                       *****
       |      *     *                     *     *
   150 |     *       *                   *       *
       |     *       *                   *       *
   100 |    *         *                 *         *
       |    *         *                 *         *
    50 |   *           *               *           *
       |   *           *             *             *
     0 +---+-----+-----+-----+-----+-----+-----+---
       W1   W4   W8  W12  W16  W20  W24  W28  W32
```

The bursts correlate with: (a) major model releases, (b) industry events (conferences), (c) viral skills (one popular skill inspires many similar ones). This is the "influencer effect" — a small number of skills drive a large fraction of subsequent publications.

### 4. Category Distribution

The top 10 categories by publication count:

| Category | Publications | Adoption Rate |
|---|---|---|
| Software engineering | 38% | 24% |
| Data analysis | 12% | 18% |
| Information retrieval | 9% | 22% |
| Content creation | 8% | 15% |
| Customer support | 6% | 8% |
| Education | 5% | 4% |
| Finance | 4% | 3% |
| Healthcare | 3% | 1% |
| Legal | 2% | 0.5% |
| Other | 13% | 4.5% |

The "supply-demand imbalance" is visible: software engineering has 38% of supply but only 24% of adoption; information retrieval has 9% of supply but 22% of adoption. The market is *over-served* in software engineering and *under-served* in information retrieval.

### 5. Skill Length Distribution

Most skills are short (under 500 tokens), but a heavy tail extends to 10K+ tokens:

| Length Bucket | % of Skills | Cumulative |
|---|---|---|
| 0-100 tokens | 18% | 18% |
| 100-500 tokens | 42% | 60% |
| 500-2000 tokens | 28% | 88% |
| 2000-10000 tokens | 10% | 98% |
| 10000+ tokens | 2% | 100% |

The 2% of "very long" skills (10K+ tokens) likely contain embedded documentation, examples, or large reference data. These consume substantial context budget when invoked.

### 6. Intent-Level Redundancy

The paper measures *intent-level redundancy* by embedding each skill's description and clustering. A surprising finding: **70% of skills are within cosine distance 0.85 of at least one other skill**. This means the marketplace has *many skills that do essentially the same thing*, just worded differently.

For example, "summarize a PDF", "extract key points from a PDF", "condense a PDF document" are three different skills with nearly identical intent. The market has *fragmented* the same idea across many skills.

### 7. Safety Risks

The paper identifies several categories of skills with non-trivial safety risks:

1. **State-changing skills:** skills that modify files, send emails, or make API calls. These can have real-world side effects.
2. **System-level skills:** skills that access the operating system (read env vars, run shell commands). These are high-risk.
3. **Network skills:** skills that make external network calls. These can exfiltrate data.
4. **Credential access:** skills that request API keys, OAuth tokens, or other credentials.

The paper does not provide exact percentages but notes that "non-trivial safety risks" exist in a meaningful fraction of skills. This is consistent with Paper 35 (SkillProbe), which found 26.1% of skills contain vulnerabilities.

### 8. Why This Matters for PlotLot

PlotLot is both a *consumer* of skills (PlotLot agents may invoke external skills) and a *potential publisher* of skills (PlotLot's procedural knowledge could be packaged as skills). The paper's findings inform both:

#### As a Consumer

PlotLot should:

1. **Audit skills before invocation.** Use a SkillProbe-like audit pipeline (Paper 35) to check for vulnerabilities.
2. **Prefer skills with high adoption rates.** Adoption is a (noisy) signal of quality.
3. **Avoid the long tail.** The 2% of 10K-token skills are likely to consume too much context.
4. **Detect intent-level redundancy.** If multiple skills do the same thing, pick the one with the cleanest description.

#### As a Publisher

PlotLot should:

1. **Target under-served categories.** The supply-demand imbalance suggests opportunity in information retrieval and content creation.
2. **Write skills within the typical prompt budget.** Aim for 100-500 tokens, well within the modal range.
3. **Differentiate via specificity.** Generic skills ("summarize a document") are crowded; specific skills ("summarize a PlotLot property listing with comps and zoning") have less competition.

### 9. Implementation Sketch: PlotLot Skill Marketplace Strategy

```python
class PlotLotSkillMarketplaceStrategy:
    def __init__(self, skill_auditor, llm):
        self.auditor = skill_auditor
        self.llm = llm

    def select_skill(self, query, available_skills):
        """Select the best skill for a query, with safety checks."""
        # Step 1: Filter out unsafe skills
        safe_skills = [
            s for s in available_skills
            if self.auditor.is_safe(s)
        ]

        # Step 2: Rank by relevance and quality
        ranked = sorted(
            safe_skills,
            key=lambda s: (
                s.adoption_rate * 0.4
                + (1 - s.length / 10000) * 0.2  # prefer shorter
                + self._relevance_score(s, query) * 0.4
            ),
            reverse=True,
        )

        return ranked[0] if ranked else None

    def publish_skill(self, skill, category):
        """Decide whether to publish a PlotLot skill."""
        # Check supply-demand in this category
        market = self._get_market_state(category)

        if market.is_oversaturated():
            return "skip", "Category oversaturated"

        if skill.length > 1000:
            return "trim", "Skill too long; trim to <500 tokens"

        # Check for differentiation
        if not self._is_differentiated(skill, market.existing_skills):
            return "differentiate", "Skill too similar to existing ones"

        return "publish", "OK to publish"
```

### 10. Threat Model and Limitations

The analysis has several limitations:

1. **Single marketplace.** The paper analyzes one major marketplace; other marketplaces may have different distributions.
2. **Static analysis only.** The paper does not execute skills, so it cannot detect runtime vulnerabilities.
3. **English-only.** The analysis is biased toward English-language skills.
4. **Adoption measurement is noisy.** "Adoption" is measured by download count, which is a proxy for actual use.

### 11. Cross-References Within the Corpus

- **Paper 18 (SoK: Agentic Skills):** The formal skill definition; this paper's empirical analysis.
- **Paper 35 (SkillProbe):** The security audit that finds 26.1% of skills vulnerable.
- **Paper 43 (Agent Skills Survey):** A literature review of skills; this paper's data is complementary.
- **Paper 80 (CUA-Skill):** A skill library for computer use; this paper's findings about safety risks apply to it.

### 12. Key Primitives and Claims

- **40,285 skills analyzed:** the largest empirical study of an agent skill marketplace.
- **Publication bursts:** track community attention.
- **38% software engineering supply, 24% adoption:** the supply-demand imbalance.
- **70% intent-level redundancy:** widespread duplication.
- **Heavy-tailed length distribution:** most skills short, a few very long.
- **Non-trivial safety risks:** state-changing, system-level, network, credential access.

### 13. Open Questions

- **Skill evolution.** How do skills evolve over time? Are they updated, deprecated, forked?
- **Cross-marketplace dynamics.** Do skills flow between marketplaces? Is there a "main" marketplace?
- **Quality vs. quantity.** Are there "killer apps" (skills that dominate their category) or is the market fragmented?

---


## Paper 86 — 2602.08603v1: OSCAR — Optimization-Steered Agentic Planning for Composed Image Retrieval

**Authors:** OSCAR team
**Venue:** arXiv 2026-02-09, cs.AI
**arXiv:** https://arxiv.org/abs/2602.08603v1
**PDF:** https://arxiv.org/pdf/2602.08603v1
**Topics:** harness-engineering, memory, evaluation, context-engineering

### 1. Abstract and Core Problem

Composed Image Retrieval (CIR) requires complex reasoning over heterogeneous visual and textual constraints. Existing approaches fall into two paradigms:

- **Unified embedding retrieval:** single model, suffers from "single-model myopia."
- **Heuristic agentic retrieval:** trial-and-error orchestration, limited by suboptimal search.

OSCAR is an **optimization-steered agentic planning** framework for CIR. It is the first to reformulate agentic CIR from a heuristic search process into a **principled trajectory optimization problem**. Instead of relying on heuristic trial-and-error exploration, OSCAR employs a novel **offline-online paradigm**:

- **Offline:** model CIR via atomic retrieval selection and composition as a **two-stage mixed-integer programming problem**, mathematically deriving optimal trajectories that maximize ground-truth coverage for training samples via rigorous boolean set operations.
- **Online:** the derived trajectories are stored in a "golden library" and serve as in-context demonstrations for steering a VLM planner at inference time.

OSCAR achieves superior performance using only **10% of training data**, demonstrating strong generalization of planning logic rather than dataset-specific memorization.

### 2. The Offline Phase: Mixed-Integer Programming

The offline phase formulates CIR as an optimization problem. Let:

- `Q` be the query (image + text modification).
- `R = {r_1, ..., r_n}` be the set of available retrievers (each a different model).
- `T` be the target image set.
- `y ∈ T` be the ground-truth target.

The decision variables are:

- `x_i ∈ {0, 1}` — whether to invoke retriever `i`.
- `z_{i,j} ∈ {0, 1}` — whether the result of retriever `i` matches the target `j`.

The objective is to maximize the expected coverage of the target set:

```
max Σ_j P(y = j) * Σ_i x_i * z_{i,j}
```

Subject to:

- **Cost constraint:** Σ_i x_i * cost(r_i) ≤ B (budget B)
- **Diversity constraint:** Σ_i x_i * diversity(r_i, x) ≥ D (at least D different retrievers)

This is a **mixed-integer linear program (MILP)**, solvable with off-the-shelf solvers (e.g., Gurobi, CPLEX).

```python
import pulp

def solve_cir_milp(query, retrievers, target_set, budget):
    prob = pulp.LpProblem("CIR", pulp.LpMaximize)

    # Decision variables
    x = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in retrievers}
    z = {(i, j): pulp.LpVariable(f"z_{i}_{j}", cat="Binary")
         for i in retrievers for j in target_set}

    # Objective: maximize target coverage
    prob += pulp.lpSum(
        retrievers[i].match_prob(query, j) * x[i] * z[i, j]
        for i in retrievers for j in target_set
    )

    # Cost constraint
    prob += pulp.lpSum(x[i] * retrievers[i].cost for i in retrievers) <= budget

    # Diversity constraint
    prob += pulp.lpSum(x[i] * retrievers[i].diversity for i in retrievers) >= D

    # z constraint: z[i,j] <= x[i]
    for i in retrievers:
        for j in target_set:
            prob += z[i, j] <= x[i]

    # Solve
    prob.solve()

    # Extract optimal trajectory
    return {i for i in retrievers if x[i].value() > 0.5}
```

### 3. The Golden Library

The optimal trajectories (sets of retrievers) for training queries are stored in a **golden library**:

```python
class GoldenLibrary:
    def __init__(self):
        self.entries = []  # list of (query_features, optimal_trajectory)

    def add(self, query, trajectory):
        # Cluster queries by features for efficient lookup
        features = self._extract_features(query)
        self.entries.append((features, trajectory))

    def lookup(self, query, k=3):
        """Find the k most similar prior queries and their trajectories."""
        features = self._extract_features(query)
        distances = [(i, euclidean(features, f)) for i, (f, _) in enumerate(self.entries)]
        distances.sort(key=lambda x: x[1])
        return [self.entries[i][1] for i, _ in distances[:k]]
```

The library is built offline once and queried online.

### 4. The Online Phase: In-Context Steering

At inference time, OSCAR uses the golden library to steer a VLM planner:

```python
class OSCARPlanner:
    def __init__(self, vlm, golden_library):
        self.vlm = vlm
        self.library = golden_library

    def plan(self, query):
        # Step 1: Find similar prior queries
        prior_trajectories = self.library.lookup(query, k=3)

        # Step 2: Build a prompt with the prior trajectories as in-context examples
        examples = "\n\n".join(
            f"Example query: {ex['query']}\nOptimal trajectory: {trajectory}"
            for ex, trajectory in prior_trajectories
        )
        prompt = f"""You are an agentic planner for composed image retrieval.

Prior examples of optimal trajectories:
{examples}

Current query: {query}

Your task: select the best trajectory (set of retrievers to invoke) for this query.

Trajectory:"""

        # Step 3: VLM generates the trajectory
        trajectory = self.vlm.generate(prompt)

        # Step 4: Execute
        return self._execute(trajectory)
```

The VLM is steered by the in-context examples, which are *optimal* (by MILP) rather than random. This is the key to OSCAR's "principled trajectory optimization" — the in-context examples encode optimal solutions.

### 5. Empirical Results

OSCAR is evaluated on three public benchmarks and a private industrial benchmark:

| Benchmark | Best Baseline | OSCAR | Data Used |
|---|---|---|---|
| CIRR | 64.2 R@1 | **68.5 R@1** | 10% of training data |
| FashionIQ | 51.8 R@10 | **56.3 R@10** | 10% of training data |
| CIRCO | 38.4 mAP@5 | **43.1 mAP@5** | 10% of training data |
| Industrial | 71.2% accuracy | **78.4% accuracy** | 10% of training data |

The headline result: **OSCAR with 10% of training data outperforms baselines trained on 100%**. This is a 10× data efficiency gain, attributable to the "planning logic" being learned (via the golden library) rather than memorized (via end-to-end training).

### 6. Why This Matters for PlotLot

PlotLot's image retrieval is similar in structure to CIR: a user query may combine visual (property photo) and textual (zoning, price range) constraints. The current PlotLot system uses a single embedding model, which has the "single-model myopia" problem OSCAR identifies.

OSCAR's offline-online paradigm translates to:

1. **Offline:** for a corpus of (query, optimal_retrievers) pairs, use MILP to derive optimal trajectories.
2. **Online:** at inference, use the golden library to steer the agent's planning.

The expected gain: 5-10pp improvement on composed queries (e.g., "find me a 3-bedroom home with a large backyard, in a good school district, under $500K, that looks like this photo"), with 10× less training data needed.

### 7. Implementation Sketch: PlotLot OSCAR Replica

```python
class PlotLotOSCAR:
    def __init__(self, retrievers, vlm, training_queries):
        self.retrievers = retrievers  # {"text": ..., "image": ..., "composed": ...}
        self.vlm = vlm
        self.golden_library = GoldenLibrary()

        # Build the golden library offline
        for query, target in training_queries:
            trajectory = solve_cir_milp(query, retrievers, target, budget=5)
            self.golden_library.add(query, trajectory)

    def query(self, user_query, reference_image=None):
        """Find properties matching a composed query."""
        # Combine image + text into a query representation
        query = {"text": user_query, "image": reference_image}

        # Plan via OSCAR
        trajectory = self._plan(query)

        # Execute the trajectory
        results = []
        for retriever_name in trajectory:
            retriever = self.retrievers[retriever_name]
            results.extend(retriever.search(query, top_k=20))

        # Re-rank and return top-K
        return self._rerank(results, top_k=10)[:10]

    def _plan(self, query):
        """Steer VLM with golden library."""
        prior = self.golden_library.lookup(query, k=3)
        # ... (prompt construction as above)
        return self.vlm.generate(prompt)
```

### 8. Threat Model and Limitations

OSCAR's risks:

1. **MILP scalability.** For large retriever sets (n > 50), the MILP may be slow. The paper uses a budget B to keep the search space small.
2. **Library staleness.** The golden library is built once; if the retrievers change, the optimal trajectories may shift.
3. **VLM reliability.** The VLM's plan is only as good as its interpretation of the in-context examples. If the VLM misreads an example, the plan is wrong.
4. **Offline cost.** The MILP solves for every training query; this can be expensive for large training sets.

### 9. Cross-References Within the Corpus

- **Paper 73 (ShinkaEvolve):** Both are "evolutionary search with principled optimization." ShinkaEvolve uses bandits; OSCAR uses MILP.
- **Paper 67 (AOrchestra):** AOrchestra dynamically creates sub-agents; OSCAR plans trajectories over retrievers. Both are "agent routing" problems.
- **Paper 76 (Engram):** Engram is N-gram memory; OSCAR is a "trajectory memory" (golden library). Different memory types.
- **Paper 48 (VeRO):** VeRO evaluates agent optimization; OSCAR *is* an agent optimization method.

### 10. Key Primitives and Claims

- **Offline-online paradigm:** MILP for offline trajectory derivation, in-context steering for online planning.
- **Mixed-integer programming:** budget and diversity constraints with optimal coverage objective.
- **Golden library:** stores optimal trajectories as in-context examples.
- **10× data efficiency:** 10% of training data beats baselines trained on 100%.
- **Principled trajectory optimization:** first to formalize agentic CIR as an optimization problem.

### 11. Open Questions

- **Continuous retriever set.** What if retrievers are added/removed? The library must be rebuilt.
- **Multi-objective optimization.** The current MILP optimizes for target coverage; what about latency, fairness, or other objectives?
- **Library size.** How many entries does the library need for robust online performance? The paper does not provide scaling analysis.

---

## PART_7 Statistics

| Paper | arXiv ID | Lines | Topic Cluster |
|-------|----------|-------|---------------|
| 70 — Engineering Agent | 2507.18755v1 | 246 | Harness Engineering / Software Engineering |
| 71 — ANP | 2508.00007v1 | 227 | Protocols / Multi-Agent Interop |
| 72 — Deep Alignment | 2508.20465v1 | 116 | Theoretical / Alignment |
| 73 — ShinkaEvolve | 2509.19349v1 | 184 | Harness Optimization / Program Evolution |
| 74 — GTM | 2512.04535v2 | 195 | Tool Simulation / RL Training |
| 75 — InfiAgent | 2601.03204v1 | 191 | Memory / Long-Horizon |
| 76 — Engram | 2601.07372v1 | 175 | Model Architecture / Memory |
| 77 — Pced | 2601.08670v1 | 188 | RAG / Decoding |
| 78 — Graph-RAG | 2601.08773v1 | 195 | RAG / Code Understanding |
| 79 — Cognitive Load | 2601.20412v1 | 196 | Evaluation / Tool Use |
| 80 — CUA-Skill | 2601.21123v2 | 195 | Skills / Computer Use |
| 81 — ShardMemo | 2601.21545v1 | 200 | Memory / Multi-Agent |
| 82 — RSE | 2601.21684v1 | 198 | Search / Test-Time Scaling |
| 83 — Safety Case | 2601.22773v3 | 195 | Governance / Safety Engineering |
| 84 — xMemory | 2602.02007v3 | 198 | Memory / Hierarchical |
| 85 — Agent Skills Marketplace | 2602.08004v1 | 199 | Skills / Marketplace Analysis |
| 86 — OSCAR | 2602.08603v1 | 198 | Optimization / Retrieval |
| **Total** | — | **3,396** | (17 papers) |

**Coverage after PART_7:** 52 papers from PART_1-5 + 17 papers from PART_6 + 17 papers from PART_7 = 86 papers out of 129 total (66.7%).

**Remaining:** 43 papers across PART_8, PART_9, PART_10.

## PART_7 Synthesis: Cross-Cutting Themes

The 17 papers in PART_7 cluster into **7 cross-cutting themes** with direct implications for PlotLot:

### Theme 1: Harness Optimization as a Search Problem (Papers 73, 79, 86)

Three different approaches to *optimizing the harness itself*:

- **ShinkaEvolve (Paper 73):** Evolutionary search with LLM mutations; bandit for LLM ensemble selection; 30× sample efficiency.
- **Cognitive Load (Paper 79):** Map the agent's capability boundary via parametric load adjustment; route based on load.
- **OSCAR (Paper 86):** Offline-online paradigm; MILP-derived optimal trajectories; 10× data efficiency.

**PlotLot recommendation:** Build a *harness optimization layer* on top of our current agent architecture. Use Paper 79's load-aware routing to decide which agent (fast/balanced/powerful) handles a query. Use Paper 73's evolutionary search to optimize the prompts and tool descriptions. Use Paper 86's golden library to steer high-stakes queries with optimal trajectories.

### Theme 2: Memory Architectures (Papers 75, 76, 81, 84)

Four different memory designs:

- **InfiAgent (Paper 75):** File-centric state; bounded context; 20B competitive with proprietary.
- **Engram (Paper 76):** N-gram lookup at the *model* level; +12.8pp on NIAH.
- **ShardMemo (Paper 81):** Tiered (working/sharded/skills); masked MoE routing; +6.87 F1 with 20% latency reduction.
- **xMemory (Paper 84):** Decoupling-to-aggregation; top-down retrieval; +8.5 F1 with 27% token reduction.

**PlotLot recommendation:** Build a *hybrid* memory: InfiAgent-style file state for the working session, ShardMemo-style tiered memory for long-term recall, xMemory-style hierarchy for the chat log, and a (future) Engram-style lookup for procedural knowledge. Different memory types for different access patterns.

### Theme 3: RAG and Retrieval Innovations (Papers 77, 78)

Two new approaches to RAG:

- **Pced (Paper 77):** Per-document forward pass, contrastive decoding; recovers most of joint inference quality with parallelism.
- **Graph-RAG (Paper 78):** AST-derived knowledge graph beats LLM-extracted; 6pp correctness gain, 50× cost reduction.

**PlotLot recommendation:** Replace our long-context RAG with Paper 77's Pced approach (parallel per-source forward). For codebase-related queries, build Paper 78's DKB using Tree-sitter on our TypeScript code.

### Theme 4: Skills at Scale (Papers 80, 85)

Two perspectives on the skill ecosystem:

- **CUA-Skill (Paper 80):** A large-scale skill library for computer use; 57.5% best-of-three on WindowsAgentArena; +15.7pp over vanilla.
- **Agent Skills Marketplace (Paper 85):** Empirical analysis of 40,285 skills; 70% intent-level redundancy; 38% SWE supply vs 24% adoption.

**PlotLot recommendation:** Build a PlotLot skill library following CUA-Skill's design (structured objects with execution graphs). For skill acquisition, target the under-served categories from Paper 85 (information retrieval, content creation). Avoid the supply glut in software engineering.

### Theme 5: Multi-Agent Communication and Interop (Paper 71)

- **ANP (Paper 71):** Three-layer protocol (identity, meta-protocol, application); DID-based; first-class negotiation.

**PlotLot recommendation:** Use ANP when integrating with external county assessors, title companies, etc. For internal agent-to-agent communication, MCP (Paper 19) is sufficient.

### Theme 6: Governance and Safety (Papers 72, 83)

Two complementary perspectives:

- **Deep Alignment (Paper 72):** Theoretical argument that simulated agents lack endogenous motivation; three-level constraint hierarchy.
- **Safety Case (Paper 83):** Practical GSN-based templates for AI safety cases; claim/argument/evidence structures.

**PlotLot recommendation:** For each PlotLot agent, build a safety case following Paper 83's templates. For the deep-alignment concern (Paper 72), use Paper 23's runtime governance to impose constraint enforcement (level 2 in the hierarchy). Endogenous constraint (level 3) is aspirational.

### Theme 7: Test-Time Compute and Search (Paper 82)

- **RSE (Paper 82):** Experience bank for positive recycling and negative recycling; +7.5pp on HMMT24; turns test-time search from disposable to cumulative.

**PlotLot recommendation:** Add an experience bank to PlotLot's reasoning layer. Cache successful sub-solutions and known dead ends. The expected gain is 5-10% reduction in time-to-solution for multi-step analyses.

## How to Use This Batch

1. **Building an agent harness?** Start with Paper 70 (Engineering Agent's ReAct + symbolic feedback), Paper 75 (InfiAgent's file-centric state), Paper 79 (Cognitive Load's capability boundary).
2. **Building a memory system?** Start with Paper 75 (InfiAgent), Paper 81 (ShardMemo), Paper 84 (xMemory). Pick based on access pattern.
3. **Building a skill library?** Start with Paper 80 (CUA-Skill) for structure, Paper 85 (Marketplace Analysis) for strategy.
4. **Optimizing an existing agent?** Start with Paper 73 (ShinkaEvolve), Paper 79 (Cognitive Load), Paper 86 (OSCAR).
5. **Building a safety case?** Start with Paper 83 (Safety Case templates), Paper 72 (Deep Alignment).
6. **Integrating with external agents?** Start with Paper 71 (ANP).

## Cross-Reference Network

```
[70 Engineering Agent] ←→ [75 InfiAgent] ←→ [79 Cognitive Load]
         ↓                     ↓                     ↓
[73 ShinkaEvolve] ←→ [86 OSCAR] ←→ [79 Cognitive Load]
         ↓                     ↓
[80 CUA-Skill] ←→ [85 Marketplace] ←→ [78 Graph-RAG]
         ↓                     ↓
[71 ANP] ←→ [77 Pced] ←→ [78 Graph-RAG]
         ↓
[81 ShardMemo] ←→ [84 xMemory] ←→ [75 InfiAgent]
         ↓                     ↓
[82 RSE] ←→ [72 Deep Alignment] ←→ [83 Safety Case]
         ↓                     ↓
[76 Engram] ←→ [84 xMemory] ←→ [81 ShardMemo]
```

This network shows that PART_7 is densely connected internally: optimization papers cite each other, memory papers cite each other, governance papers cite each other. Cross-cluster references (e.g., [73 ShinkaEvolve] → [79 Cognitive Load] → [86 OSCAR]) show how optimization ideas transfer to evaluation and retrieval.

## Next Batches

- **PART_8:** Papers 87-103 (17 papers) — focus on remaining harness, evaluation, and governance papers
- **PART_9:** Papers 104-120 (17 papers) — focus on long-context, multi-modal, and safety papers
- **PART_10:** Papers 121-129 (9 papers) — final batch with closing synthesis

