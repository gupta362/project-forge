# PM Agents v2 — Orchestrator Specification (v2)

## Document Purpose
This is the finalized orchestrator design spec, compiled from iterative design sessions. It captures all architecture decisions, interaction patterns, and data structures needed to implement the orchestrator layer of the PM Agents system.

**Changelog v2.1 (post spec review):**
- Replaced static OrgContext file with dynamic enrichment (model knowledge + optional user input)
- See claude-code-implementation-spec for full implementation changes from spec review

**Changelog v2:**
- Added granular tool/function calls for state management (replaces JSON blob updates)
- Added two-phase-per-turn architecture (lightweight routing + heavy execution)
- Replaced "match tone to user's energy" with "match density to risk"
- Added support for unstructured document paste (messy Confluence/SharePoint dumps)
- Refined dual-tone output structure (blunt analysis + diplomatic stakeholder scripts)

---

## 1. Architecture Overview

### Core Architecture Decision
**Single orchestrator with dynamically-injected specialized modes** (not a multi-agent router).

The previous system used a coordinator agent that routed to separate specialist agents. This failed because:
- Problems rarely map to ONE agent cleanly (e.g., "digital twins for pre-campaign measurement" needs problem exploration AND solution validation AND constraints)
- The coordinator matched keywords to categories instead of diagnosing where the user is in their thinking
- Context was lost between agents because it had to be serialized through state

### Five System Components

| Component | Description | Persistence |
|-----------|-------------|-------------|
| **Orchestrator** | Two-phase routing + execution layer, assumption checking, mode sequencing, progressive questioning | Per-session (prompt) |
| **5 Mode Knowledge Bases** | Deep PM expertise, dynamically injected when a mode activates | Static (loaded on demand) |
| **Assumption Register** | Structured state managed via granular tool calls with dependency tracking | Per-session (application state) |
| **Document Skeleton** | Structured state managed via granular tool calls, rendered into artifacts on demand | Per-session (application state) |
| **OrgContext** | Dynamic context built from model knowledge + optional user-provided internal details. Two layers: public (auto-populated from model knowledge about the company/domain) and internal (user-provided organizational details). Enriched on turn 1 and re-enriched if problem domain shifts materially. | Per-session (application state) |

### Why Not Multi-Agent?
The intelligence of this system lives in three places:
1. **Diagnostic reasoning** — knowing where the user is in their PM journey (orchestrator)
2. **Domain expertise** — deep frameworks and patterns for each type of analysis (mode knowledge bases)
3. **Context continuity** — tracking what's been learned and how new info affects prior conclusions (assumption register)

A single orchestrator naturally holds all context. Separate agents require explicit state passing, which is lossy.

### Two-Phase-Per-Turn Architecture

Each turn is processed in two phases to prevent attention dilution:

```
User Message Arrives
        │
        ▼
┌─────────────────────────┐
│ PHASE A: Think (Light)  │
│                         │
│ - Read assumption register
│ - Check for conflicts   │
│ - Determine next action:│
│   • Continue questioning│
│   • Enter a mode        │
│   • Flag assumption risk│
│ - Select which probe or │
│   mode to activate      │
│                         │
│ Output: Internal routing│
│ decision + any flags    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ PHASE B: Act (Heavy)    │
│                         │
│ If still gathering      │
│ context:                │
│   → Orchestrator prompt │
│   → Ask questions       │
│   → Micro-synthesize    │
│                         │
│ If entering a mode:     │
│   → Inject mode KB      │
│   → Run mode analysis   │
│   → Generate output     │
│                         │
│ Output: User-facing     │
│ response + tool calls   │
│ for state updates       │
└─────────────────────────┘
```

**Why two phases?** A single LLM call trying to analyze input + check assumptions + select mode + generate deep response suffers from attention dilution. Splitting "think about what to do" from "do it" keeps each call focused.

