# mode2_knowledge.py — Decomposed for RAG-based selective injection
#
# Four exports:
#   MODE2_CORE_INSTRUCTIONS — always sent to Phase B (behavioral meta-rules)
#   MODE2_PROBES            — dict keyed by probe name, looked up via Phase A routing
#   MODE2_RISK_FRAMEWORK    — Cagan four-risk-dimension framework (always included in Mode 2)
#   MODE2_PATTERNS          — dict keyed by pattern name, looked up via Phase A routing
#
# Plus backward-compatible MODE2_KNOWLEDGE that joins everything (removed after orchestrator refactor).

MODE2_CORE_INSTRUCTIONS = """
# Mode 2: Evaluate Solution — Specification

## 0. How This Fits Into the System

**What exists already (Orchestrator + Mode 1):**
- Two-phase-per-turn architecture: Phase A (lightweight routing) → Phase B (heavy execution with tools)
- 8 tools: register_assumption, update_assumption_status, record_probe_fired, record_pattern_fired, update_conversation_summary, update_org_context, generate_artifact, complete_mode
- Session state: assumption register, document skeleton, routing context, org context, conversation summary
- Mode 1 knowledge base: 7 diagnostic probes + 8 domain patterns for problem discovery

**What Mode 2 adds:**
- A new knowledge base file (`mode2_knowledge.py`) — injected into Phase B when Mode 2 is active, replacing Mode 1's knowledge base
- A new tool: `set_risk_assessment` — writes risk dimension assessments to the skeleton with validated inputs
- A new tool: `set_validation_plan` — writes the validation plan to the skeleton
- A new tool: `set_go_no_go` — writes the go/no-go recommendation to the skeleton
- New document skeleton fields for Mode 2's output artifact (flat keys, no deep nesting)
- Updated Phase A routing prompt to know when to enter/exit Mode 2

**What Mode 2 does NOT change:**
- No changes to the Phase A/B loop mechanics
- No changes to the tool execution pipeline
- The assumption register is shared — Mode 2 adds to the same register Mode 1 built

---

## 1. Core Question

**"Will this specific approach actually work?"**

Mode 2 activates when:
- A concrete solution is on the table (user has named a specific approach, technology, or product concept)
- AND the underlying problem has been validated (usually by Mode 1, but could be by the user saying "we've already validated the problem")

Mode 2 does NOT activate when:
- The user only has a problem with no proposed solution → Mode 1
- The user is exploring constraints without a solution in mind → Mode 3
- The user wants to size an opportunity → Mode 4

---

## 2. What Mode 2 Inherits from Mode 1

When Mode 2 activates after Mode 1, the session state already contains:

| State Element | What Mode 2 Does With It |
|--------------|--------------------------|
| **Assumption register** (all assumptions from Mode 1 — full register, no filtering) | Adds new solution-specific assumptions. Some Mode 1 assumptions become dependencies for Mode 2 assumptions (e.g., "data exists" → "we can build the model"). |
| **Problem statement** | The benchmark. Mode 2 evaluates the solution AGAINST this. If the solution doesn't address the validated problem, that's a finding. |
| **Stakeholder map** | Mode 2 needs to know: who would need to adopt this solution? Who would need to approve it? Who would build it? |
| **Success metrics** (leading/lagging/anti) | Mode 2 checks: does the proposed solution actually move these metrics? |
| **Decision criteria** (proceed_if / do_not_proceed_if) | Mode 2 adds solution-specific go/no-go criteria to this list. |
| **Org context** | Informs feasibility and viability assessment — what the organization can realistically build and support. |
| **Probes/patterns fired** | Mode 2 doesn't re-fire Mode 1 probes. It has its own probe set. |

If Mode 2 is entered WITHOUT Mode 1 (user claims problem is already validated):
- The system should still do a quick problem-validity check (lightweight version of Probe 1) before diving into solution evaluation
- Register the "problem is validated" claim as an assumption with confidence "informed" (not "validated" — we're taking the user's word for it)

---

## 3. Failure Modes (What Mode 2 Must Avoid)

| Failure Mode | Description | Prevention |
|-------------|-------------|------------|
| **Rubber-stamping the solution** | Goes through the motions without finding real risks | Each risk dimension must produce at least one assumption or explicitly state "no significant risk identified and why" |
| **Generic risk lists** | "You should consider scalability, security, performance..." without connection to this specific solution and context | Three-layer risk identification: (1) conversation-derived, (2) org-context-derived, (3) domain-expert-derived using Claude's subject matter knowledge of the solution type × domain intersection. See Section 4.1. |
| **Ignoring Mode 1 findings** | Evaluates the solution in isolation, not against the validated problem | Probe 1 (Solution-Problem Fit) explicitly checks alignment |
| **Conflating feasibility with desirability** | "We can build it" treated as evidence that "users will want it" | Four risk dimensions are evaluated independently, each with its own probe |
| **Premature go/no-go** | Declaring "go" or "no-go" before key assumptions are validated | Final recommendation must be conditional: "Go IF [assumptions hold]. No-go IF [these prove false]." |
| **Scope amnesia** | Solution scope creeps beyond what Mode 1 framed | Probe 7 checks for scope drift between problem definition and proposed solution |

---

## 5. Domain Patterns for Mode 2

Mode 1's 8 domain patterns are problem-discovery patterns. Mode 2 needs solution-evaluation patterns. Some Mode 1 patterns carry forward (Analytics-Execution Gap is relevant to feasibility), but Mode 2 adds its own patterns.

---

## 6. Output Artifact: Solution Evaluation Brief

### Document Skeleton Fields (added to existing skeleton)

```python
# These fields get added to st.session_state.document_skeleton
# Flat keys — no deep nesting. Each field is one level deep under document_skeleton.
# This avoids dot-notation path hallucination and keeps tool calls simple.

"solution_name": None,           # What's being evaluated
"solution_description": None,    # 2-3 sentence summary

"value_risk_level": None,        # "low" | "medium" | "high"
"value_risk_summary": None,      # 1-2 sentence assessment
"value_risk_evidence_for": [],   # what supports low risk
"value_risk_evidence_against": [],  # what supports high risk

"usability_risk_level": None,
"usability_risk_summary": None,
"usability_risk_evidence_for": [],
"usability_risk_evidence_against": [],

"feasibility_risk_level": None,
"feasibility_risk_summary": None,
"feasibility_risk_evidence_for": [],
"feasibility_risk_evidence_against": [],

"viability_risk_level": None,
"viability_risk_summary": None,
"viability_risk_evidence_for": [],
"viability_risk_evidence_against": [],

"build_vs_buy_assessment": None,  # null if not applicable, else summary

"validation_riskiest_assumption": None,  # assumption ID
"validation_approach": None,       # "painted_door" | "concierge" | "technical_spike" | "wizard_of_oz" | "prototype" | "other"
"validation_description": None,    # specific plan
"validation_timeline": None,       # estimated duration
"validation_success_criteria": None,  # what "validated" looks like

"go_no_go_recommendation": None,   # "go" | "conditional_go" | "pivot" | "no_go"
"go_no_go_conditions": [],         # what must be true for "go"
"go_no_go_dealbreakers": [],       # what would make this "no_go"
```

**Why flat keys instead of nested dicts:**
The original spec used deeply nested paths like `solution_evaluation.risk_assessment.value_risk.level` with a generic `update_document_skeleton` tool. This was identified as an engineering anti-pattern:
- LLMs hallucinate on long, precise dot-notation strings (missing middle layers, wrong key names)
- Error-retry loops burn tokens when paths don't match
- Coupling prompt text to internal variable names is fragile

Flat keys eliminate path hallucination entirely. Semantic tools (below) enforce valid inputs at the API boundary.

### Artifact Content Structure (the actual markdown rendered by generate_artifact)

```
# Solution Evaluation: [Solution Name]

## Executive Summary
[2-3 sentences: what was evaluated, against what problem, headline recommendation]

## Problem-Solution Fit
[Does this solution address the validated problem? Gaps? Scope drift?]

## Risk Assessment

### Value Risk: [LOW/MEDIUM/HIGH]
[Assessment with evidence]

### Usability Risk: [LOW/MEDIUM/HIGH]
[Assessment with evidence]

### Feasibility Risk: [LOW/MEDIUM/HIGH]
[Assessment with evidence]

### Viability Risk: [LOW/MEDIUM/HIGH]
[Assessment with evidence]

## Build vs. Buy Consideration
[If applicable]

## Key Assumptions Requiring Validation
[Table: Assumption | Impact | Current Confidence | Recommended Validation]

## Recommended Validation Approach
[Specific experiment/prototype with timeline and success criteria]

## Go/No-Go Assessment
**Recommendation: [CONDITIONAL GO / PIVOT / NO-GO]**
Proceed IF: [specific conditions]
Do NOT proceed IF: [specific dealbreakers]

## Stakeholder Questions
[Dual-tone: diplomatic questions for specific stakeholders, mapped to specific risks]
```

---

## 7. Mode Lifecycle

### Entry
Phase A detects Mode 2 entry conditions:
- User has named a specific solution AND problem context exists (from Mode 1 or user statement)
- OR user explicitly asks to evaluate a solution

Phase A sets:
```json
{
  "action": "enter_mode",
  "mode": "mode_2",
  "reasoning": "User has proposed [solution]. Problem context is established. Ready for solution evaluation."
}
```

### During Mode 2
- Probes fire in roughly the order listed (1-7), but the model adapts based on what the user reveals
- Each probe can register assumptions, update existing ones, and fire patterns
- The model uses `record_probe_fired` after each probe's completion criteria are met
- Micro-synthesis every 2-3 turns (same as Mode 1 pacing)
- Max 3 questions per turn, one cognitive task per turn (same rules as Mode 1)

### Exit
Mode 2 exits when:
- All applicable probes have fired (or been explicitly skipped with reasoning)
- The risk assessment has enough information to generate a recommendation
- The model calls `generate_artifact` to produce the Solution Evaluation Brief
- Then calls `complete_mode` to exit

### Natural Next Modes
| Finding | Suggested Next |
|---------|---------------|
| High feasibility risk | Mode 3 (Surface Constraints) for deeper constraint analysis |
| Value unclear | Mode 4 (Size & Value) to quantify the opportunity |
| Multiple solution options | Mode 5 (Prioritize & Sequence) to compare |
| Problem-solution misfit | Back to Mode 1 to reframe |

---

## 8. Implementation Changes Required

### New file:
- `mode2_knowledge.py` — Contains the full knowledge base text (probes, patterns, artifact structure, behavioral rules). Same structure as `mode1_knowledge.py`.

### New tools (added to `tools.py`):

Three semantic tools that enforce schema at the API boundary. The LLM calls meaningful operations, not generic path writes.

**Tool 1: `set_risk_assessment`**
```python
{
    "name": "set_risk_assessment",
    "description": "Set or update a risk assessment for one of the four Cagan risk dimensions. Call this as you evaluate each dimension during Mode 2.",
    "input_schema": {
        "type": "object",
        "properties": {
            "dimension": {"type": "string", "enum": ["value", "usability", "feasibility", "viability"]},
            "level": {"type": "string", "enum": ["low", "medium", "high"]},
            "summary": {"type": "string", "description": "1-2 sentence assessment of this risk dimension"},
            "evidence_for": {"type": "array", "items": {"type": "string"}, "description": "Evidence supporting low risk", "default": []},
            "evidence_against": {"type": "array", "items": {"type": "string"}, "description": "Evidence supporting high risk", "default": []},
        },
        "required": ["dimension", "level", "summary"],
    },
}
```

Handler writes to flat skeleton keys: `{dimension}_risk_level`, `{dimension}_risk_summary`, `{dimension}_risk_evidence_for`, `{dimension}_risk_evidence_against`.

**Tool 2: `set_validation_plan`**
```python
{
    "name": "set_validation_plan",
    "description": "Set the recommended validation approach for the riskiest assumption. Call this after identifying the key risks.",
    "input_schema": {
        "type": "object",
        "properties": {
            "riskiest_assumption": {"type": "string", "description": "Assumption ID (e.g., 'A5')"},
            "approach": {"type": "string", "enum": ["painted_door", "concierge", "technical_spike", "wizard_of_oz", "prototype", "other"]},
            "description": {"type": "string", "description": "Specific validation plan"},
            "timeline": {"type": "string", "description": "Estimated duration"},
            "success_criteria": {"type": "string", "description": "What 'validated' looks like"},
        },
        "required": ["riskiest_assumption", "approach", "description", "success_criteria"],
    },
}
```

Handler writes to: `validation_riskiest_assumption`, `validation_approach`, `validation_description`, `validation_timeline`, `validation_success_criteria`.

**Tool 3: `set_go_no_go`**
```python
{
    "name": "set_go_no_go",
    "description": "Set the go/no-go recommendation with conditions and dealbreakers. Call this when the evaluation is complete.",
    "input_schema": {
        "type": "object",
        "properties": {
            "recommendation": {"type": "string", "enum": ["go", "conditional_go", "pivot", "no_go"]},
            "conditions": {"type": "array", "items": {"type": "string"}, "description": "What must be true for 'go'"},
            "dealbreakers": {"type": "array", "items": {"type": "string"}, "description": "What would make this 'no_go'"},
        },
        "required": ["recommendation", "conditions", "dealbreakers"],
    },
}
```

Handler writes to: `go_no_go_recommendation`, `go_no_go_conditions`, `go_no_go_dealbreakers`.

**Why semantic tools instead of a generic `update_document_skeleton`:**
- Input validation at the API boundary (enums for level, dimension, approach)
- No dot-notation path hallucination — the LLM calls `set_risk_assessment(dimension="value", level="high", ...)` not `update_document_skeleton(field_path="solution_evaluation.risk_assessment.value_risk.level", value="high")`
- Meaningful tool names the LLM understands ("set risk" vs "update field at path X")
- Keeps total tool count manageable (3 new tools vs. 1 generic tool, but the generic tool would have been called 15+ times with error-prone paths)

**Note:** `solution_name`, `solution_description`, and `build_vs_buy_assessment` are simple string fields. These are set via the existing `update_problem_statement`-style pattern: add two small tools `set_solution_info` and `set_build_vs_buy`, or have Phase B set them directly. Simplest approach: one more tool:

**Tool 4: `set_solution_info`**
```python
{
    "name": "set_solution_info",
    "description": "Set the solution name, description, and optionally the build-vs-buy assessment. Call on first Mode 2 turn.",
    "input_schema": {
        "type": "object",
        "properties": {
            "solution_name": {"type": "string", "description": "Name of the solution being evaluated"},
            "solution_description": {"type": "string", "description": "2-3 sentence summary"},
            "build_vs_buy": {"type": "string", "description": "Build vs buy assessment (optional)"},
        },
        "required": ["solution_name", "solution_description"],
    },
}
```

### Modified files:
- `tools.py` — Add the 4 new tool definitions and handlers; update `generate_artifact` to support `solution_evaluation_brief`
- `state.py` — Add flat Mode 2 fields to document skeleton initialization
- `prompts.py` — Update Phase A prompt to include Mode 2 entry/exit conditions; add PHASE_B_MODE2_PROMPT; add new tools to tool usage docs in system prompt
- `orchestrator.py` — Update the knowledge base injection logic to load `mode2_knowledge.py` when `active_mode == "mode_2"`; add new tools to TOOL_DEFINITIONS passed to API

### No changes needed:
- `app.py` — UI doesn't change (sidebar already shows skeleton fields dynamically)
- `config.py` — No new constants

---

## 9. What Mode 2 Does NOT Do

| Activity | Where It Happens |
|----------|-----------------|
| Validate that the problem is real | Mode 1 (Discover & Frame) |
| Deep constraint mapping | Mode 3 (Surface Constraints) |
| Opportunity sizing with sensitivity analysis | Mode 4 (Size & Value) |
| Compare multiple solutions against each other | Mode 5 (Prioritize & Sequence) |
| Generate a PRD or technical spec | Artifact generation (separate from any mode) |

---

*Status: FINALIZED v1.1 (post-engineering review: flattened skeleton, semantic tools, feasibility guardrail, vendor guardrail, cannibalization check)*
*Depends on: Orchestrator + Mode 1 (implemented)*
*Inherits: Assumption register, document skeleton, org context, stakeholder map from Mode 1*
"""

