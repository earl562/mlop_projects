---

# PAPER 18: 2602.20867 - SoK: Agentic Skills: Beyond Tool Use in LLM Agents

**Authors:** Yanna Jiang et al.  
**Date:** 24 Feb 2026 | cs.CR | 4,989 KB

## TECHNICAL BREAKDOWN

### Core Contributions
This Systematization of Knowledge (SoK) provides six key contributions:
1. Unified definition of agentic skills as S=(C,π,T,R) where:
   - C: Applicability condition (observation × goal → {0,1})
   - π: Executable policy (observation × history → actions/skill invocations)
   - T: Termination condition (observation × history × goal → {0,1})
   - R: Reusable callable interface (name, params, returns)
2. Skill lifecycle model covering discovery through evaluation/update
3. Seven-pattern design taxonomy for skill packaging/execution
4. Orthogonal representation × scope taxonomy
5. Security and governance analysis including ClawHavoc case study
6. Evaluation framework with metrics and benchmark mapping

### Skill Lifecycle Model
The lifecycle comprises seven stages:
1. **Discovery**: Identifying recurring task patterns/workflow bottlenecks
2. **Practice/Refinement**: Iterative improvement through trial-and-error
3. **Distillation**: Extracting essential behavior from varied interactions
4. **Storage**: Persisting skills with metadata for retrieval
5. **Retrieval**: Selecting relevant skills for current context
6. **Execution**: Running skills with monitoring and adaptation
7. **Update**: Evolving skills based on performance feedback

### Seven Design Patterns
| Pattern | Description | Key Characteristics |
|---------|-------------|-------------------|
| **1. Metadata-Driven Disclosure** | Progressive skill disclosure based on context | Declarative metadata, context-sensitive loading |
| **2. Code-as-Skill** | Executable scripts as skills | Direct execution, versionable, auditable |
| **3. Workflow Enforcement** | Structured execution with validation | Pre/post conditions, state verification |
| **4. Self-Evolving Skill Libraries** | Libraries that improve over time | Performance-based ranking, automated pruning |
| **5. Hybrid NL+Code Macros** | Natural language templates with code slots | Human-readable, parameterizable, executable |
| **6. Meta-Skills** | Skills that manage other skills | Skill selection, composition, adaptation |
| **7. Plugin/Marketplace Distribution** | Skills distributed via registries | Versioning, dependency management, provenance |

### Representation × Scope Taxonomy
**Representation Axis** (what skills *are*):
- Natural Language: Playbooks, instructions, templates
- Code: Executable scripts, functions, methods
- Policy: Rule-based systems, decision trees
- Hybrid: Combinations of above representations

**Scope Axis** (what environments they operate over):
- Web: Browser automation, web APIs
- OS: File systems, processes, shells
- Software Engineering: IDEs, compilers, version control
- Robotics: Motor control, sensor processing, navigation

### Skill Composition and Orchestration
Skills can be composed hierarchically:
- **Hierarchical Skill Structures**: Skills calling other skills (option-subroutine pattern)
- **DAG Structures**: Skills with dependency graphs for parallel execution
- **Recursive Structures**: Skills that invoke themselves with different parameters

### Security, Trust, and Governance
**Threat Model**:
1. Context Injection: Adversarial context manipulation
2. Decision Manipulation: Forced incorrect reasoning
3. Tool Hijacking: Unauthorized tool use
4. State Corruption: Malicious state modification
5. Privilege Escalation: Unauthorized capability access
6. Data Exfiltration: Sensitive data leakage

**Trust Tiers and Progressive Disclosure**:
- Skills tagged with trust levels (low/medium/high)
- Progressive disclosure of capabilities based on trust
- Sandboxing and permission boundaries per trust tier

**Case Study: ClawHavoc Supply-Chain Attack**:
- ~1,200 malicious skills infiltrated major agent marketplace
- Exfiltrated API keys, cryptocurrency wallets, browser credentials
- Demonstrates critical need for skill supply-chain governance

### Evaluation Framework
**Evaluation Dimensions**:
- Correctness: Outcome accuracy, safety compliance
- Efficiency: Execution time, resource consumption
- Adaptability: Performance across environment variations
- Composability: Skill chaining effectiveness
- Governance: Auditability, provenance tracking

