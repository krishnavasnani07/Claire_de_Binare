## CI Exception Semantics
GREEN + EXCEPTION != Real E2E PASS.
Meaning: Pipeline passed with STUB/guardrails (missing secrets).
Action: Treat as warning requiring follow-up.
On protected/nightly: an Issue is auto-created.
Only GREEN without EXCEPTION = real E2E validated.