**Note:** During early turns (context gathering), Phase B is still the orchestrator asking questions — it doesn't route to a mode until critical mass is reached. The split isn't always "router → responder"; it's "decide → execute."

---

## 2. The Five Modes

Each mode has a **fundamentally different analytical question**, distinct output structure, and different frameworks.

| Mode | Core Question | Activates When | Key Outputs |
|------|---------------|-----------------|-------------|
| **Mode 1: Discover & Frame** | "What's really going on, and is it worth pursuing?" | User has an unvalidated problem/opportunity. OR user mentions a solution without evidence of prior validation. | Problem definition, stakeholder map, severity assessment, success metrics, decision criteria |
| **Mode 2: Evaluate Solution** | "Will this specific approach actually work?" | A concrete solution is on the table AND the underlying problem has been validated. | 4-risks analysis (Value, Usability, Feasibility, Viability), risk matrix, go/no-go criteria |
| **Mode 3: Surface Constraints** | "What will block us or limit what's possible?" | User suspects hidden limitations. OR orchestrator detects unvalidated assumptions about what's feasible. | Constraint inventory by type, severity matrix, negotiable vs. fixed, binding constraint identification |
| **Mode 4: Size & Value** | "How much is this worth, and what drives that number?" | Problem is defined and user needs to quantify the opportunity. | Value estimation with explicit assumptions, sensitivity analysis, labeled as "Projected Opportunity (Unadjusted)" |
| **Mode 5: Prioritize & Sequence** | "Given multiple options, what order and why?" | User is comparing across multiple validated options. | Framework-based comparison, ranked recommendation, sequencing rationale, cost of delay analysis |

### Mode Boundaries
- **Experimentation** is NOT a separate mode — it's an output that multiple modes produce
- **User Research** is a method that feeds multiple modes, not a mode itself
- **Stakeholder Management** is embedded in Mode 1 (stakeholder mapping) and the orchestrator (proactive stakeholder surfacing)
- **Success Metrics** are a mandatory output of Mode 1 and Mode 2, not a separate mode

### Dynamic Context Injection
The orchestrator holds a lightweight meta-prompt with mode definitions. When a mode activates, its full knowledge base is injected into the context, replacing the previous mode's knowledge base. This prevents context window bloat from loading all 5 knowledge bases simultaneously.

---

## 3. State Management via Granular Tool Calls

### Why Tool Calls (Not JSON Blob Updates)

LLMs are unreliable at maintaining large JSON objects over long conversations. When asked to "update the success_metrics field," the model often regenerates the entire object, accidentally deleting or hallucinating other fields that fell out of immediate focus.

**Solution:** All state mutations happen through explicit, atomic function calls. The application layer handles inserting/updating the data without touching anything else.

### State Management Functions

#### Assumption Register Functions

```python
register_assumption(
    claim: str,           # "Mobile reach is 30%"
    type: str,            # "value" | "technical" | "stakeholder_dependency" | "market" | "organizational"
    impact: str,          # "high" | "medium" | "low"
    confidence: str,      # "validated" | "informed" | "guessed"
    basis: str,           # "User stated during Mode 4 valuation"
    surfaced_by: str,     # "Mode 1: Probe 3"
    depends_on: list[str] = [],  # ["A1", "A2"]
    recommended_action: str = "",
    implied_stakeholders: list[str] = []  # For stakeholder_dependency type
) -> str  # Returns assumption ID (e.g., "A1")

update_assumption_status(
    assumption_id: str,   # "A1"
    new_status: str,      # "active" | "at_risk" | "invalidated" | "confirmed"
    reason: str           # "Mode 3 discovered mobile reach is only 10%"
) -> None

update_assumption_confidence(
    assumption_id: str,   # "A1"
    new_confidence: str,  # "validated" | "informed" | "guessed"
    reason: str           # "User confirmed with analytics team"
) -> None

get_assumptions(
    status: str = None,   # Filter by status
    impact: str = None,   # Filter by impact
    type: str = None      # Filter by type
) -> list[dict]

get_at_risk_assumptions() -> list[dict]  # Convenience: all at_risk + invalidated
```

