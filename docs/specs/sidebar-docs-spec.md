# Project Forge — Sidebar Documentation Tabs Specification

## Purpose
Add two reference sections to the Forge sidebar so that users can understand how to use the tool (Quick Start) and how it works under the hood (How It Works). Quick Start is a short sidebar expander. How It Works is a button that opens a wide dialog overlay to avoid the "scroll of death" in the narrow sidebar.

**Why now:** Before sharing with the team for testing. Users need to understand what Forge expects from them and why it asks the questions it does.

---

## 1. UI Layout

```
Forge
├── Project selector + Create New Project
├── Current: **Project Name**
├── ─────────────── (divider)
├── 📖 Quick Start Guide          ← NEW (st.expander, collapsed by default)
├── 🔍 How Forge Works            ← NEW (st.button → opens @st.dialog)
├── ─────────────── (divider)
├── Active Mode: Mode 1
├── Turn: 6
├── Assumptions (14)
│   └── ...
```

**Quick Start** uses `st.expander()` — it's short enough to fit in the sidebar without pushing important elements off screen.

**How It Works** uses `st.button()` that triggers a `@st.dialog("How Forge Works", width="large")`. This opens a wide, center-screen overlay that's readable and doesn't interfere with the sidebar's real-time elements (Active Mode, Turn, Assumptions).

**Fallback:** If `@st.dialog` is not available (requires Streamlit 1.35+), fall back to `st.expander` in the sidebar and log a warning.

---

## 2. Quick Start Guide — Content (sidebar expander)

```markdown
### Getting Started

Forge is a PM discovery partner. It doesn't generate solutions — it helps you 
think through problems systematically by asking the questions experienced PMs ask.

### Before Your First Session

**Set up your project context** to get sharper analysis:

1. Open your project's `context.md` file:  
   `~/Documents/forge-workspace/projects/<your-project>/context.md`

2. Add organizational context that Forge should know:
   - **Team structure** — who's on the team, what they do
   - **Key stakeholders** — decision-makers, pain holders, people who 
     benefit from the status quo
   - **Systems & tools** — what the team works with daily
   - **Terminology** — acronyms and internal language
   - **Current priorities** — what leadership cares about right now
   - **Known challenges** — politics, constraints, past failures

3. The more context you provide upfront, the less Forge has to guess.
   You can update `context.md` anytime — Forge re-reads it every turn.

### During a Session

- **Start with the problem, not a solution.** If you come in with 
  "we need to build X," Forge will probe whether X is the right thing 
  to build. That's by design.

- **Answer the "why" questions.** When Forge asks "why now?" or 
  "who benefits from the status quo?" — these aren't filler. They're 
  the questions that separate good discovery from superficial analysis.

- **Paste supporting documents.** Meeting notes, research summaries, 
  stakeholder feedback — Forge will extract relevant context and 
  register assumptions from them.

- **Watch the sidebar.** Assumptions accumulate as you talk. 
  High-impact + low-confidence assumptions (🔴) are the ones that 
  need validation before you commit to a direction.

- **Ask for the brief when ready.** When you feel the problem is well 
  framed, ask Forge to generate the Problem Brief. If the skeleton 
  fields are empty, Forge will tell you what's missing.

### What Forge Produces

- **Mode 1 → Problem Brief:** Structured problem statement, stakeholders, 
  assumptions ranked by risk, success metrics, proceed/don't-proceed criteria.

- **Mode 2 → Solution Evaluation:** Risk assessment across 4 dimensions, 
  validation plan for the riskiest assumption, go/no-go recommendation.

### Tips

- Keep messages focused. Long document pastes work, but break your 
  own thoughts into digestible pieces.
- If Forge seems stuck or gives an empty response, type "continue" — 
  it may have hit an output limit.
- You can switch between projects using the dropdown above. Each 
  project has its own conversation, context, and assumptions.
```

---

## 3. How It Works — Content (dialog overlay)