# Three-layer risk identification framework — always included when Mode 2 is active.
MODE2_RISK_FRAMEWORK = """
## 4. Risk Identification Approach

### 4.1 Three-Layer Risk Identification

Mode 2 surfaces risks from three sources, in order of specificity:

**Layer 1: Conversation-derived risks**
Risks that emerge directly from what the user has said. Example: user mentions "we'll need data from the partner team" → dependency risk on an external team.

**Layer 2: Org-context-derived risks**
Risks from organizational patterns, history, and constraints captured in org context or surfaced by Mode 1. Example: org context indicates the organization has historically struggled with cross-team integrations → heightened integration risk.

**Layer 3: Domain-expert-derived risks (Claude's subject matter knowledge)**
Risks the system proactively surfaces based on the solution type × domain intersection, using Claude's training knowledge — even if nobody in the conversation mentioned them.

**Instructions for the knowledge base (how to activate Layer 3):**

The knowledge base will NOT enumerate risks by domain. Instead, it will contain instructions like:

> After identifying the solution type (ML model, data pipeline, customer-facing tool, internal platform, integration, etc.) and the operating domain (marketing, supply chain, finance, retail operations, R&D, etc.), use your subject matter expertise to generate 6-8 risks specific to this combination. Then prioritize and surface only the 3-4 highest-impact, least-obvious ones to the user.

**Quality bar — two examples of the difference:**

BAD (generic): "You should consider model scalability and data quality."

GOOD (domain-expert): "ML models in demand forecasting commonly degrade during promotional periods because the training data distribution shifts significantly. Has the team accounted for how the model handles promotional events versus baseline periods? This is a well-known failure mode in retail forecasting that often doesn't surface until the first major promotional cycle after launch."

BAD (generic): "Consider user adoption challenges."

GOOD (domain-expert): "Marketing teams typically have deeply embedded workflows around campaign planning tools. Solutions that require marketers to check a separate dashboard or change their planning sequence face much higher adoption friction than solutions that integrate into existing tools like their campaign management platform. Where does this solution sit relative to their current daily workflow?"

**Prioritization rule:**
- Skip risks the PM has likely already considered (obvious ones)
- Lead with risks that are domain-specific or solution-type-specific and easy to miss
- Register all identified risks as assumptions with confidence "guessed" and recommended validation actions — the system isn't claiming these are definitive, it's saying "based on solutions like this in domains like this, these are worth investigating"

**Cognitive load rule (same as Mode 1):**
- Surface max 3-4 risks per turn
- The system may internally identify 8-10 risks but holds the lower-priority ones for later turns
- Bring forward additional risks only when they become relevant based on what the user reveals

### 4.2 Diagnostic Probes

Seven probes for solution evaluation. Like Mode 1, not every probe fires for every input.
"""

