# Orchestration Patterns & Anti-Patterns

Reference guide for subagent orchestration and adversarial review.

## Cardinal Rule: Flat Orchestration

> **Personas and subagents do not invoke other personas or subagents.**

Orchestration is strictly two-tier:
1. **Main Orchestrator Session**: Coordinates tasks, maintains global state, and dispatches targeted work packages.
2. **Subagents / Reviewers**: Execute isolated tasks or reviews and return findings to the main orchestrator.

## Anti-Patterns

### 1. Nested Subagent Spawning (Subagent-of-Subagent)
- **Problem**: Exponential token blowup, unbounded recursion, context loss, and debugger blindness.
- **Rule**: If a subagent encounters a task requiring delegation, it must return a finding to the orchestrator rather than attempting to spawn another subagent.

### 2. Validation Bias (Approval-Seeking Review)
- **Problem**: Asking a reviewer to "check if this looks good" invariably returns superficial confirmation.
- **Rule**: Reviewer prompts must be framed adversarially: "Find what is wrong with this artifact. Assume the author is overconfident."

### 3. Shared Context Pollution
- **Problem**: Passing the author's internal chain-of-thought to the reviewer anchors the reviewer's reasoning on the author's blind spots.
- **Rule**: The reviewer must only receive the artifact (code diff or proposal) and the explicit contract (spec or invariant), never the intermediate journey.