```markdown
### What Problem Forge Solves

When a PM opens a blank AI chat and says "help me think through this 
problem," the AI gives a generic response. It has no framework for what 
good discovery looks like.

Forge is different because it has an opinionated methodology baked in — 
it knows what questions experienced PMs ask, in what order, and why. The 
methodology is drawn from practitioners like Teresa Torres, Marty Cagan, 
and Rob Fitzpatrick, and from documented practices at companies like 
Stripe, Airbnb, and Spotify.

---

### The Two-Phase Loop

Every time you send a message, two things happen before you get a response.

**Phase A — Strategic Routing**  
A fast, lightweight call that reads the conversation and decides what to 
do next. It considers: which probes have already fired, what assumptions 
are registered, whether it's time to synthesize, whether something you 
said conflicts with earlier information.

Phase A doesn't talk to you. It produces an internal routing decision — 
like "continue probing, focus on stakeholder dynamics" or "time for a 
micro-synthesis" or "enter Mode 1."

**Phase B — Execution & Response**  
A heavier call that takes Phase A's routing decision plus the full 
conversation history, organizational context, assumption register, and 
document skeleton — and generates the response you see.

**Why this matters:** Phase A keeps Phase B honest. Without it, the 
model would just react to your last message. With it, every response is 
informed by a strategic assessment of where the conversation is, what's 
been covered, and what's still missing.

---

### Mode 1: Discover & Frame

Mode 1 activates when Forge has enough context to begin structured 
problem analysis. Its job is to help you frame the problem clearly 
before anyone starts building solutions.

#### The 7 Diagnostic Probes

Each probe has trigger conditions (when to fire), specific questions, 
and completion criteria (how to know when enough signal has been gathered).

**Probe 1 — Solution-Problem Separation**  
*What it asks:* Is the user describing a solution or a real problem?  
*Why it matters:* Most people come in with "we need to build X" when 
the real question is "what problem are we solving?" This probe peels 
back the solution to find the underlying need.  
*What it sounds like:* "You've described the solution clearly — but 
what's the specific pain point or unmet need that's driving this?"

**Probe 2 — Temporal Trigger**  
*What it asks:* Why now? What changed?  
*Why it matters:* If there's no forcing function — no deadline, no 
market shift, no escalating cost — the problem may not be urgent enough 
to act on. This reveals whether there's real momentum or just 
organizational habit.  
*What it sounds like:* "This seems like it's been a challenge for a 
while. What's changed recently that makes this worth tackling now?"

**Probe 3 — Stakeholder Mapping**  
*What it asks:* Who has decision authority? Who feels the pain? Who 
benefits from the status quo? Who needs to execute?  
*Why it matters:* The status quo beneficiary question is the one most 
PMs skip — and it's the one that kills projects. If someone powerful 
benefits from things staying the same, your solution faces resistance 
you haven't accounted for.  
*What it sounds like:* "Who would actually be worse off if this problem 
got solved? Whose workflow or authority depends on the current setup?"

**Probe 4 — Root Cause Depth**  
*What it asks:* Is the stated problem the real problem, or a symptom?  
*Why it matters:* Surface-level problem statements lead to surface-level 
solutions. This probe keeps pushing deeper — "why does that happen?" — 
until you hit something structural.  
*What it sounds like:* "You mentioned measurement variability is 
eroding trust. But is variability the root cause, or is it that the 
methodology changed and wasn't communicated clearly?"

**Probe 5 — Success Criteria Clarity**  
*What it asks:* How would you know this worked? What would you measure? 
What's the anti-metric?  
*Why it matters:* Without clear success criteria, you can't evaluate 
solutions, prioritize work, or know when to stop. The anti-metric — the 
thing that tells you you're making things worse — is particularly 
important for avoiding unintended consequences.  
*What it sounds like:* "If this initiative succeeds, what specific 
number changes? And what's the thing we should watch to make sure we're 
not creating a new problem?"

**Probe 6 — Constraint Archaeology**  
*What it asks:* Which constraints are real technical limitations and 
which are policy decisions nobody's questioned?  
*Why it matters:* Organizations accumulate constraints over time. Some 
are load-bearing (remove them and things break), some are vestigial 
(they made sense years ago but nobody's revisited them). This probe 
separates the two, revealing hidden flexibility in the solution space.  
*What it sounds like:* "The minimum 12 offers requirement — is that a 
printer limitation, a contractual commitment, customer research, or 
something else? I want to understand which constraints we're working 
within versus which ones we could challenge."

**Probe 7 — Prior Art & Organizational Memory**  
*What it asks:* Has this been tried before? What happened? Why?  
*Why it matters:* Organizations repeat failures when institutional 
memory is poor. A project that failed in 2021 may be viable now under 
different conditions — but only if you understand why it failed then.  
*What it sounds like:* "Has anyone attempted to address this before? 
What happened, and what's different now?"

#### The 8 Domain Patterns

These are recurring organizational dynamics that experienced PMs 
recognize. When a pattern's trigger conditions are met in the 
conversation, Forge incorporates that lens into its analysis.

**Pattern 1 — Analytics-Execution Gap**  
The organization can diagnose problems through data but struggles to 
ship solutions. Dashboards show what's wrong, but problems persist 
quarter after quarter. The bottleneck isn't insight — it's execution 
capacity, organizational authority, or the gap between people who see 
the data and people who can act on it.

**Pattern 2 — Metric Fixation**  
The team is optimizing a metric that's disconnected from real value. 
The number goes up, but customers aren't happier and the business isn't 
improving. This pattern probes the causal chain — does improving this 
metric actually cause the outcome you care about?

**Pattern 3 — Stakeholder Misalignment**  
Different stakeholders define the problem or success differently, but 
the disagreement is implicit. "Alignment meetings" keep happening 
without resolution. This pattern surfaces the specific dimensions of 
disagreement so they can be resolved before delivery.

**Pattern 4 — Solution Inertia**  
A solution direction has been chosen before the problem was framed, and 
organizational momentum makes it hard to revisit. The solution is 
described with high specificity while the problem remains vague. This 
pattern separates solution from problem so both can be evaluated.

**Pattern 5 — Organizational Scar Tissue**  
Past failures are creating risk aversion that may no longer be 
justified. "We tried that before" without evidence that current 
conditions match historical ones. This pattern probes what specifically 
failed and whether those conditions still apply.

**Pattern 6 — Infrastructure Debt as Feature Requests**  
What looks like a product problem is actually an infrastructure, data, 
or platform problem in disguise. The proposed solution involves building 
new capabilities when existing ones should work but don't. This pattern 
probes whether the root cause is a missing capability versus a broken 
existing one.

**Pattern 7 — Proxy User Problem**  
The team is solving for a proxy user (internal stakeholders, account 
managers) rather than the actual end user. The "customer need" is 
actually an internal operational pain point. This pattern probes whether 
the problem has been validated with actual users or only through 
internal intermediaries.

**Pattern 8 — Premature Scaling**  
The team is trying to scale something that hasn't been validated at 
small scale. Large investment is planned but there's no evidence the 
core value proposition works for even a handful of users. This pattern 
probes for small-scale evidence before recommending scale investment.

---

### The Structured State

As the conversation progresses, Forge builds three things behind the 
scenes:

**The Assumption Register**  
Every time something is assumed but not validated, Forge logs it with: 
what the assumption is, the confidence level (validated / informed / 
guessed), the impact level (high / medium / low), and what depends on 
it. High-impact, low-confidence assumptions get flagged with 🔴. If an 
assumption is invalidated, anything that depends on it automatically 
gets flagged as at-risk. This is the thing most PM conversations never 
do — track what you're assuming versus what you know.

**The Document Skeleton**  
As Forge learns about the problem, it fills in a structured brief: 
problem statement, target audience, stakeholders, success metrics, 
proceed/don't-proceed criteria. This is built turn by turn — not 
generated at the end. Fields get revised as the picture gets clearer.

**The Routing Context**  
Forge tracks which probes have fired, which patterns have triggered, 
and maintains a rolling conversation summary. This prevents re-asking 
covered questions and ensures every important angle gets explored.

---

### Mode 2: Evaluate Solution

Once you have a clear problem frame from Mode 1, Mode 2 evaluates a 
proposed solution against it.

#### What It Assesses

Mode 2 uses Marty Cagan's four risk dimensions:

**Value Risk** — Will anyone use it? Is the problem painful enough 
that the solution is worth adopting? Is there evidence of demand beyond 
stakeholder assertions?

**Usability Risk** — Can users figure it out? Is the solution 
accessible to the target audience? Does it fit into existing workflows?

**Feasibility Risk** — Can we build it? Do we have the technical 
capability, data, and infrastructure? What are the dependencies and 
unknowns?

**Viability Risk** — Should we build it? Does it align with business 
strategy? Can we sustain it operationally? What's the cost structure?

#### What It Produces

- Risk assessment across all 4 dimensions with evidence for and against
- Identification of the riskiest assumption
- A recommended validation approach (painted door test, concierge MVP, 
  technical spike, wizard of oz, prototype)
- A go / conditional go / pivot / no-go recommendation with explicit 
  conditions and dealbreakers

#### Mode 2 Probes

Mode 2 has its own probe set focused on:
- Problem-solution fit (does this solution actually address the root 
  cause identified in Mode 1?)
- Implementation risk (technical complexity, integration challenges, 
  data dependencies)
- Organizational readiness (does the team have capacity and authority 
  to execute?)
- Competitive and market context (is this the right approach given 
  market dynamics?)
- Sustainability (can this be maintained long-term, or is it a 
  one-time effort?)

#### How Mode 2 Connects to Mode 1

Mode 2 inherits the assumption register from Mode 1. Risks identified 
during problem discovery carry forward into solution evaluation. If 
Mode 1 flagged "stakeholder misalignment on success metrics" as a 
high-risk assumption, Mode 2 will factor that into its viability 
assessment.

---

### Why This Matters — What Forge Replaces

Without Forge, a PM opens a blank chat, dumps context, and gets a 
plausible-sounding but shallow response. There's no systematic probe 
coverage, no assumption tracking, no progressive document building, no 
strategic routing.

With Forge:
- The methodology is encoded — you don't have to remember what to ask
- Assumptions are tracked and dependency-chained automatically
- The document builds itself from validated findings
- Strategic routing ensures comprehensive coverage
- You can focus on thinking about the answers instead of remembering 
  the questions
```

