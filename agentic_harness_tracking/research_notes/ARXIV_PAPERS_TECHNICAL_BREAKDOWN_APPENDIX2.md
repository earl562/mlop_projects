---

# PAPER 19: 2602.14878 - Model Context Protocol (MCP) Tool Descriptions Are Smelly! Towards Improving AI Agent Efficiency with Augmented MCP Tool Descriptions

**Authors:** Mohammed Mehedi Hasan et al.  
**Date:** 16 Feb 2026 (v1), last revised 31 May 2026 (v3) | cs.SE

## TECHNICAL BREAKDOWN

### Core Problem
The Model Context Protocol (MCP) enables FM-based agents to interact with external systems via tools, but agents rely on natural-language tool descriptions to understand tool purpose and features. Defects or "smells" in these descriptions can misguide agents, yet their prevalence and consequences in the MCP ecosystem were previously unclear.

### Methodology
- **Dataset**: 856 tools across 103 MCP servers (official and community-maintained)
- **Approach**: 
  1. Identified six components of tool descriptions from literature
  2. Developed scoring rubric using these components
  3. Formalized tool description smells based on rubric
  4. Operationalized rubric via FM-based scanner
  5. Evaluated impact of augmentation using MCP Universe benchmark

### Six Components of Tool Descriptions
From literature review, tool descriptions consist of:
1. **Purpose**: Clear statement of what the tool does
2. **Parameters**: Explicit argument names, types, and constraints
3. **Usage Guidelines**: Instructions on when and how to use the tool
4. **Examples**: Concrete usage examples with sample inputs/outputs
5. **Limitations**: Known constraints, edge cases, or failure conditions
6. **Error Handling**: Description of error conditions and responses

### Smell Derivation
Tool description smells are defined as deviations from ideal component quality:
- **Unclear Purpose**: Vague or ambiguous description of tool functionality
- **Opaque Parameters**: Missing/unclear parameter names, types, or constraints
- **Missing Usage Guidelines**: Lack of instructions on appropriate use contexts
- **Omitted Examples**: Absence of concrete usage illustrations
- **Unstated Limitations**: Failure to document constraints or edge cases
- **Poor Error Handling**: Inadequate description of error conditions/responses

### Key Results

#### RQ-1: Smell Prevalence
- **97.1%** of tool descriptions contain at least one smell
- **56%** fail to state purpose clearly (Unclear Purpose smell)
- Majority exhibit multiple smells, particularly:
  - Unstated Limitations
  - Missing Usage Guidelines  
  - Opaque Parameters
- Similar issues in both official and community-maintained servers

#### RQ-2: Impact of Full Augmentation
Augmenting descriptions with all components:
- ✅ **Improves task success rates** by median **+5.85 percentage points**
- ✅ **Improves partial goal completion** by **+15.12%** (Average Evaluator score)
- ❌ **Increases execution steps** by **+67.46%** (median)
- ❌ **Causes performance regressions** in **16.67%** of cases
- **Trade-off**: Semantic completeness vs. token efficiency/execution cost

#### RQ-3: Component-Level Impact (Ablation Study)
- No single component combination consistently improves performance across all domains/models
- **Examples component removal** does not statistically degrade performance
- **Compact variants** often preserve behavioral reliability while reducing token overhead
- Practitioners should identify impactful components for their specific domain/model

### MCP Tool Description Rubric (1-5 scale per component)
```
Purpose (1-5): 
  5 = Crystal clear, actionable statement of tool functionality
  3 = Basic purpose understandable but lacks detail
  1 = Vague, ambiguous, or misleading purpose description

Parameters (1-5):
  5 = All parameters explicitly named with types/constraints
  3 = Most parameters defined but some ambiguity
  1 = Parameter names/types unclear or missing

Usage Guidelines (1-5):
  5 = Clear instructions on when/how to use tool
  3 = Basic guidelines present but incomplete
  1 = Missing or confusing usage instructions

Examples (1-5):
  5 = Relevant, varied examples with inputs/outputs
  3 = Limited or poorly explained examples
  1 = No examples provided

Limitations (1-5):
  5 = Comprehensive documentation of constraints/edge cases
  3 = Some limitations mentioned but incomplete
  1 = No limitations described

Error Handling (1-5):
  5 = Clear error conditions and response descriptions
  3 = Basic error info present but incomplete
  1 = No error handling information
```

