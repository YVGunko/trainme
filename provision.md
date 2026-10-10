# trainme
1. Project

trainme is a personal adaptive training system for cycling, running, and strength training.

The system:

imports Garmin Connect data;
stores raw and normalized training/recovery data;
combines objective Garmin data with subjective user input;
maintains a current training state;
generates adaptive training recommendations;
converts approved recommendations into structured workouts;
uploads approved workouts to Garmin Connect.

The primary goal is minimum development time with a reliable, replaceable architecture.

This is a personal tool. Do not build multi-tenant infrastructure, mobile applications, complex event-driven systems, or enterprise abstractions unless explicitly requested.

2. Product Principles
2.1 Garmin is a data/execution layer

Garmin is NOT the source of truth for training decisions.

Garmin provides:

activities;
health/recovery metrics;
physiological metrics;
workout execution;
device synchronization.

trainme owns:

training history;
subjective data;
constraints;
training state;
planning;
adaptation decisions;
AI recommendations.

Never encode training logic directly into Garmin-specific code.

2.2 AI is a recommendation engine, not the application architecture

LLMs may recommend:

what to train;
when to train;
intensity;
duration;
progression;
adaptation after missed sessions;
modifications based on recovery/constraints.

LLMs must NOT directly manipulate Garmin API payloads.

The flow is:

User + Garmin data
        ↓
Training State
        ↓
Training Recommendation
        ↓
Internal Workout DSL
        ↓
Validation
        ↓
Garmin Adapter
        ↓
Garmin Connect

The LLM must produce structured application-level objects.

2.3 Garmin integration must be replaceable

Current implementation uses unofficial Garmin Connect access through:

cyberjunky/python-garminconnect

Do not allow Garmin-specific implementation details to leak into domain logic.

All Garmin access must go through a GarminAdapter interface/service.

Future official Garmin API support must be possible without rewriting:

training logic;
database model;
AI prompts;
web UI;
workout DSL.
3. Current Technical Direction
Backend

Preferred:

Python 3.12+
FastAPI or equivalent small Python HTTP/service layer
PostgreSQL
python-garminconnect

Do NOT introduce a large framework.

The Garmin integration should run as a separate Python service/process because the Garmin library is Python-based and should not be forced into a JavaScript/Vercel runtime.

Frontend

Simple web application.

Preferred:

Next.js / React if already established in the repository;
otherwise choose the smallest reasonable web stack.

No mobile application.

No React Native.

No native iOS/Android work.

4. Architecture

Target architecture:

                         ┌──────────────────────┐
                         │     Garmin Connect   │
                         └──────────┬───────────┘
                                    │
                           unofficial API
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │    GarminAdapter     │
                         │ python-garminconnect │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │     Raw Garmin       │
                         │       storage       │
                         └──────────┬───────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │ Normalized training  │
                         │       database       │
                         └──────────┬───────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
                 ▼                  ▼                  ▼
          Objective data      Subjective data      Constraints
                 │                  │                  │
                 └──────────────────┼──────────────────┘
                                    ▼
                         ┌──────────────────────┐
                         │   Training State     │
                         └──────────┬───────────┘
                                    ▼
                         ┌──────────────────────┐
                         │   Recommendation     │
                         │         AI           │
                         └──────────┬───────────┘
                                    ▼
                         ┌──────────────────────┐
                         │    Workout DSL       │
                         └──────────┬───────────┘
                                    ▼
                         ┌──────────────────────┐
                         │      Validator       │
                         └──────────┬───────────┘
                                    ▼
                         ┌──────────────────────┐
                         │    GarminAdapter     │
                         └──────────┬───────────┘
                                    ▼
                         Garmin Connect / Device
5. Repository Structure

Prefer this structure:

trainme/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .env.example
│
├── app/
│   ├── api/
│   │   ├── routes/
│   │   └── dependencies/
│   │
│   ├── domain/
│   │   ├── training/
│   │   ├── workout/
│   │   ├── recovery/
│   │   └── constraints/
│   │
│   ├── garmin/
│   │   ├── adapter.py
│   │   ├── client.py
│   │   ├── mapper.py
│   │   └── sync.py
│   │
│   ├── ai/
│   │   ├── prompts/
│   │   ├── recommendation.py
│   │   └── schemas.py
│   │
│   ├── persistence/
│   │   ├── models/
│   │   ├── repositories/
│   │   └── migrations/
│   │
│   ├── services/
│   │   ├── training_state.py
│   │   ├── adaptation.py
│   │   └── workout_service.py
│   │
│   └── config.py
│
├── web/
│   └── ...
│
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/