#### Document Skeleton Functions

```python
update_problem_statement(text: str) -> None
update_target_audience(text: str) -> None

add_stakeholder(
    name: str,            # "Store Operations"
    type: str,            # "decision_authority" | "pain_holder" | "status_quo_beneficiary" | "execution_dependency"
    validated: bool = False,
    notes: str = ""
) -> str  # Returns stakeholder ID

update_success_metrics(
    leading: str = None,
    lagging: str = None,
    anti_metric: str = None
) -> None

update_value_estimate(
    estimate: str,
    label: str = "Projected Opportunity (Unadjusted)",
    depends_on_assumptions: list[str] = []
) -> None

add_decision_criteria(
    criteria_type: str,   # "proceed_if" | "do_not_proceed_if"
    condition: str        # "Campaign managers confirm budget allocation is a pain point"
) -> None

add_constraint(
    constraint: str,
    type: str,            # "technical" | "organizational" | "resource" | "regulatory"
    severity: str,        # "hard_blocker" | "negotiable" | "soft"
    source: str           # "Mode 3 analysis"
) -> None

update_proposed_solution(text: str) -> None
update_prioritization_rationale(text: str) -> None

generate_artifact(
    artifact_type: str    # "prd" | "one_pager" | "problem_brief" | "executive_summary"
) -> str  # Returns rendered document
```

### Benefits of Tool-Based State Management
1. **Atomic operations** — each mutation is isolated, no risk of accidentally overwriting unrelated fields
2. **Audit trail** — every tool call is logged, creating a history of how the analysis evolved
3. **Reliability** — application layer handles data integrity, LLM only decides WHAT to update
4. **Debuggability** — easy to see which tool call caused unexpected state

---

## 4. Orchestrator Responsibilities

### 4.1 Intake & Triage

**Goal:** Determine where the user is in their thinking maturity and propose a starting point.

**Three Diagnostic Signals:**

| Signal | What It Detects | How to Evaluate |
|--------|-----------------|-----------------|
| **Solution Specificity** | Has the user named a specific solution or technical approach? | High specificity + low validation evidence = likely premature solution focus → start with Mode 1 |
| **Evidence of Prior Validation** | Does the user reference data, interviews, stakeholder conversations, or prior analysis? | References to evidence suggest the user has done discovery work → may be ready for Mode 2-5 |
| **Specificity of Ask** | Is the request open-ended ("help me think through this") or targeted ("is this viable?")? | Open-ended = early stage, targeted = later stage (but verify with Signal 2) |

**Decision Logic:**
- High solution specificity + low validation evidence → "You've described a specific approach, but I want to make sure the underlying need is validated. I'd recommend starting with Discover & Frame."
- High validation evidence + specific ask → Proceed to the requested mode
- Low everything → Start with Mode 1, begin with broad context gathering

**Critical Rule:** Always offer an escape hatch. "...or do you already have validation for the underlying problem and want to jump straight to solution evaluation?"

### 4.2 Progressive Context Gathering

**Goal:** Build understanding through focused questioning without overwhelming the user.

**Interaction Pattern:**

```
Turns 1-3:  Ask 2-3 high-impact questions (motivated — user understands why)
Turns 2-3:  Micro-synthesis: "Here's what I'm understanding so far: [1-2 sentences]"
Turns 4-6:  Follow-up questions driven by what previous answers revealed
Turns 5-6:  Micro-synthesis: "Building on that: [updated understanding]"
Turn 7-ish: Critical mass check → Full synthesis + propose mode entry
```

**Critical Mass Criteria (ready to enter a mode):**
1. The core problem/opportunity is articulable in 2-3 sentences
2. The primary stakeholders are identified (even if not fully mapped)
3. At least the highest-impact assumptions are surfaced

