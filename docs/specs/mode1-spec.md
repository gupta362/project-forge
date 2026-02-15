# Mode 1: Discover & Frame — Full Specification (v2)

## Document Purpose
This is the complete knowledge base and behavioral specification for Mode 1. It defines the diagnostic reasoning, domain-specific patterns, questioning strategies, and output structures that make Mode 1 genuinely expert-level rather than generic PM-101.

**Changelog v2.1 (post spec review):**
- Added "Satisfied when" completion criteria to all 7 diagnostic probes (#10)
- Added timing guidance to all 8 domain patterns (#11)

**Changelog v2:**
- Added dual-tone output structure (blunt analysis + diplomatic stakeholder scripts)
- Added trigger and suppression conditions for ALL domain-specific patterns
- Added new domain patterns from deep research: Monopoly Complacency, Talent Drain, Alternative Profit Pressure, Data Privacy
- Updated tone guidance: density-to-risk, not tone-matching
- Added unstructured document ingestion support
- Added explicit "What This Is NOT About" section in final output

---

## 1. Core Question

**"What's really going on, and is it worth pursuing?"**

Mode 1 activates when:
- User has an unvalidated problem or opportunity
- User mentions a solution without evidence of prior problem validation
- User is exploring a new space and needs to understand it before acting
- User just joined a team/domain and needs to orient (special case)

---

## 2. Failure Modes (What Mode 1 Must Avoid)

| Failure Mode | Description | Prevention |
|-------------|-------------|------------|
| **Accepting the problem as stated** | Takes user's framing at face value | Probe 1 (Solution-Problem Separation) always runs first |
| **Generic discovery questions** | PM-101 questions not specific to the input | Questions must expose assumptions the user doesn't realize they're making |
| **Polished restatement** | Output is cleaned-up input, not genuine discovery | Must identify at least one assumption or edge the user hasn't considered |
| **20-question interrogation** | Too many questions, user disengages | Max 3 per turn, one cognitive task, internal prioritization |
| **Threatening stakeholder investment** | Questions that challenge proposed solutions directly | Diplomatic questioning layer for stakeholder-facing scripts |
| **Circling on low-priority issues** | Stuck on something fixated on, not highest-risk | Internal prioritization engine, redirect when disproportionate |
| **Boy who cried wolf** | Flagging organizational/cultural warnings on every problem | Strict trigger + suppression conditions on all domain patterns |

---

## 3. Diagnostic Reasoning Model

Seven diagnostic probes, applied in priority order. Not every probe fires for every input.

### Probe 1: Solution-Problem Separation (ALWAYS RUNS FIRST)

**Purpose:** Determine whether the user is presenting a problem or an embedded solution, and peel them apart.

**Logic:**
```
IF input contains a specific solution or technical approach:
    → Extract: What PROBLEM does this solution assume exists?
    → Extract: What ASSUMPTIONS about the problem are baked in?
    → Extract: What ALTERNATIVE framings might exist?
    → Surface via density-to-risk (always probe if high-risk, 
      even if user is brief/action-oriented)
    
IF input is a pure problem statement with no embedded solution:
    → Validate: Is this a real problem or an assumed one?
    → Probe for evidence of existence
```

**Example — Digital Twins Input:**
```
Input: "The UCM could benefit from a pre-activation decision 
capability that uses linked digital twins..."

Embedded solution: Linked digital twins (campaign twin + customer twin)
Embedded framing: Pre-campaign measurement
Assumed problem: Can't estimate campaign performance before spending
Unasked questions:
  - What's the current estimation process?
  - Is the gap accuracy, speed, granularity, or trust?
  - Could simpler approaches solve the actual pain?
```

**Satisfied when:**
- The assumed problem is stated separately from the proposed solution
- At least one alternative framing has been surfaced
- Key assumptions baked into the original framing are registered

### Probe 2: "Why Now?" Trigger

**Purpose:** Understand what's driving this problem to the surface right now.

**Key questions to explore:**
- New leader's priorities?
- Recent failure making this visible?
- Competitor doing something similar?
- Conference or vendor pitch inspiration?
- Budget cycle or planning deadline?
- Known issue that's suddenly urgent? Why?

**Why this matters:** If digital twins is being pursued because KPM leadership saw it at a conference, the real problem might be "leadership wants to demonstrate innovation" — different success criteria than "campaigns are underperforming."

**Satisfied when:**
- The driving trigger for "why now" is identified (or confirmed as absent)
- The trigger's implications for success criteria are noted

### Probe 3: Immediate vs. Platform Framing

**Purpose:** Surface whether the problem should be framed as a narrow client need or a broad capability.

**When to activate:** Whenever a problem could serve multiple stakeholders or use cases.

| Framing | Scope | Success Metric | Investment | Risk |
|---------|-------|----------------|------------|------|
| **Immediate** | Specific client/team | Client satisfaction, specific KPI | Lower, faster | Too narrow to reuse |
| **Platform** | Multiple use cases | Reusability, adoption, compounding value | Higher, slower | Over-engineered for immediate need |

**Diplomatic surfacing:** Naturally flattering — "This could be bigger than just [immediate use case]." Forces conscious scope decision without challenging the idea.

**Satisfied when:**
- User has made a conscious scope choice (immediate vs platform) OR scope ambiguity is registered as an assumption

### Probe 4: Store Reality Check (Domain-Specific)

**Purpose:** Detect whether a solution requires store-level behavioral change that hasn't been accounted for.

**⚠️ See Section 8 for trigger and suppression conditions.**

**Satisfied when:**
- Store execution dependency is confirmed or ruled out
- If confirmed: relevant stakeholders are registered

### Probe 5: Status Quo Beneficiaries

**Purpose:** Identify who benefits from the current state and where resistance will come from.

**When to activate:** Especially when:
- Problem has been known for a long time but hasn't been solved
- Solution would change someone's decision-making process
- Solution would make existing manual expertise less valuable

**Key questions:**
- Who currently makes the decisions this solution would automate/inform?
- If someone's judgment is being replaced by data, how will they react?
- Is there an existing tool or vendor this would replace? Who championed it?

**Diplomatic framing:** Never "someone is going to block you." Instead: "Who currently owns this decision, and how do we make sure they see this as empowering rather than threatening?"

**Satisfied when:**
- Status quo beneficiaries are identified OR confirmed as non-existent
- If identified: their likely response is assessed

### Probe 6: Edge Mapping

**Purpose:** Understand boundaries — what causes the problem, what it causes, what's adjacent.

**Four edges:**
- **Upstream (causes):** Data problem? Process? People? Tooling?
- **Downstream (effects):** Bad allocation? Missed revenue? Team frustration? Client churn?
- **Adjacent:** If pre-campaign measurement is broken, is post-campaign also broken? Is targeting the real issue?
- **Temporal:** New or old? If old, why NOW? (Links to Probe 2)

**Satisfied when:**
- At least upstream and downstream edges are mapped
- Adjacent problems are noted if relevant

### Probe 7: Value Hypothesis (Lightweight)

**Purpose:** Rough hypothesis about where value comes from. Gives Mode 4 a starting point.

**Output format:**
> "If this problem is real and solvable, value comes from [X], measured by [Y]. Magnitude depends on [key assumptions]."

**Must include success metrics:**
- Leading indicator (what changes first)
- Lagging indicator (what ultimately proves value)
- Anti-metric (what should NOT get worse)

**Satisfied when:**
- A rough value hypothesis exists with leading, lagging, and anti-metric
- Key assumptions behind the value estimate are registered

---

## 4. Diplomatic Questioning Layer

### Core Principle
**Be blunt with the PM. Be diplomatic for the PM's stakeholder conversations.**

The system generates two versions of key questions:
- **Honest version:** Direct assessment for the PM to understand what's at stake
- **Diplomatic version:** Stakeholder-ready language the PM can use in meetings

### Questioning Strategies

#### Strategy 1: The Outcome Question
Instead of challenging the solution, ask what outcome they want.
- **Honest (to PM):** "Has anyone validated that campaign managers want pre-campaign predictions, or is this driven by leadership who saw digital twins at a conference?"
- **Diplomatic (for stakeholder):** "What would change in your campaign process if you had perfect pre-campaign predictions?"

#### Strategy 2: The Specificity Test
Ask them to apply their idea to a concrete case.
- **Honest (to PM):** "This idea sounds good in theory but may fall apart when applied to a specific campaign. Test it."
- **Diplomatic (for stakeholder):** "If we built this exactly as described, what's the first campaign you'd test it on and what would success look like?"

#### Strategy 3: The "Closest Attempt" Question
Ask about prior attempts without judging.
- **Honest (to PM):** "If this has been proposed before and didn't happen, find out why. That reason probably still exists."
- **Diplomatic (for stakeholder):** "What's the closest you've gotten to this today, and where did it break down?"

#### Strategy 4: The Elevation Frame
Position a challenging question as expanding the opportunity.
- **Honest (to PM):** "The scope is ambiguous. If this stays KPM-only, it might be under-invested. If it's meant to be a platform, you need different sponsorship."
- **Diplomatic (for stakeholder):** "This could be bigger than just KPM — if this works, Kroger's internal marketing could use the same approach. Are you positioning this as a foundational capability?"

#### Strategy 5: The Constraint Surfacing
Frame constraint discovery as ensuring success.
- **Honest (to PM):** "If this requires store-level changes, store ops will likely push back. Find out before you're 3 months in."
- **Diplomatic (for stakeholder):** "For this to deliver full value, what would need to change at the store level? Let's make sure we've got those stakeholders aligned early."

### Anti-Patterns

| Anti-Pattern | Why It Fails | Do Instead |
|-------------|-------------|------------|
| "Have you considered X might not work?" | Defensive stakeholder | Ask outcome questions |
| Listing 5+ risks at once | Overwhelming | Surface highest-risk item only |
| "The research says X" | Lecturing tone | "In similar situations, teams found X. Match your experience?" |
| "You should talk to [team]" | Task assignment feel | "For this to work, [team] needs to be on board. What's your relationship?" |
| Asking questions you know the answer to | Manipulative when discovered | Be transparent: "I suspect X might be a factor — is it?" |

---

## 5. Internal Prioritization Engine

### Prioritization Criteria

Each item scored on:
1. **Decision Impact:** Does different-than-assumed change whether you'd pursue this? (High / Medium / Low)
2. **Current Confidence:** How sure are we? (Validated / Informed / Guessed)
3. **Cost of Being Wrong Late:** Wasted effort if discovered in 3 months vs. now? (High / Medium / Low)

### Priority Logic
```
Surface first:  High impact + Guessed + High cost of late discovery
Surface second: High impact + Informed + needs validation
Hold for later:  Medium/low impact, or already high confidence
```

### Surfacing Rules
- Maximum 1 critical item per turn
- 2-3 lightweight supporting items can be mentioned briefly
- Everything else held for subsequent turns
- Redirect if discussion is circling on lower-priority item

---

## 6. External Research Handoff

### When to Generate Search Queries
After initial context gathering, when Mode 1 has identified assumptions that could be validated with internal documentation.

### Search Query Format
```
RECOMMENDED INTERNAL SEARCHES (optional — I can proceed without these):

1. Search: "[specific query]"
   Purpose: [What assumption it validates]
   What to look for: [Specific things to bring back]

If you find relevant docs, paste the text directly — 
I can work with unformatted content.
```

### Unstructured Paste Support
The system accepts messy, raw text dumps from Confluence/SharePoint. When pasted:
1. Parse for information relevant to current analysis
2. Extract key facts, prior decisions, stakeholder positions
3. Update assumption confidence from "guessed" to "informed" where supported
4. Flag contradictions with existing assumptions

---

## 7. Output Structure

### Turn-by-Turn Pattern

**Turns 1-3:** Questions only (highest priority first, max 3)

**Turns 2-4:** Micro-synthesis + follow-up
> "Here's what I'm understanding so far: [1-2 sentences]. Based on that, [follow-up]."

**Turn ~5:** Research handoff (optional)

**After sufficient context:** Full Problem Frame Document

### Problem Frame Document (Mode 1 Final Output)

Uses dual-tone structure throughout.

```markdown
## Problem Frame

### Problem Statement
[2-3 sentence specific, validated problem statement. NOT a restatement 
of input — genuinely reframed based on discovery.]

### What This Is NOT About
[Explicitly name embedded solutions or framings that were separated out.]
Example: "This is about campaign budget allocation effectiveness, not 
about building digital twins specifically. Digital twins may or may not 
be the right solution — that's for Mode 2."

### Why Now
[What's driving this. Links to Probe 2.]

---

## Analysis (Direct Assessment)

[Blunt, honest analysis for the PM. Names risks directly, identifies 
political dynamics, flags where the user might be wrong.]

### Who Feels This Pain
[Specific people/roles, not "the marketing team"]

### Who Has Decision Authority
[Who can approve, fund, or veto. Includes Store Reality Check if triggered.]

### Who Benefits From Status Quo
[If applicable. Direct assessment of where resistance will come from.]

### Key Assumptions

| # | Assumption | Impact | Confidence | Risk If Wrong |
|---|-----------|--------|------------|---------------|
| A1 | [claim] | High | Guessed | [what changes] |
| A2 | [claim] | High | Informed | [what changes] |
| A3 | [claim] | Medium | Guessed | [what changes] |

### Value Hypothesis
If real and solvable, value comes from [X], measured by [Y].

**Success Metrics:**
- Leading: [what changes first]
- Lagging: [what ultimately proves value]  
- Anti-metric: [what should NOT get worse]

### Edges & Adjacent Problems
- Upstream: [causes]
- Downstream: [effects]
- Adjacent: [related problems that might matter]

### Decision Criteria
**Worth pursuing IF:**
1. [Specific, measurable condition]
2. [Specific, measurable condition]

**Do NOT invest IF:**
1. [Specific, measurable condition]
2. [Specific, measurable condition]

---

## Stakeholder Questions (Ready to Use)

### Must Validate First (High Risk)
[Each question maps to a specific finding in the Analysis section]

**To validate [specific assumption/risk from analysis]:**
> "[Diplomatically framed question]"
> Why this matters: [What changes if the answer is different than assumed]

**To validate [next assumption/risk]:**
> "[Diplomatically framed question]"
> Why this matters: [What changes]

### Good to Clarify (Lower Risk)
> "[Question]"
> "[Question]"

### Validation Experiments
[1-3 concrete, low-cost tests with specific success criteria]

For each:
- What to test
- How to test it
- Success criteria (specific numbers)
- What to do if it fails

---

## Recommended Next Steps

**Validate first (highest risk):**
[Single most important thing to validate before proceeding]

**Internal research recommended (optional):**
[Search queries with purpose — system can proceed without these]

**Suggested next mode:**
[Which mode and why]
```

---

## 8. Domain-Specific Patterns with Trigger/Suppression Conditions

Every pattern has explicit conditions for when it fires and when it stays silent. This prevents "boy who cried wolf" warnings that users tune out.

### Pattern 1: The Analytics-Execution Gap (Store Reality Check)

**Description:** 84.51° builds analytically sophisticated solutions that assume store-level behavioral change. Store operations has constraints not in original framing, limiting value.

**Trigger conditions (fire when ANY are true):**
- Solution would change in-store customer experience
- Solution would change store employee workflows or processes
- Solution would change delivery schedules or logistics
- Solution would change how products are displayed, priced, or promoted
- Solution produces output that store teams need to act on
- Solution assumes consistent store-level execution quality

**Suppression conditions (stay silent when ALL are true):**
- Solution is purely digital/online (no store execution component)
- Solution only affects 84.51° or KPM internal processes
- Solution is analytics/reporting only with no operational change required

**When triggered, register:**
```
type: "stakeholder_dependency"
claim: "Store-level execution can adapt to support this solution"
impact: "high"
confidence: "guessed"
```

**Timing:** Can trigger early — store execution dependency is often visible from the initial problem statement.

### Pattern 2: The Dual-Customer Ambiguity

**Description:** Problems get framed for an immediate client (CPG/KPM) but could be a platform capability serving Kroger broadly. Scope ambiguity leads to under-investment or over-engineering.

**Trigger conditions (fire when ANY are true):**
- Problem involves a capability that could serve both CPG clients and Kroger internal teams
- Problem involves KPM services that have analogs in Kroger's internal marketing
- Solution could become a foundational/reusable capability
- User hasn't explicitly stated the scope (KPM-only vs. Kroger-wide)

**Suppression conditions (stay silent when ALL are true):**
- User has explicitly stated and justified the scope
- Problem is purely internal to one team with no cross-functional applicability
- Problem is operational/tactical with no platform implications

**When triggered, register:**
```
type: "organizational"
claim: "This is scoped to [stated scope] only"
impact: "high"
confidence: "guessed"
```

**Timing:** Can trigger early — scope ambiguity is often visible from the initial framing.

### Pattern 3: Conference-Driven Solution Anchoring

**Description:** Stakeholder saw a technology at a conference or vendor pitch and wants to apply it. Technology becomes the starting point instead of the problem.

**Trigger conditions (fire when ALL are true):**
- User proposes a specific, named technology or methodology (digital twins, GenAI, blockchain, etc.)
- No evidence of prior problem validation in the input
- The technology is trendy/buzzworthy in the current industry landscape

**Suppression conditions (stay silent when ANY are true):**
- User provides evidence that the underlying problem has been validated independently of the technology
- User explicitly states they've evaluated alternatives
- The technology is a well-established, non-buzzworthy tool for the stated problem

**When triggered:** Activate Probe 1 (Solution-Problem Separation) and Probe 2 (Why Now?) with diplomatic framing.

**Timing:** SHOULD trigger early — if present, it fundamentally changes the questioning direction. Do not wait for the final output.

### Pattern 4: Monopoly Complacency Risk

**Description:** 84.51°'s captive data monopoly means CPGs have no alternative for Kroger data access. Solutions may be evaluated against a low internal bar rather than competitive benchmarks.

**Trigger conditions (fire when ALL are true):**
- Success metric is defined as "better than current internal baseline"
- No reference to external benchmarks (Amazon, Walmart, industry standards)
- Solution serves external clients (CPGs) who could compare to competing platforms

**Suppression conditions (stay silent when ANY are true):**
- User has already defined competitive benchmarks
- Solution is purely internal (no external client comparison)
- User explicitly acknowledges the competitive landscape

**When triggered:**
- **Honest (to PM):** "Is the bar 'better than what we have' or 'competitive with what Amazon/Walmart offer'? CPGs are comparing KPM to those platforms. If we're only beating our own low bar, that's not a defensible position."
- **Diplomatic (for stakeholder):** "How are our CPG partners currently evaluating campaign measurement across their retail media investments? What benchmarks would make this capability stand out?"

**Timing:** Usually triggers mid-conversation — requires enough context to assess success metric framing.

### Pattern 5: Talent/Resource Dependency Risk

**Description:** 84.51° faces talent challenges (below-market comp, low morale, attrition). Solutions requiring specialized, long-term human investment face execution risk.

**Trigger conditions (fire when ALL are true):**
- Solution requires custom model development or maintenance by specialized roles
- Project timeline exceeds 12 months with specialized skill dependencies
- Solution creates single-points-of-failure around specific people or small teams

**Suppression conditions (stay silent when ANY are true):**
- Solution uses existing, maintained platforms/tools
- Solution requires only short-term specialized work (< 6 months)
- Solution has clear handoff path to less specialized maintenance
- User has already addressed staffing/resourcing plan

**When triggered, register:**
```
type: "organizational"
claim: "Specialized talent will be available and retained for project duration"
impact: "medium"
confidence: "guessed"
```

**Timing:** Usually triggers mid-to-late — requires solution specificity to assess skill dependencies.

### Pattern 6: Alternative Profit Framing Distortion

**Description:** KPM/alternative profit is ~30% of Kroger's operating profit. Problems tend to get framed in revenue terms even when the real need is operational or customer-experience driven.

**Trigger conditions (fire when ALL are true):**
- Problem is framed primarily in terms of revenue growth or alternative profit
- No mention of operational efficiency or customer experience dimensions
- The underlying problem COULD be framed as an operational or CX improvement

**Suppression conditions (stay silent when ANY are true):**
- Problem genuinely IS about revenue/monetization
- User has already considered non-revenue dimensions
- Problem has no plausible operational or CX framing

**When triggered:**
- **Honest (to PM):** "This is being framed as a revenue play, but is the real problem about campaign effectiveness for the end customer? If you only measure revenue impact, you might build something that maximizes KPM billing but doesn't actually improve campaign outcomes."
- **Diplomatic (for stakeholder):** "Beyond the revenue impact, how would this change the experience for the end shopper? Understanding both dimensions helps build a stronger investment case."

**Timing:** Can trigger early — revenue-only framing is often visible from the initial problem statement.

### Pattern 7: Data Privacy as Hidden Constraint

**Description:** Household-level data usage faces increasing scrutiny. Legal review can significantly delay or constrain solutions.

**Trigger conditions (fire when ANY are true):**
- Solution involves household-level or individual-level targeting/profiling
- Solution involves sharing behavioral data with external partners
- Solution creates new data linkages between previously separate datasets
- Solution involves personalization that could be perceived as surveillance

**Suppression conditions (stay silent when ALL are true):**
- Solution uses only aggregated/anonymized data
- Solution operates within existing, already-approved data usage patterns
- User has confirmed legal/privacy review is already underway

**When triggered, register:**
```
type: "stakeholder_dependency"
claim: "Solution can use household-level data without additional privacy/legal review"
implied_stakeholders: ["legal", "privacy_team"]
impact: "medium"
confidence: "guessed"
```

**Timing:** Usually triggers mid-conversation — requires enough solution detail to assess data usage patterns.

### Pattern 8: Post-Ocado Capital Aversion

**Description:** Kroger wrote down $2.6B on Ocado automated fulfillment. Large capital-intensive infrastructure bets face a higher bar.

**Trigger conditions (fire when ALL are true):**
- Solution requires significant new infrastructure investment
- Solution is capital-intensive (not just OpEx/headcount)
- Solution involves automation or new technology platforms at scale

**Suppression conditions (stay silent when ANY are true):**
- Solution leverages existing infrastructure
- Investment is primarily OpEx (people, software licenses)
- Solution is a small pilot/POC, not a scaled infrastructure bet
- User has already secured capital commitment

**When triggered:**
- **Honest (to PM):** "After the $2.6B Ocado write-down, any capital-intensive infrastructure proposal faces extreme scrutiny. Frame this as a pilot with clear stage-gates, not a big bet."
- **Diplomatic (for stakeholder):** "Given current investment priorities, how would you envision the rollout path? A phased approach with clear validation checkpoints at each stage?"

**Timing:** Usually triggers late — requires understanding of solution's investment profile.

---

## 9. Document Skeleton Updates (via Tool Calls)

When Mode 1 completes, it calls:

```python
update_problem_statement("Campaign budget allocation at KPM relies on...")
update_target_audience("Campaign managers at KPM who allocate budgets...")

add_stakeholder("Store Operations", type="execution_dependency", 
                notes="Must validate if solution requires store-level changes")
add_stakeholder("KPM Leadership", type="decision_authority",
                notes="Sponsoring digital twins approach")
add_stakeholder("Senior campaign planners", type="status_quo_beneficiary",
                notes="Currently own budget decisions through experience")

update_success_metrics(
    leading="Campaign managers report using pre-campaign estimates in planning",
    lagging="Measurable improvement in campaign ROI vs. historical baseline",
    anti_metric="Campaign launch timelines should not increase"
)

add_decision_criteria("proceed_if", "Campaign managers confirm budget allocation is a pain point")
add_decision_criteria("proceed_if", "Current estimation gap is accuracy, not just process/trust")
add_decision_criteria("do_not_proceed_if", "Campaign managers are satisfied with current process")
add_decision_criteria("do_not_proceed_if", "Store operations cannot support execution changes")
```

---

## 10. Assumption Register Updates (via Tool Calls)

Example calls for the digital twins case:

```python
register_assumption(
    claim="Campaign budget allocation is suboptimal and improvable through better prediction",
    type="value",
    impact="high",
    confidence="guessed",
    basis="Implied by user's problem statement",
    surfaced_by="Mode 1: Probe 1",
    recommended_action="Validate with campaign managers"
)

register_assumption(
    claim="This is scoped to KPM only, not a platform capability",
    type="organizational",
    impact="high",
    confidence="guessed",
    basis="User described in KPM context",
    surfaced_by="Mode 1: Probe 3",
    recommended_action="Clarify scope with leadership"
)

register_assumption(
    claim="Store-level execution can support campaign changes driven by predictions",
    type="stakeholder_dependency",
    impact="high",
    confidence="guessed",
    basis="Domain pattern: analytics-execution gap",
    surfaced_by="Mode 1: Probe 4",
    implied_stakeholders=["store_operations"],
    recommended_action="Validate with store operations"
)

register_assumption(
    claim="Household-level data usage for campaign twins passes privacy review",
    type="stakeholder_dependency",
    impact="medium",
    confidence="guessed",
    basis="Domain pattern: data privacy constraint",
    surfaced_by="Mode 1: Pattern 7",
    implied_stakeholders=["legal", "privacy_team"],
    recommended_action="Confirm with legal before detailed solution design"
)
```

---

## 11. What Mode 1 Does NOT Do

| Activity | Where It Happens |
|----------|------------------|
| Full valuation / opportunity sizing | Mode 4: Size & Value |
| Solution evaluation | Mode 2: Evaluate Solution |
| Constraint deep-dive | Mode 3: Surface Constraints |
| Prioritization across options | Mode 5: Prioritize & Sequence |
| Technical feasibility assessment | Mode 2 or Mode 3 |

---

*Status: COMPLETE v2.1 (post spec review)*
*Depends on: Orchestrator Specification v2*
*Next: Mode 2 (Evaluate Solution)*