---

## 4. Implementation

### New file: `src/pm_copilot/sidebar_docs.py`

Contains two string constants: `QUICK_START_CONTENT` and `HOW_IT_WORKS_CONTENT`.

Must include this warning comment at the top:

```python
# ⚠️ WARNING: The probe and pattern descriptions in this file are user-facing
# documentation. If you update probe/pattern definitions, you must also update
# the corresponding descriptions in mode1_knowledge.py (LLM-facing) and vice versa.
# These are intentionally different versions for different audiences — the knowledge
# base is optimized for LLM consumption, this file is written for PMs.
```

### Modified: `src/pm_copilot/app.py`

```python
from .sidebar_docs import QUICK_START_CONTENT, HOW_IT_WORKS_CONTENT

# In the sidebar, after project management and first divider:

with st.expander("📖 Quick Start Guide"):
    st.markdown(QUICK_START_CONTENT)

if st.button("🔍 How Forge Works", use_container_width=True):
    show_how_it_works()

st.divider()

# Dialog function (defined outside the sidebar block):
@st.dialog("How Forge Works", width="large")
def show_how_it_works():
    st.markdown(HOW_IT_WORKS_CONTENT)
```

**Fallback:** If `@st.dialog` is not available (Streamlit < 1.35), fall back to `st.expander` in the sidebar and log a warning: `logger.warning("st.dialog not available, falling back to sidebar expander for How It Works")`.

---

## 5. Testing

- [ ] Quick Start expander appears in sidebar below project management, above Active Mode
- [ ] Quick Start expands and shows formatted markdown without pushing sidebar elements too far
- [ ] "How Forge Works" button appears in sidebar
- [ ] Clicking the button opens a wide dialog overlay in the center of the screen
- [ ] Dialog content renders correctly (headers, bold, bullet points)
- [ ] Dialog can be closed and sidebar elements remain visible and functional
- [ ] Active Mode, Turn count, and Assumptions remain visible when Quick Start is collapsed
- [ ] No impact on chat area or conversation functionality

---

*Status: SPEC COMPLETE*
*Depends on: Persistence build (complete)*
*Build time: ~15 minutes with Claude Code*