### 4.3 Density-to-Risk Principle

**The system's depth of questioning is driven by how risky the assumptions are, NOT by the user's tone or energy level.**

| Input Characteristics | System Behavior |
|----------------------|-----------------|
| Brief input + high-risk unvalidated assumptions | Deep probing. Ask the hard question even if user wants to move fast. Stay concise — one focused question, not three paragraphs. |
| Brief input + low-risk (user has clearly done homework) | Light touch. Confirm a few things and proceed. |
| Detailed input + high-risk assumptions embedded | Acknowledge the detail, then probe the specific high-risk gaps. |
| Detailed input + well-validated | Minimal probing. Proceed to mode execution. |

**Critical rule:** The system NEVER skips high-risk probing because the user seems impatient or action-oriented. A brief, confident "Build digital twins, go!" with zero validation evidence gets the same depth of questioning as a long, uncertain exploration. The system stays concise either way — but it asks the hard question regardless.

**Anti-pattern:** "Matching energy." If the user is in execution mode but the risk is high, the system does NOT match that energy. It says: "You're ready to move fast — before we do, one thing that could derail this: [specific high-risk question]."

### 4.4 Mode Execution Management

After context gathering reaches critical mass:

1. **Propose mode with reasoning**
2. **Inject mode knowledge base** dynamically (swap context, not accumulate)
3. **After mode completes:**
   - Surface the most relevant output
   - Full analysis available if user asks
   - Suggest natural next mode based on what was learned
   - Execute tool calls to update assumption register and document skeleton

### 4.5 Assumption Management

#### Orchestrator Behavior by Severity

| Combination | Orchestrator Action |
|-------------|---------------------|
| **High Impact + Guessed** | Proactively flag BEFORE leaving current mode |
| **High Impact + Invalidated** | Automatic backward transition recommendation |
| **Medium Impact + Invalidated** | Flagged but doesn't interrupt flow |
| **Low Impact anything** | Logged quietly via tool call, surfaced only on review |

### 4.6 Conflict Detection

Four categories of conflicts:

| Category | Description | Detection | Action |
|----------|-------------|-----------|--------|
| **Direct Contradiction** | New finding explicitly disproves existing assumption | Compare new findings against register | Invalidate, trace dependents, flag per severity |
| **Feasibility Cliff** | Constraint makes current approach impossible | Mode 3 output contains hard blockers | Flag critical, recommend revisiting Mode 2 or Mode 1 |
| **Unaccounted Decision Authority** | Stakeholder with veto power surfaces late | New stakeholder with authority over implementation | Flag as critical validation point, recommend revisiting Mode 1 |
| **High-Impact Assumption Collapse** | High Impact / Guessed assumption invalidated | Status transition to invalidated | Automatic backward transition recommendation |

**Deferred to Phase 2:** Scope Change, Cluster Degradation.

### 4.7 Proactive Stakeholder Surfacing

Uses domain knowledge patterns AND OrgContext to identify overlooked stakeholders. Stakeholder assumptions are flagged for validation earlier and more aggressively than other types.

### 4.8 Document Skeleton Management

Managed entirely through granular tool calls. Modes call specific update functions when they complete. User can request artifact generation at any point via `generate_artifact()`.

### 4.9 Unstructured Document Ingestion

The system accepts messy, unformatted text pastes from Confluence, SharePoint, or other sources. When a user pastes raw document text, the system:

1. Parses for relevant information related to the current analysis
2. Extracts key facts, prior decisions, and stakeholder positions
3. Updates assumptions from "guessed" to "informed" where the document provides evidence
4. Flags any contradictions with existing assumptions

**The research handoff is explicitly optional:**
> "These searches would strengthen the analysis, but I can proceed with what we have. The assumptions will stay at 'Guessed' confidence until validated."

This prevents user drop-off from research friction while making the tradeoff transparent.

---

## 5. Dual-Tone Output Structure