Do not create directories merely to satisfy this structure. Keep the actual implementation small.

6. Garmin Adapter

All Garmin-specific code belongs under the Garmin integration boundary.

Example interface:

class GarminAdapter(Protocol):

    async def get_activities(...):
        ...

    async def get_activity_details(...):
        ...

    async def get_health_data(...):
        ...

    async def get_sleep(...):
        ...

    async def get_training_metrics(...):
        ...

    async def upload_workout(...):
        ...

    async def schedule_workout(...):
        ...

    async def delete_workout(...):
        ...

The exact interface should evolve according to actual application needs.

Do not expose python-garminconnect classes outside the Garmin adapter.

Domain code must never import:

garminconnect

directly.

Only the Garmin adapter may do so.

7. Garmin Authentication

Garmin authentication is private/unofficial.

Therefore:

never hard-code credentials;
never commit Garmin tokens;
never log access tokens;
never log refresh tokens;
never expose Garmin authentication data to the browser;
keep Garmin credentials server-side;
isolate Garmin authentication from the rest of the application.

Assume Garmin can change its private authentication flow.

The system must fail gracefully if Garmin authentication stops working.

Do not compensate for a Garmin API break by spreading Garmin-specific workarounds throughout the application.

8. Raw Data Rule

Never store only derived aggregates.

Whenever practical, preserve the original Garmin representation:

raw API response;
FIT;
TCX;
or equivalent source payload.

Then normalize it into application tables.

Each normalized activity and daily row records where that payload lives:

source_format;
source_path;
source_sha256.

Tables must be rebuildable from those files.

Reason:

Training algorithms will evolve.

If raw data is discarded, historical data must be re-downloaded from Garmin.

9. Minimum Data Model

The initial schema should remain small.

Garmin account
garmin_account
- id
- garmin_user_id
- encrypted_auth_data
- last_sync_at
- sync_status
- created_at
- updated_at
Activities
activity is one row per activity. Power, normalized power, and cadence do not live here.

activity
- id
- garmin_activity_id
- sport
- sub_sport
- garmin_type_key
- start_at
- end_at
- duration_sec
- moving_duration_sec
- elapsed_duration_sec
- timezone_offset_min
- distance_m
- avg_hr
- max_hr
- avg_speed
- calories
- aerobic_effect
- anaerobic_effect
- training_effect_label
- garmin_activity_load
- hr_zone_1_sec
- hr_zone_2_sec
- hr_zone_3_sec
- hr_zone_4_sec
- hr_zone_5_sec
- source
- source_format
- source_path
- source_sha256
- created_at

garmin_activity_id is unique. id stays the application key.

Do not assume every field exists for every sport.

Sport aggregates are one-to-one with activity. A row exists only for that sport.

activity_field keeps every field present on the FIT session, activity, lap, set, split, and the other non-record messages. The FIT field name and unit are stored as decoded. A field that is not in the file is not invented. Record points stay in activity_sample, one row per numeric record field.

cycling_activity exists when sport is cycling, including indoor_cycling.
- activity_id
- avg_power_w
- max_power_w
- normalized_power_w
- intensity_factor
- tss
- avg_cadence_rpm
- max_cadence_rpm
- total_work_j
- threshold_power_w
- left_power_pct
- avg_left_torque_effectiveness
- avg_right_torque_effectiveness
- avg_left_pedal_smoothness
- avg_right_pedal_smoothness
- avg_combined_pedal_smoothness
- total_ascent_m
- total_descent_m

running_activity
- activity_id
- avg_cadence_spm
- max_cadence_spm
- avg_step_length_mm
- avg_stride_length_cm
- elevation_gain_m
- total_descent_m
- avg_ground_contact_time_ms
- avg_vertical_oscillation_cm
- avg_vertical_ratio
- avg_stance_time_percent
- avg_stance_time_balance
- avg_power_w
- max_power_w
- normalized_power_w
- avg_respiration
- max_respiration
- total_strides