# Probe definitions — looked up by key based on Phase A's next_probe output.
# Keys are descriptive names matching the probe's focus area.
MODE2_PROBES = {
    "Solution-Problem Fit": """### Probe 1: Solution-Problem Fit

**Purpose:** Does this solution actually solve the validated problem? This sounds obvious but is the #1 failure mode — solutions evolve during discussion and quietly decouple from the original problem.

**When it fires:** Always runs first (same as Mode 1's Probe 1 is always-first).

**What it checks:**
- Does the proposed solution address the root cause identified in Mode 1, or a symptom?
- Has the solution scope expanded beyond the original problem scope?
- Are there aspects of the validated problem that this solution doesn't address?
- Are there things this solution does that aren't related to the validated problem (scope creep)?

**Completion criteria:** An explicit statement mapping solution capabilities → validated problem elements, with gaps identified.

**Example:**
> Mode 1 validated: "Campaign managers estimate performance manually with 30-40% error rates."
> Proposed solution: "Build a digital twin simulation engine."
> Fit check: The simulation engine addresses the accuracy gap, but doesn't address the trust gap (campaign managers may not trust model predictions over their judgment). The solution also includes scenario testing capabilities that weren't part of the original problem — is that intentional scope expansion or creep?""",

    "Value Risk": """### Probe 2: Value Risk

**Purpose:** Will the target users actually choose to use this? Having a real problem doesn't guarantee adoption of a specific solution.

**When it fires:** Always (this is Cagan's first risk dimension).

**What it checks:**
- Is there evidence that users want THIS solution, not just relief from the problem?
- What's the switching cost from their current approach? (Even a bad manual process has zero learning curve)
- Would users need to change their workflow to use this? How much?
- Is the value proposition clear enough that users could explain it to a colleague?

**Key questions to explore:**
- "If this existed tomorrow, what would [target user] do differently on Monday morning?"
- "What's the minimum this needs to do to be worth switching from the current approach?"
- "Who tried to solve this before, and what happened?" (Prior failed attempts reveal adoption barriers)

**Completion criteria:** Either evidence of user demand for this approach, or identification of the adoption risk with a recommended validation step.""",

    "Usability Risk": """### Probe 3: Usability Risk

**Purpose:** Can the target users actually figure this out and integrate it into their work?

**When it fires:** When the solution involves a user-facing component (skip for pure backend/infrastructure solutions).

**What it checks:**
- Who are the actual end users? (Not the sponsor — the person using it daily)
- What's their technical sophistication?
- Does this replace an existing tool/workflow, or add a new one? (Adding is harder than replacing)
- What's the "last mile" — how does output from this tool actually influence a decision?

**Key questions to explore:**
- "Walk me through how [user] would use this in their actual workflow. What do they do before, during, and after?"
- "What happens if the tool gives a result the user disagrees with? Do they override it?"
- "Is there a simpler version of this that would capture 80% of the value?"

**Completion criteria:** A workflow integration assessment — how this fits into existing work patterns, or what changes are required.""",

    "Feasibility Risk": """### Probe 4: Feasibility Risk

**Purpose:** Can this actually be built with the available resources, data, and technology?

**When it fires:** Always (but depth varies — if the user has a strong technical team and the approach is well-understood, this can be brief).

**What it checks:**
- Does the required data exist, is it accessible, and is it clean enough?
- Does the team have the skills to build this? (Or does it depend on 1-2 key people?)
- Is this a known-solvable problem (engineering) or an unknown (research)?
- What's the realistic timeline? (Compare against organizational patience)
- Are there infrastructure dependencies?

**Key questions to explore:**
- "What's the hardest technical problem in this solution? Is that solved or unsolved?"
- "If the key technical person left tomorrow, could someone else continue this?"
- "What data does this need that you don't currently have access to?"

**Completion criteria:** Classification of technical risk as low (engineering problem, known approach), medium (some unknowns, but manageable), or high (research problem, uncertain if solvable). With specific unknowns identified.

**Feasibility confidence guardrail:** The system cannot validate technical feasibility — it can only surface the right questions. If no named technical stakeholder has confirmed feasibility, register any feasibility assessment as confidence "guessed" regardless of how plausible the approach sounds. A solution that "sounds feasible" based on textbook knowledge is not the same as one confirmed by someone who knows the codebase, the tech debt, and the team's actual capabilities.""",

    "Viability Risk": """### Probe 5: Viability Risk

**Purpose:** Does this make business sense? Can the organization afford to build, launch, and maintain it?

**When it fires:** Always, but especially deep when the solution requires significant investment or organizational change.

**What it checks:**
- What's the total cost of ownership (build + maintain + support)?
- Does this align with current organizational priorities and budget cycles?
- Who needs to approve this, and what's their appetite for this type of investment?
- Is there a sustainable model for maintaining this after launch? (Or does it become shelfware?)
- Does this create dependencies on external vendors or partners?
- **Cannibalization check:** Does this solution's success for one stakeholder create losses for another? Especially in multi-sided business models (e.g., optimizing CPG campaign spend could erode Kroger's private label margin; maximizing ad revenue could degrade shopper experience). This is distinct from anti-metrics — anti-metrics track what shouldn't get worse within the same stakeholder's domain; cannibalization tracks cross-stakeholder value transfer.

**Key questions to explore:**
- "Who approves the budget for this, and what's their decision timeline?"
- "What happens to this product in 2 years? Who maintains it?"
- "Does this compete with any other initiative for the same resources?"

**Completion criteria:** Assessment of organizational alignment and sustainability, with specific approval gates identified.""",

    "Build vs Buy": """### Probe 6: Build vs. Buy vs. Partner

**Purpose:** Has the user considered that building from scratch may not be the right approach?

**When it fires:** When the proposed solution is a custom build. Suppress if the user has already evaluated alternatives or if the solution is clearly unique to their context.

**What it checks:**
- Are there existing products or platforms that solve this or something close?
- What's the total cost of building vs. licensing vs. partnering?
- What's the maintenance burden of a custom build vs. a managed solution?
- Is the differentiation in the solution itself, or in how it's applied? (If the latter, buy the platform and customize the application)

**Key questions to explore:**
- "Have you looked at what's available on the market for this?"
- "What part of this solution is truly unique to your context vs. a general capability?"
- "If a vendor could get you 70% of the way there, would that be worth exploring?"

**Completion criteria:** Either a justified build decision (with reasoning for why buy/partner won't work) or a recommendation to evaluate alternatives.

**Vendor knowledge guardrail:** Do not recommend specific vendors or products. The system's knowledge of the vendor landscape may be outdated. Instead, help the PM define evaluation criteria for vendor assessment and ask whether they've done a current market scan. The output of this probe should be a decision framework ("here's how to evaluate build vs. buy for this specific case"), not vendor recommendations.""",

    "Validation Approach": """### Probe 7: Validation Approach

**Purpose:** What's the fastest, cheapest way to test the riskiest assumptions before committing to a full build?

**When it fires:** After the other probes have identified the key risks. This is typically the last probe.

**What it checks:**
- What's the single riskiest assumption? (From the assumption register)
- What's the cheapest experiment that would validate or invalidate it?
- What prototype fidelity is appropriate? Options:
  - **Painted door test:** Fake the feature, measure demand (tests value risk)
  - **Concierge MVP:** Do it manually for a few users, learn what actually matters (tests value + usability risk)
  - **Technical spike:** Build the hardest part first, see if it works (tests feasibility risk)
  - **Wizard of Oz:** User thinks it's automated, human does it behind the scenes (tests value + usability without feasibility investment)
  - **Clickable prototype:** Non-functional mockup for user feedback (tests usability risk)

**Key questions to explore:**
- "What's the one thing that, if it turned out to be wrong, would kill this project?"
- "Can we test that assumption in under 2 weeks with minimal investment?"
- "What would 'good enough evidence' look like to proceed to full build?"

**Completion criteria:** A specific validation recommendation with approach, timeline, and success criteria.""",
}