All analytical outputs use a two-section structure: blunt analysis for the PM, diplomatic scripts for stakeholder conversations.

### Structure

**Analysis Section** (blunt, direct, for the PM):
Contains the honest assessment of what's going on. Names risks directly, identifies political dynamics, flags where the user might be wrong. This is NOT hidden or collapsible — it's the primary content.

Example:
> "KPM has been pushing digital twins for years without shipping. The risk is this is a solution-in-search-of-a-problem driven by leadership attachment, not validated customer need. If campaign managers are currently allocating budget effectively through experience, the ROI case for sophisticated pre-campaign prediction is weaker than it appears."

**Stakeholder Questions Section** (diplomatic, ready to use in meetings):
Contains specific questions the PM can ask stakeholders, framed to open thinking rather than challenge it. Each question maps to a specific risk or assumption from the analysis section.

Example:
> **To validate whether the problem is real (maps to analysis above):**
> "What's the closest the campaign team has gotten to estimating performance before launch? Where did that break down?"
>
> "If we had perfect pre-campaign predictions, what would you do differently in your planning process?"

### Rules
- **Never interleave** blunt and diplomatic versions in the same narrative flow
- Analysis section comes first (understanding), stakeholder questions come second (action)
- Each diplomatic question should map to a specific finding in the analysis
- Blunt analysis is NOT hidden — it's the primary content the PM needs to understand the situation

---

## 6. Transition Logic

### Forward Transitions (Natural Progression)

| From | Natural Next | Trigger |
|------|-------------|---------|
| Mode 1 (Discover) | Mode 4 (Value) or Mode 3 (Constraints) | Problem well-defined; need sizing or limitation check |
| Mode 2 (Solution) | Mode 3 (Constraints) or Mode 4 (Value) | Solution articulated; need feasibility or value |
| Mode 3 (Constraints) | Mode 2 (Solution) or Mode 1 (Discover) | Constraints mapped; evaluate within constraints or reframe |
| Mode 4 (Value) | Mode 5 (Prioritize) or Mode 2 (Solution) | Value sized; compare alternatives or evaluate approach |
| Mode 5 (Prioritize) | Artifact Generation | Prioritization complete; need deliverable |

### Backward Transitions (Triggered by Conflicts)

| Trigger | Recommendation |
|---------|---------------|
| High Impact assumption invalidated | "A core assumption just broke. I recommend revisiting [originating mode]." |
| Feasibility cliff discovered | "Current approach appears blocked. Consider revisiting problem framing or solution approach." |
| New stakeholder with decision authority | "This stakeholder wasn't part of original framing. Recommend revisiting Discover & Frame." |

### Behavior
- Always suggest, never force
- Provide reasoning for every transition recommendation
- After mode completion, always suggest next mode with rationale

---

## 7. OrgContext — Dynamic Enrichment

OrgContext is built dynamically from two sources, not maintained as a static file:

### Two Layers

| Layer | Source | When Populated | Required? |
|-------|--------|----------------|-----------|
| **Public context** | Model's own knowledge about the company, industry, competitive landscape, recent events | Turn 1 (auto), re-enriched if domain shifts | Yes — always attempted |
| **Internal context** | User-provided details about team dynamics, internal vocabulary, political realities | When user offers it (optional, non-blocking) | No — system proceeds without it |

### Structure (Same as Before)

```markdown
## Organizational Map
- [Team]: [Responsibilities]. [Key relationships/dependencies].
  - Decision authority: [What they can approve/veto]

## Domain Vocabulary
- [Term]: [What it means in THIS organization]

## Historical Patterns
- [Pattern]: [What happened and what it teaches]
```

### Enrichment Flow