Garmin Connect shows running cadence in steps/min, which is twice the FIT strides/min value, and stride length as twice the FIT step length. Those two display numbers are written on running_activity. The FIT values themselves stay in activity_field.

strength_set is one row per FIT set.
- activity_id
- set_index
- set_type
- category
- exercise
- repetitions
- weight_kg
- duration_sec
- start_at

garmin_activity_load is FIT training_load_peak when that field is present. training_effect_label is not a FIT field.

Power-duration curves stay in the raw FIT or TCX file.

Activity samples

For high-frequency data use a flexible model rather than creating dozens of columns.

activity_sample
- activity_id
- timestamp
- metric
- value
- unit

Unique (activity_id, timestamp, metric).

Rows are the numeric fields of each FIT record point. Lap, split, set, and other FIT messages are stored in activity_field.

Examples:

power
heart_rate
cadence
speed
gps_lat
gps_lon
left_right_balance
pedal_smoothness
torque_effectiveness
running_dynamics

Do not prematurely normalize every Garmin metric into a dedicated table.

Daily state
daily_metrics is one row per training day. date is that day in the user's timezone.

Sleep columns are the main sleep. Extra sleep sessions stay in the raw JSON.

daily_metrics
- date
- resting_hr
- overnight_hrv
- hrv_status
- sleep_duration_sec
- sleep_score
- readiness_score
- readiness_level
- training_status
- vo2max_generic
- vo2max_cycling
- garmin_load_acute
- garmin_load_chronic
- garmin_acwr
- monthly_load_aerobic_low
- monthly_load_aerobic_high
- monthly_load_anaerobic
- running_impact_load
- running_tolerance
- source_format
- source_path
- source_sha256

Stress, body battery, and sleep-stage series are not columns. They stay in the raw JSON.

Garmin metrics are inputs, not unquestionable truth.

garmin_acwr, the monthly load components, and running_tolerance are Garmin inputs. They do not define training state.

Subjective data
subjective_log
- date
- fatigue
- sleep_quality
- soreness
- pain
- pain_location
- motivation
- rpe
- notes

Subjective data is first-class data.

Do not replace subjective information with Garmin-derived metrics.

Constraints
training_constraint
- id
- type
- body_area
- severity
- start_date
- end_date
- status
- notes

Constraints can represent:

injury limitation;
tendon load limitation;
running restriction;
cycling restriction;
available equipment;
available time;
travel;
illness;
temporary training prohibition.
10. Training State

Training state is a deterministic application object.

It should not be generated as free-form prose.

Example:

{
  "date": "2026-10-08",
  "aerobic_load": {},
  "cycling_load": {},
  "running_load": {},
  "strength_load": {},
  "recovery": {},
  "sleep": {},
  "subjective_fatigue": {},
  "mechanical_constraints": [],
  "recent_hard_sessions": [],
  "available_training_time": 60
}

The exact schema may evolve.

The important rule:

AI receives structured training state, not an uncontrolled dump of the entire database.

11. Training Load

Do not use ACWR as the sole injury-risk or readiness model.

daily_metrics may store Garmin's ACWR, load balance, and running tolerance. Training state reads those values and computes its own multi-axis load.

Training state should consider multiple dimensions:

cycling aerobic load
running mechanical load
strength load
recent intensity
recent hard sessions
recovery
sleep
HRV
fatigue
pain
local constraints
available time
planned training
missed sessions

Different sports have different mechanical costs.

A running session must not be treated as equivalent to a cycling session merely because both have the same duration or TSS-like number.

12. Adaptive Planning

The system must distinguish:

planned
completed
partially_completed
missed
cancelled
modified

A missed workout must NOT automatically be moved to the next available day.

Adaptation must consider:

intended training stimulus;
current fatigue;
previous hard sessions;
upcoming planned sessions;
sport-specific load;
mechanical constraints;
available time.

The goal is to preserve the intended adaptation, not the original calendar.

13. Workout DSL

AI must never directly produce Garmin-specific workout JSON.

Use an internal workout representation.

