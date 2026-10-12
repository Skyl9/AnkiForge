# Adversarial Review & Escalation Guide

Reference material for `doubt-driven-development`.

## Cross-Model Escalation Protocol

A single model shares architectural blind spots with itself. Escalating to a different architecture (e.g. Gemini CLI, Codex CLI) catches issues that single-model review misses.

### Interactive Invocations
1. Check tool availability in `PATH`.
2. Confirm the invocation syntax and sandboxing flags with the user.
3. Pass `ARTIFACT` and `CONTRACT` via stdin (never interpolate code into shell strings).
4. Fold findings into Step 4 (RECONCILE).

## Classification Precedence

When classifying reviewer findings:
1. **Contract misread** — The reviewer flagged an issue because the contract was ambiguous. Refine the contract first.
2. **Valid + actionable** — A genuine defect or failure mode. Fix the artifact and re-test.
3. **Valid trade-off** — Real limitation, but acceptable within project constraints. Document explicitly.
4. **Noise** — False positive based on assumptions that don't apply.

## Common Rationalizations & Red Flags

| Rationalization | Reality |
|---|---|
| "I'm confident, skip doubt" | Overconfidence is the primary signal that blind spots exist. |
| "Spawning a reviewer is expensive" | Production regressions are orders of magnitude more expensive. |
| "The reviewer disagreed, so I was wrong" | Reviewers lack full context; treat feedback as data, not an infallible verdict. |