**Turn 1 enrichment (always runs, no external search):**
- Extract company/organization and domain from the user's first message
- Use the model's own knowledge to generate public context: company overview, organizational structure, known strategic context, industry dynamics relevant to the stated problem
- Store in session state via tool call
- Offer the user a chance to supplement with internal context (non-blocking — don't re-ask if declined)

**Progressive re-enrichment (rare, Phase A triggered):**
- Phase A evaluates whether the problem domain has materially shifted from what's captured
- "Materially different" means: different business function (marketing → logistics), different stakeholder ecosystem, or different competitive context. NOT just new details within the same domain.
- If shift detected AND enrichment count < 3: Phase B generates updated public context for the new domain
- Appends to public context (doesn't replace)

### Why Not Web Search?
v1 uses Claude's model knowledge instead of a search API. Claude already knows a lot about major companies — org structure, competitive dynamics, historical events. This is free (no extra API calls, no third-party dependency). For work use, a search API can be bolted on later — the architecture supports it via the same `update_org_context` tool.

### Maintenance
- Public context is auto-generated, not user-maintained
- Internal context grows as the user provides details during conversation
- System can suggest additions based on discoveries during analysis

---

## 8. Design Principles (System-Wide)

### Progressive Disclosure
- 2-3 questions per turn maximum
- One cognitive task per turn
- Micro-synthesis every 2-3 turns
- Full analysis available on request, not dumped unprompted

### Density-to-Risk (NOT Tone-Matching)
System depth is driven by assumption risk level, not user mood. High-risk unvalidated assumptions get deep probing regardless of how brief or action-oriented the user's input is. System stays concise either way.

### Generative, Not Blocking
Modes make soft guesses (marked with ⚠️) and proceed. Guesses tracked in assumption register with impact and confidence ratings.

### Concrete Decision Criteria
Every mode output includes specific proceed/don't-proceed criteria. No "proceed with caution."

### Dual-Tone Output
Blunt analysis for the PM (primary content) + diplomatic stakeholder scripts (action items). Never interleaved.

### Value Labeling
Mode 4 outputs always labeled "Projected Opportunity (Unadjusted)" to prevent anchoring bias.

---

## 9. Data Flow Summary

```
User Message
    │
    ▼
┌─────────────────────────┐
│ PHASE A: Think (Light)  │ ◄── Assumption Register (read via get_assumptions)
│                         │ ◄── OrgContext (persistent)
│  - Check for conflicts  │
│  - Determine next action│
│  - Select probe/mode    │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ PHASE B: Act (Heavy)    │ ◄── Mode Knowledge Base (injected if entering mode)
│                         │
│  Generate response      │
│  Call state tools:      │
│  - register_assumption()│
│  - update_problem_      │
│    statement()          │
│  - add_stakeholder()    │
│  - etc.                 │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ POST-TURN               │
│  - Scan for conflicts   │
│  - Flag at-risk         │
│    assumptions          │
│  - Suggest next mode    │
└─────────────────────────┘
```

---

## 10. What's NOT in This Spec (Deferred)

| Item | Reason for Deferral |
|------|---------------------|
| Agent-driven automatic looping | Phase 2 — user-driven looping sufficient |
| Scope Change conflict detection | Phase 2 — hard to detect reliably |
| Cluster Degradation detection | Phase 2 — requires statistical reasoning |
| Multi-hop assumption propagation | Phase 2 — single-level tracking sufficient |
| Automated Confluence/SharePoint integration | Phase 2 — manual paste + optional search queries for now |

---

## 11. Next Steps

1. ✅ **Orchestrator Specification** — COMPLETE (this document)
2. ✅ **Mode 1: Discover & Frame** — COMPLETE (mode1-discover-frame-spec.md)
3. 🔲 **Mode 2: Evaluate Solution** — Next
4. 🔲 **Mode 3: Surface Constraints**
5. 🔲 **Mode 4: Size & Value**
6. 🔲 **Mode 5: Prioritize & Sequence**
7. 🔲 **Master Claude Code Spec** — After all modes complete
8. 🔲 **OrgContext Template** — For 8451-specific context

---

*Last updated: February 2026*
*Status: FINALIZED v2.1 (post spec review)*