Example:

{
  "sport": "cycling",
  "goal": "vo2max",
  "duration_min": 55,
  "steps": [
    {
      "type": "warmup",
      "duration_min": 10
    },
    {
      "type": "interval",
      "duration_min": 4,
      "target": {
        "type": "power_zone",
        "zone": 5
      }
    },
    {
      "type": "recovery",
      "duration_min": 4
    },
    {
      "type": "repeat",
      "count": 4
    },
    {
      "type": "cooldown",
      "duration_min": 10
    }
  ]
}

The DSL must be:

sport-neutral where possible;
deterministic;
schema validated;
versioned;
independent of Garmin.
14. Workout Validation

Every AI-generated workout must pass deterministic validation before Garmin upload.

Validation must check:

valid sport;
valid duration;
valid step types;
valid target;
valid target ranges;
total duration;
repetition structure;
constraint violations;
impossible combinations;
maximum allowed intensity;
user time limit.

AI output is untrusted input.

Never send raw LLM output directly to Garmin.

15. AI Recommendation Contract

AI should return structured output similar to:

{
  "recommendation": {
    "primary_goal": "...",
    "secondary_goal": "...",
    "reason": "...",
    "confidence": 0.0
  },
  "decision": {
    "sport": "cycling",
    "duration_min": 60,
    "intensity": "moderate"
  },
  "workout": {},
  "adaptation": {
    "changed_from_plan": true,
    "reason": "..."
  }
}

The schema must be validated before persistence.

The AI should explain important decisions, but explanations are secondary to structured output.

16. Human Approval

For the MVP:

AI recommends → user reviews → user approves → Garmin upload.

Do not implement autonomous workout upload initially.

The UI should make these states explicit:

Recommended
Approved
Sent to Garmin
Scheduled
Completed
Skipped
Modified
17. Sync Strategy

Do not build complex real-time infrastructure initially.

For one user:

manual Sync now;
scheduled synchronization approximately 1–2 times/day;
sync after a workout when convenient;
recompute training state after successful sync.

Avoid:

Kafka;
RabbitMQ;
BullMQ;
complex event buses;
unnecessary microservices;
real-time Garmin webhooks unless later proven necessary.
18. Idempotency

Garmin synchronization must be idempotent.

Repeated sync must NOT create duplicate:

activities;
daily metrics;
workouts;
subjective logs.

Use Garmin IDs and appropriate unique constraints.

Example:

UNIQUE(garmin_activity_id)
UNIQUE(garmin_workout_id)

Do not rely on timestamps alone for identity.

19. Time

Store timestamps in UTC.

Keep the user's timezone separately.

Calendar/training-day calculations must use the user's configured timezone.

Never use server local time for training-day logic.

20. Security

Never commit:

.env
Garmin credentials
Garmin tokens
database passwords
LLM API keys
session secrets

Do not log:

Authorization headers
cookies
OAuth tokens
refresh tokens
passwords

Production logs must be safe to share.

21. Testing

Every non-trivial change requires tests.

Prioritize:

domain logic tests;
workout DSL validation tests;
adaptation tests;
Garmin mapping tests;
sync idempotency tests;
integration tests.

Garmin network calls should not be required for ordinary unit tests.

Use fixtures/mocks for Garmin responses.

22. Garmin Contract Fixtures

Create representative fixtures for:

cycling activity;
running activity;
strength activity;
sleep;
HRV;
training readiness;
training status;
body battery;
workout creation;
workout upload response.

Fixtures should be based on actual Garmin responses where possible.

Never fabricate Garmin response structures when real examples are available.

23. Development Workflow

Before implementing a feature:

identify the domain boundary;
identify the minimum required data;
define/modify the schema;
write failing tests;
implement;
run focused tests;
run full test suite;
inspect the diff.

Do not perform unrelated refactoring.

Do not introduce abstractions without a concrete second use case.

24. Dependency Policy

Prefer existing, mature dependencies.

Current Garmin dependency:

python-garminconnect

Do not add another Garmin client unless the current adapter cannot provide a required capability.

Do NOT use deprecated garth as the primary Garmin authentication/client layer.

Do NOT introduce an MCP server for Garmin into the application architecture.