### Tool Description Augmentation Process
1. **Initial Assessment**: Evaluate description against six-component rubric
2. **Component Augmentation**: Systematically enhance each weak component
3. **Examples/Limitations Generation**: Use FMs to create realistic examples and identify limitations
4. **Automated Task Generation**: Scale augmentation via synthetic task creation
5. **Final Consolidation**: Integrate augmented components into coherent description

### Tool Description Router
Enables runtime experimentation with description variants:
- MCP users can test multiple description versions without server modification
- Router selects best-performing variant based on workflow metrics
- Facilitates A/B testing of description improvements

### Key Insights
1. **Semantic Completeness ≠ Always Better**: Richer descriptions improve accuracy but increase token usage and execution steps
2. **Context Matters**: Optimal description complexity depends on domain, model, and available context window
3. **Component Trade-offs**: Different components impact performance differently; Examples often least critical
4. **Augmentation Cost-Benefit**: Improvements require justification; seek compact effective variants
5. **Continuous Improvement**: Descriptions should evolve based on agent performance feedback

### APPLICATION TO PLOTLOT

#### 1. Standardized Tool Description Templates for Land-Dev MCP Servers
```python
# Template for PlotLot Land-Dev MCP Tools
LAND_DEV_TOOL_DESC_TEMPLATE = """
{Purpose}: Clear, actionable statement of what the land-dev tool accomplishes.

{Parameters}:
  - param_name (type): Description with constraints/examples
  - [Repeat for all parameters]

{Usage Guidelines}: 
  - When to use this tool (appropriate scenarios)
  - Prerequisites or preconditions
  - Recommended workflow position

{Examples}:
  - Example 1: [Input] → [Output] with explanation
  - Example 2: [Input] → [Output] with explanation

{Limitation}:
  - Known constraints or edge cases
  - Conditions where tool may not apply
  - Accuracy or precision boundaries

{Error Handling}:
  - Error conditions that may occur
  - Expected error responses or fallback behaviors
"""

# Example: Zoning Query Tool
ZONING_QUERY_TOOL_DESC = LAND_DEV_TOOL_DESC_TEMPLATE.format(
    Purpose="Retrieve applicable zoning regulations for a specific parcel and jurisdiction",
    Parameters="""
      - parcel_id (string): Unique identifier for the parcel (APN or address)
      - jurisdiction (string): City/county name or FIPS code
      - date_effective (string, optional): Date for which regulations apply (YYYY-MM-DD format, defaults to current)
    """,
    Usage Guidelines="""
      - Use during site analysis phase to identify applicable zoning constraints
      - Prerequisite: Parcel must be geocoded and jurisdiction identified
      - Call before variance analysis or entitlement strategy development
    """,
    Examples="""
      - Input: parcel_id="123-456-789", jurisdiction="Springfield" 
        → Output: {zoning_code: "R-1", max_height: 35, setbacks: {front: 25, side: 10, rear: 20}}
      - Input: parcel_id="987-654-321", jurisdiction="Shelby County", date_effective="2023-01-01"
        → Output: {zoning_code: "C-2", max_height: 50, setbacks: {front: 10, side: 0, rear: 10}, special_conditions: ["historic_district"]}
    """,
    Limitation="""
      - Does not reflect pending zoning changes not yet in effect
      - May not capture site-specific variances or conditional use permits
      - Accuracy dependent on municipal data update frequency (typically monthly)
    """,
    Error Handling="""
      - INVALID_PARCEL: Parcel ID not found in jurisdiction records
      - JURISDICTION_NOT_FOUND: Unable to locate specified jurisdiction
      - DATA_UNAVAILABLE: Zoning data temporarily unavailable for jurisdiction
      - FORMAT_ERROR: Invalid date format provided
    """
)
```