**Deterministic Evaluation Harnesses**:
- Fixed input/output pairs for skill validation
- Regression testing against known good/bad cases
- Property-based testing for invariant validation

**Anchor Case Study: SkillsBench**:
- Curated skills raise agent pass rates by 16.2 percentage points
- Self-generated skills degrade performance by 1.3 pp (incorrect heuristics)
- Smaller model + curated skills > larger model without skills

### APPLICATION TO PLOTLOT
```python
# PlotLot Skill Implementation Examples

# 1. WebXSkill Pattern for Entitlement Tools
zoning_variance_skill = WebXSkill(
    name="zoning_variance_analyzer_v2.0",
    signature="(parcel: Parcel, variance_type: str, hardship_factors: List[str]) -> VarianceAssessment",
    preconditions=["parcel.zoning != requested_zoning", "hardship_documented_per_code"],
    postconditions=["assessment_complete", "likelihood_determined", "requirements_identified"],
    step_guidance=[
        "Verify current vs requested zoning classification",
        "Document hardship factors per local ordinance §XX.XX",
        "Research historical approval rates for similar cases",
        "Prepare variance application package per jurisdiction template",
        "Calculate estimated timeline and cost implications",
        "Identify potential community concerns and mitigation strategies"
    ],
    execution_mode="GUIDED",  # Start guided, move to grounded with experience
    version="2.0.0",
    evidence_sources=["municipal_code", "zoning_board_records", "historical_cases"],
    confidence=0.85
)

# 2. Skill Organization: URL-Based Graph
skill_registry = {
    # Indexed by jurisdiction patterns
    "jurisdiction_patterns": {
        "city_name_zoning": ["zoning_analysis", "variance_evaluation", "permit_check"],
        "county_env_dept": ["wetland_delineation", "floodplain_analysis", "stormwater_review"]
    },
    # Indexed by capability tags
    "capability_tags": {
        "zoning": ["zoning_analysis", "variance_evaluation", "rezoning_assessment"],
        "environmental": ["wetland_check", "endangered_species", "historic_review"],
        "utilities": ["water_sewer", "electrical", "telecommunications", "gas"]
    }
}

# 3. Trust-Tiered Execution for Irreversible Actions
class TrustTieredExecutor:
    def execute_irreversible_action(self, action: Action, trust_level: TrustLevel):
        if trust_level == TrustLevel.LOW:
            return self.request_approval(action)  # Require manual approval
        elif trust_level == TrustLevel.MEDIUM:
            return self.execute_with_monitoring(action)  # Execute with enhanced logging
        else:  # HIGH
            return self.execute_directly(action)  # Execute autonomously with audit

# 4. Skill Supply-Chain Governance
class SkillSupplyChainGovernor:
    def validate_skill_source(self, skill: Skill) -> ValidationResult:
        # Check skill provenance and integrity
        if not self.verify_signature(skill):
            return ValidationResult(valid=False, reason="Unsigned skill")
        
        # Check for known vulnerabilities
        if self.is_in_vulnerability_database(skill.id):
            return ValidationResult(valid=False, reason="Known vulnerable skill")
        
        # Validate skill behavior in sandbox
        behavior_result = self.sandbox_execute(skill)
        if not behavior_result.is_safe:
            return ValidationResult(valid=False, reason="Unsafe behavior detected")
        
        return ValidationResult(valid=True)
```

### Key Insights for PlotLot
- **Skill-First Design**: Prioritize reusable skills over one-off plans for land-dev processes
- **Trust-Graduated Automation**: Start with guided execution, progress to grounded as skills prove reliable
- **Supply-Chain Security**: Validate external skill/tool sources before integration
- **Meta-Skill Development**: Create skills for adapting to new jurisdictions/regulation changes
- **Evidence-Based Skill Evolution**: Use actual land-dev outcomes to refine and validate skills
- **Hierarchical Workflow Composition**: Compose basic skills (zoning check, setback calc) into complex workflows (entitlement strategy, proforma analysis)