# Domain patterns — looked up by key when Phase A detects a triggered pattern.
MODE2_PATTERNS = {
    "Build It and They Will Come": """### Pattern 1: "Build It and They Will Come"
**Trigger:** ALL: custom build proposed + no distribution/adoption plan + users not involved in design
**Why it exists:** Technical teams often focus on building the capability and assume users will adopt it because the problem is real. But adoption requires change management, training, workflow integration, and often organizational incentives. Failure to plan for adoption is the #1 reason technically successful projects fail to deliver value.
**What it does:** Registers a high-impact assumption: "target users will adopt this without a dedicated adoption plan." Asks about distribution strategy, change management, and user involvement in design.""",

    "V1 Overengineering": """### Pattern 2: "V1 Overengineering"
**Trigger:** ALL: first version + >6 month timeline + no prior validation
**Why it exists:** Teams sometimes design V1 as a comprehensive platform when a narrower first version would validate the core hypothesis faster and cheaper. The risk is spending 12 months building something that misses the mark when a 6-week version would have revealed that.
**What it does:** Asks: "What's the smallest version of this that would tell you if the approach works? Could you validate the core value proposition with a fraction of the planned scope?" """,

    "Data Optimism": """### Pattern 3: "Data Optimism"
**Trigger:** ANY: ML/AI-based solution, data pipeline dependency, "we have the data" without specifics
**Why it exists:** Solutions involving data or ML almost always underestimate data preparation effort. "We have the data" usually means "the data exists somewhere" — not that it's accessible, clean, at the right granularity, or has sufficient history. This is the most common source of timeline overruns.
**What it does:** Registers a feasibility assumption about data readiness. Asks: "Have you actually looked at this data? Is it at the granularity you need? How much cleaning/transformation is required? What's the historical depth?" """,

    "Key Person Dependency": """### Pattern 4: "Key Person Dependency"
**Trigger:** ALL: specialized technical approach + small team (<5) + timeline >6 months
**Why it exists:** Complex technical solutions often depend on 1-2 people with specialized knowledge. If those people leave, get reassigned, or burn out, the project stalls. This risk increases with timeline length.
**What it does:** Registers a feasibility risk about talent continuity. Asks about knowledge transfer plans, documentation practices, and whether the approach could be simplified to reduce single-point-of-failure risk.
*Note: This overlaps with Mode 1's Pattern 5 (Talent Drain). If already fired in Mode 1, Mode 2 references the existing assumption rather than re-registering.*""",

    "Integration Underestimation": """### Pattern 5: "Integration Underestimation"
**Trigger:** ANY: connects to existing systems, replaces current tool, requires API/data integration
**Why it exists:** New solutions rarely exist in isolation — they need to connect to existing tools, data sources, and workflows. Integration work is consistently underestimated because it involves negotiating with other teams, understanding undocumented dependencies, and working with systems you don't control.
**What it does:** Asks: "What systems does this need to connect to? Who owns those systems? Have you discussed this integration with them? What's their roadmap and availability?" """,
}

# Backward-compatible export — joins everything into a single string.
# Used by current orchestrator.py imports. Will be removed after orchestrator refactor.
MODE2_KNOWLEDGE = (
    MODE2_CORE_INSTRUCTIONS
    + "\n\n" + MODE2_RISK_FRAMEWORK
    + "\n\n" + "\n\n".join(MODE2_PROBES.values())
    + "\n\n" + "\n\n".join(MODE2_PATTERNS.values())
)