#### 2. MCP Description Augmentation System for PlotLot
```python
class PlotLotMcpDescriptionAugmentor:
    def __init__(self):
        self.rubric_evaluator = ComponentRubricEvaluator()
        self.example_generator = ExampleGenerator()
        self.limitations_identifier = LimitationsIdentifier()
        
    def augment_tool_description(self, server_name: str, tool_name: str, 
                               original_description: str) -> str:
        """Augment MCP tool description using six-component framework"""
        
        # 1. Evaluate original description
        component_scores = self.rubric_evaluator.evaluate(original_description)
        
        # 2. Identify deficient components (< 3/5 score)
        deficient_components = [
            comp for comp, score in component_scores.items() 
            if score < 3
        ]
        
        # 3. Augment each deficient component
        augmented_desc = original_description
        for component in deficient_components:
            if component == "purpose":
                augmented_desc = self._augment_purpose(augmented_desc, tool_name)
            elif component == "parameters":
                augmented_desc = self._augment_parameters(augmented_desc, tool_name)
            elif component == "usage_guidelines":
                augmented_desc = self._augment_usage_guidelines(augmented_desc, tool_name)
            elif component == "examples":
                augmented_desc = self._augment_examples(augmented_desc, tool_name)
            elif component == "limitations":
                augmented_desc = self._augment_limitations(augmented_desc, tool_name)
            elif component == "error_handling":
                augmented_desc = self._augment_error_handling(augmented_desc, tool_name)
        
        # 4. Generate examples and limitations if missing
        if "examples" in deficient_components:
            augmented_desc = self.example_generator.generate_examples(
                augmented_desc, tool_name
            )
        if "limitations" in deficient_components:
            augmented_desc = self.limitations_identifier.identify_limitations(
                augmented_desc, tool_name
            )
            
        return self._consolidate_description(augmented_desc)
    
    def _augment_purpose(self, description: str, tool_name: str) -> str:
        """Enhance purpose statement using land-dev domain knowledge"""
        purpose_templates = {
            "zoning_query": "Retrieve applicable zoning regulations including use districts, density limits, and dimensional standards",
            "variance_analyzer": "Analyze likelihood of obtaining zoning variances based on hardship factors and historical approval rates",
            "permit_checker": "Verify permit requirements and approval processes for proposed land development activities",
            "environmental_screen": "Identify potential environmental constraints including wetlands, habitats, and hazardous materials",
            "utility_coordinator": "Map utility infrastructure and identify potential conflicts with proposed development"
        }
        
        base_purpose = purpose_templates.get(tool_name, 
            f"Perform {tool_name.replace('_', ' ')} analysis for land development site assessment")
            
        # Insert or enhance purpose statement
        if "Purpose:" not in description:
            return f"Purpose: {base_purpose}\n{description}"
        else:
            # Replace existing purpose with enhanced version
            import re
            return re.sub(
                r'Purpose:.*', 
                f'Purpose: {base_purpose}', 
                description
            )
    
    # Similar methods for other components (_augment_parameters, etc.)
```

#### 3. Tool Description Router for Runtime Experimentation
```python
class PlotLotToolDescriptionRouter:
    def __init__(self):
        self.description_variants = {}  # tool_name -> [desc_variants]
        self.performance_metrics = {}   # (tool_name, variant_id) -> metrics
        
    def register_variant(self, tool_name: str, variant_id: str, 
                        description: str, metadata: dict = None):
        """Register a description variant for a tool"""
        if tool_name not in self.description_variants:
            self.description_variants[tool_name] = []
            
        self.description_variants[tool_name].append({
            "id": variant_id,
            "description": description,
            "metadata": metadata or {},
            "registered_at": datetime.now()
        })
        
    def select_best_variant(self, tool_name: str, context: dict) -> str:
        """Select best-performing variant based on historical metrics"""
        if tool_name not in self.description_variants:
            raise ValueError(f"No variants registered for tool {tool_name}")
            
        variants = self.description_variants[tool_name]
        if not variants:
            raise ValueError(f"No variants available for tool {tool_name}")
            
        # Select variant with best historical performance in similar context
        best_variant = None
        best_score = -1
        
        for variant in variants:
            variant_id = variant["id"]
            metric_key = (tool_name, variant_id)
            
            if metric_key in self.performance_metrics:
                metrics = self.performance_metrics[metric_key]
                # Weighted score: success_rate (0.4) + efficiency (0.3) + quality (0.3)
                score = (
                    metrics.get("success_rate", 0) * 0.4 +
                    (1 - metrics.get("normalized_steps", 1)) * 0.3 +  # Invert steps (lower is better)
                    metrics.get("output_quality", 0) * 0.3
                )
                
                if score > best_score:
                    best_score = score
                    best_variant = variant
        
        # Fallback to most recently registered variant if no metrics
        return best_variant["description"] if best_variant else variants[-1]["description"]
    
    def record_performance(self, tool_name: str, variant_id: str, 
                         metrics: dict):
        """Record performance metrics for a description variant"""
        metric_key = (tool_name, variant_id)
        self.performance_metrics[metric_key] = metrics
```