MCP may be useful for external AI tooling, but it is unnecessary for the core web application.

25. Architecture Decisions
Decision: unofficial Garmin API

Chosen because:

personal application;
no mobile application required;
minimal development time;
read + workout-write capabilities are required;
official Garmin Developer Program is not optimized for a purely personal hobby application.

Risk:

Garmin may change private endpoints/authentication.

Mitigation:

Keep Garmin behind GarminAdapter.

Decision: Python Garmin service

Chosen because the current Garmin client ecosystem is Python-based.

Do not attempt to execute the Garmin client inside a JavaScript serverless function.

Decision: PostgreSQL

PostgreSQL is the system of record.

Do not introduce SQLite as the production database.

SQLite may be used by external Garmin tooling or local experiments, but application persistence belongs in PostgreSQL.

Decision: raw + normalized data

Both are required.

Raw data provides recoverability.

Normalized rows store source_format, source_path, and source_sha256 so tables can be rebuilt from the saved files.

Normalized data provides application usability.

Decision: web only

No mobile app.

The MVP web UI must support:

dashboard;
recent activities;
training state;
calendar;
subjective input;
constraints;
AI recommendation;
workout review;
Garmin upload/status.
26. MVP Scope

The first usable version should contain only:

Garmin
authenticate;
sync activities;
sync basic health/recovery metrics;
retrieve workout history;
create/upload structured workout.
Web
dashboard;
activity list/detail;
training calendar;
subjective daily input;
constraints;
recommendation screen;
workout approval;
Garmin upload.
AI
daily recommendation;
workout generation;
adaptation after missed/modified workout;
explanation of recommendation.

Everything else is secondary.

27. Explicit Non-Goals

Do NOT implement initially:

mobile application;
multi-user SaaS;
social features;
athlete sharing;
coach accounts;
Garmin webhook infrastructure;
complex notification system;
advanced predictive injury model;
autonomous workout upload;
automatic medical diagnosis;
computer vision;
wearable-device abstraction layer for multiple vendors;
Kafka/RabbitMQ;
Kubernetes;
microservice decomposition;
complex event sourcing.
28. Medical / Injury Boundary

The application may use user-entered pain and physical constraints to modify training recommendations.

It must NOT:

diagnose injuries;
claim to determine injury risk;
replace medical evaluation;
infer a medical diagnosis from Garmin data.

Training recommendations should respect explicitly entered restrictions.

If a constraint is marked as a hard restriction, the planner must treat it as a hard constraint.

29. User Time Constraint

Available training time is a first-class planning constraint.

A recommendation that cannot fit the user's available time is invalid.

Prefer:

short effective workout

over:

ideal workout that cannot be completed

The planner should preserve the primary adaptation when shortening a workout.

Example:

60 min planned
↓
40 min available
↓
remove secondary volume
↓
preserve primary interval stimulus

Do not simply scale every interval proportionally.

30. Training Progression

Progression must be explicit.

A workout should have an identifiable:

adaptation goal;
progression variable;
current level;
next progression condition.

Progression variables may include:

duration;
interval count;
interval duration;
recovery duration;
intensity;
density;
frequency.

Do not increase multiple major stress dimensions simultaneously without a reason.

31. Code Quality Rules

Prefer:

simple > clever
explicit > implicit
typed > dynamic
deterministic > probabilistic
small interfaces > large interfaces

Avoid:

premature abstractions;
generic repositories everywhere;
unnecessary factories;
unnecessary dependency injection;
excessive configuration;
speculative support for future marketplaces/devices.
32. Change Discipline

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
33. Definition of Done

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

35. Agent Behavior

Before coding, inspect the existing repository.

Do not assume the repository matches this document.

If existing code contradicts this document:

identify the contradiction;
preserve working behavior unless change is required;
make the smallest change needed;
update this document only when the architecture intentionally changes.

When uncertain about Garmin behavior, inspect the current library source/tests or actual API responses instead of guessing.

When uncertain about training logic, keep the decision explicit and configurable rather than hiding assumptions inside code.

Never silently invent Garmin API fields, workout capabilities, physiological metrics, or training rules.

All assumptions that materially affect behavior must be documented in code comments, tests, or architecture documentation.