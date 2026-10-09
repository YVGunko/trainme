# AGENTS.md

Instructions for coding agents working in this repository.

## 1. Before changing code

* Read the relevant existing code before making changes.
* Inspect the repository structure and existing configuration before introducing new files, dependencies, patterns, or services.
* Do not guess file paths, APIs, library methods, database fields, or existing behavior.
* If required behavior cannot be established from the repository, tests, or authoritative documentation, stop and state the uncertainty.
* State material assumptions before implementing ambiguous behavior.

## 2. Scope

* Implement only what is required for the requested task.
* Prefer the smallest change that correctly solves the problem.
* Do not perform unrelated refactoring.
* Do not rename, move, or rewrite working code without a concrete reason.
* Do not add speculative features or abstractions for future use.
* Do not introduce a new framework, service, or dependency when the existing stack can solve the problem.
* Keep adjacent issues separate from the requested change.

## 3. Architecture

The application has a web interface and a Python backend/service layer.
Garmin Connect integration is isolated behind an internal Garmin adapter.
Application/domain code must not depend directly on the Garmin client library.
Garmin-specific code belongs in the Garmin integration layer.
Do not spread Garmin API details, authentication details, request formats, or response structures through unrelated application code.
The current Garmin implementation uses the unofficial `python-garminconnect` library.
Keep the Garmin integration replaceable. Do not design the rest of the application around private Garmin API implementation details.

## 4. Data

PostgreSQL is the application system of record.
Do not introduce another production database unless explicitly requested.
Preserve source Garmin data where practical so that normalized application data can be rebuilt when necessary.
Use stable external Garmin identifiers for synchronization and enforce idempotency at the database level where appropriate.
Do not silently discard existing historical data when changing schemas or synchronization logic.
Database schema changes must include the corresponding migration.

## 5. Garmin

Garmin authentication data and tokens are server-side secrets.
Never:

* commit Garmin credentials or tokens;
* expose Garmin tokens to the browser;
* log authentication headers, cookies, access tokens, or refresh tokens;
* hard-code Garmin credentials.

Do not assume undocumented Garmin behavior.
When Garmin behavior is relevant to a change, verify it against the installed library source, tests, or current authoritative documentation.
Do not replace the Garmin client library without a concrete requirement.

## 6. Domain logic

Training logic is application/domain logic.
Do not invent physiological rules while implementing unrelated features.
Do not silently change training rules because an implementation appears simpler.
Training decisions must be represented in deterministic, testable code where possible.
LLM output must not bypass application validation or domain constraints.

## 7. AI

Treat LLM output as untrusted input.
Validate structured LLM output before using or persisting it.
Do not allow an LLM to directly construct or send Garmin API requests.
AI-generated workouts must pass the application's workout validation before being sent to Garmin.
Do not hard-code provider-specific LLM behavior into unrelated domain logic.

## 8. Tests

Preserve existing tests.
When behavior changes, update or add tests that protect the changed behavior.
For a bug fix, prefer a regression test that fails before the fix and passes after it.
Tests should verify behavior, not implementation details.
Do not add tests merely to increase coverage.
Prefer the narrowest relevant test during development.
After implementation, run the relevant validation commands.
If full validation is impractical, run the narrowest useful checks and state what was not verified.
If a pre-existing test or build failure is encountered, distinguish it from failures caused by the current change.

## 9. External integrations

Do not make real external-service calls in ordinary unit tests.
Use fixtures, mocks, or test doubles for Garmin and other external services.
Integration tests may use real services only when the test explicitly requires them and the repository already provides the required mechanism.
Never put real credentials or tokens into tests or fixtures.

## 10. Errors and security

Do not silently swallow errors.
Follow the existing error-handling conventions.
Validate external input at application boundaries.
Do not introduce:

* hard-coded secrets;
* unsafe dynamic code execution;
* authentication bypasses;
* unvalidated filesystem paths;
* unvalidated database input;
* sensitive information in logs.

For infrastructure/configuration changes, inspect the existing configuration before changing it.

## 11. Dependencies

Prefer existing dependencies.
Add a dependency only when it is necessary for the requested functionality.
Before adding one, verify that an existing dependency or standard-library solution is insufficient.
Do not add multiple libraries providing substantially the same capability.
Do not upgrade unrelated dependencies as part of another task.

## 12. Code style

Follow the style already established in the affected part of the repository.
Prefer explicit, readable code over clever abstractions.
Reuse existing utilities, types, error handling, and patterns where appropriate.
Do not introduce a new architectural pattern for a single use case.
Keep functions and modules focused on one responsibility.

## 13. Validation

Use evidence from the repository rather than assumptions.
For implementation changes:

1. inspect;
2. make the smallest change;
3. run focused tests/checks;
4. inspect the resulting diff;
5. run broader validation when justified by the change.

Do not claim that tests, builds, migrations, or external integrations were verified unless they were actually executed.
Do not fabricate command output or test results.

## 14. Git

Do not:

* force-push;
* rewrite history;
* delete branches;
* reset or discard unrelated user changes.

Do not overwrite uncommitted user work.
Keep changes attributable to the current task.
Do not create commits unless explicitly requested.

## 15. Reporting

At completion report briefly:

* what changed;
* files changed;
* validation performed;
* remaining known limitations or failures.

Do not provide a long narrative when a concise factual summary is sufficient.

## 16. Definition of Done

A feature is complete only when:

implementation exists;
schema/migrations are complete if needed;
validation exists;
relevant tests exist;
error handling exists;
logs are safe;
no secrets are exposed;
existing tests pass;
the diff contains no unrelated changes.

For Garmin features additionally verify:

actual Garmin request/response shape;
idempotency;
authentication failure behavior;
retry behavior;
mapping to internal models.
34. Priority Order

When requirements conflict, prioritize:

correctness;
user safety / hard constraints;
deterministic domain behavior;
data integrity;
Garmin compatibility;
simplicity;
development speed;
UI polish;
theoretical scalability.

Do not sacrifice correctness for abstraction purity.

## 17. Change Discipline

An agent must not:

rewrite unrelated code;
rename large portions of the project without need;
replace the database layer unnecessarily;
replace the Garmin library without a concrete reason;
introduce a second architecture;
add infrastructure merely because it is theoretically scalable.

If an architectural change is necessary, explain:

current limitation;
concrete requirement;
proposed change;
migration impact;
rollback strategy.