#### 4. Integration with PlotLot Harness
```python
class PlotLotMcpEnhancedHarness:
    def __init__(self):
        self.description_augmentor = PlotLotMcpDescriptionAugmentor()
        self.description_router = PlotLotToolDescriptionRouter()
        self.mcp_client = McpClient()
        
    async def invoke_tool(self, server_name: str, tool_name: str, 
                         tool_args: dict) -> Any:
        """Invoke MCP tool with enhanced description handling"""
        
        # 1. Get original tool description from MCP server
        original_description = await self.mcp_client.get_tool_description(
            server_name, tool_name
        )
        
        # 2. Augment description using six-component framework
        augmented_description = self.description_augmentor.augment_tool_description(
            server_name, tool_name, original_description
        )
        
        # 3. Register variant for future routing
        variant_id = f"augmented_{int(datetime.now().timestamp())}"
        self.description_router.register_variant(
            f"{server_name}.{tool_name}", 
            variant_id, 
            augmented_description,
            {"augmentation_method": "six_component", "server": server_name}
        )
        
        # 4. Select best variant for current invocation
        selected_description = self.description_router.select_best_variant(
            f"{server_name}.{tool_name}", 
            {"tool_args": tool_args, "server": server_name}
        )
        
        # 5. Enhance MCP client context with selected description
        enhanced_context = await self.mcp_client.prepare_invocation_context(
            server_name, tool_name, tool_args, selected_description
        )
        
        # 6. Execute tool with enhanced context
        result = await self.mcp_client.invoke_tool(
            server_name, tool_name, tool_args, enhanced_context
        )
        
        # 7. Record performance for future variant selection
        performance_metrics = self._extract_performance_metrics(result)
        self.description_router.record_performance(
            f"{server_name}.{tool_name}",
            variant_id,
            performance_metrics
        )
        
        return result
```

### Key Benefits for PlotLot
1. **Improved Tool Selection Accuracy**: Clearer descriptions reduce incorrect tool selection by FM
2. **Better Parameterization**: Explicit parameters reduce incorrect/incomplete tool invocations
3. **Reduced Token Overhead**: Component-aware augmentation balances completeness with efficiency
4. **Enhanced Agent Reliability**: Fewer execution steps needed for same task completion
5. **Runtime Optimization**: Description router enables continuous improvement without server changes
6. **Supply-Chain Quality**: Standardized templates improve quality of third-party tool integrations
7. **Traceability**: Performance tracking enables data-driven description refinement

### Recommendations for PlotLot Implementation
1. **Adopt Six-Component Standard**: Require all PlotLot MCP tools to follow Purpose/Parameters/Usage/Examples/Limitations/Error structure
2. **Build Description Augmentation Pipeline**: Automatically enhance descriptions during tool registration
3. **Implement Description Router**: Enable A/B testing of description variants in production
4. **Create Land-Dev Template Library**: Standardized templates for common land-dev tool categories
5. **Establish Feedback Loop**: Use agent performance metrics to continuously refine descriptions
6. **Train FM Agents**: Fine-tune models to better utilize structured tool descriptions
7. **Monitor Component Impact**: Track which description components most affect land-dev task performance