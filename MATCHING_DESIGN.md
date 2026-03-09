# Matching Service Design

## Goal

Keep the current scoring logic in `cv_matching.py` and build the integration layer around it so the service can:

1. Read candidates and jobs from Postgres.
2. Convert database rows into the payload shape expected by the matcher.
3. Save match results into the existing match tables.
4. Notify the main backend when matching is finished.

This design covers only the basic matching flow:

- Direct job matching when a company publishes a job.
- Scraped job matching when the scraper batch finishes.

No re-matching strategy is included in this version.

## Current Matcher Contract

`cv_matching.py` expects this shape:

```json
{
  "totalExperience": 2.5,
  "skills": [
    { "skillName": "Python", "verified": true }
  ]
}
```

For jobs:

```json
{
  "totalExperience": 4,
  "skills": [
    { "skillName": "Python" },
    { "skillName": "PostgreSQL" }
  ]
}
```

The integration layer should adapt Postgres data into this shape instead of changing the scoring code.

## Trigger API

The matching service should expose two trigger endpoints.

### 1. Direct Job Trigger

`POST /match/direct-job`

Request:

```json
{
  "jobId": "uuid",
  "requestId": "optional-string"
}
```

Use case:

- Main backend calls this when a company publishes a direct job.

Immediate response:

```json
{
  "type": "direct",
  "status": "accepted",
  "requestId": "generated-or-forwarded-id",
  "jobId": "uuid",
  "acceptedAt": "2026-03-08T12:00:00Z"
}
```

### 2. Scraped Jobs Trigger

`POST /match/scraped-jobs`

Request:

```json
{
  "since": "2026-03-08T10:00:00Z",
  "until": "2026-03-08T11:00:00Z",
  "requestId": "optional-string"
}
```

Use case:

- Scraper or main backend calls this after a scrape batch finishes.
- Matcher loads scraped jobs where `updated_at >= since` and `updated_at < until`.

Immediate response:

```json
{
  "type": "scraped",
  "status": "accepted",
  "requestId": "generated-or-forwarded-id",
  "since": "2026-03-08T10:00:00Z",
  "until": "2026-03-08T11:00:00Z",
  "acceptedAt": "2026-03-08T12:00:00Z"
}
```

Why `since` and `until`:

- It is safer than sending only the first scraped timestamp.
- It works for both inserts and updates.

## Completion Callback

After matching completes, the matching service should call a backend webhook endpoint.

Recommended config:

- `MATCHING_DIRECT_CALLBACK_URL`
- `MATCHING_DIRECT_CALLBACK_TOKEN`
- `MATCHING_SCRAPED_CALLBACK_URL`
- `MATCHING_SCRAPED_CALLBACK_TOKEN`

Recommended endpoint shape on the backend:

- `POST /internal/matching/direct/completed`
- `POST /internal/matching/scraped/completed`

Direct callback payload:

```json
{
  "type": "direct",
  "status": "completed",
  "jobId": "uuid",
  "requestId": "optional-string",
  "processedJobs": 1,
  "processedCandidates": 120,
  "upsertedMatches": 120,
  "startedAt": "2026-03-08T12:00:00Z",
  "finishedAt": "2026-03-08T12:00:12Z"
}
```

Scraped callback example:

```json
{
  "type": "scraped",
  "status": "completed",
  "since": "2026-03-08T10:00:00Z",
  "until": "2026-03-08T11:00:00Z",
  "requestId": "optional-string",
  "processedJobs": 35,
  "processedCandidates": 120,
  "upsertedMatches": 4200,
  "startedAt": "2026-03-08T11:00:05Z",
  "finishedAt": "2026-03-08T11:02:10Z"
}
```

Failure callback example:

```json
{
  "type": "scraped",
  "status": "failed",
  "requestId": "optional-string",
  "error": "short failure reason",
  "startedAt": "2026-03-08T11:00:05Z",
  "finishedAt": "2026-03-08T11:00:09Z"
}
```

The backend should use these callbacks only as a signal that the results now exist in Postgres.

The trigger endpoints should return immediately with `accepted`. Completion and failure should be tracked through the callback payload.

## Database Reads

### Candidates

Load only active candidates that have profile data.

Tables:

- `job_seekers`
- `job_seeker_profiles`
- `job_seeker_skills`
- `skills`

Required fields:

- `job_seekers.id`
- `job_seekers.is_active`
- `job_seeker_profiles.years_of_experience`
- `job_seeker_skills.verified`
- `skills.name`

Recommended candidate filter:

- `job_seekers.is_active = true`
- profile exists

Optional later:

- only candidates with at least one skill

### Direct Jobs

Tables:

- `direct_jobs`
- `direct_job_skills`
- `skills`

Required fields:

- `direct_jobs.id`
- `direct_jobs.status`
- `direct_jobs.experience_level`
- `skills.name`

Recommended direct job filter:

- `direct_jobs.id = :jobId`
- `direct_jobs.status = 'PUBLISHED'`

### Scraped Jobs

Tables:

- `scraped_jobs`
- `scraped_job_skills`
- `skills`

Required fields:

- `scraped_jobs.id`
- `scraped_jobs.updated_at`
- `skills.name`

Recommended scraped job filter:

- `scraped_jobs.updated_at >= :since`
- `scraped_jobs.updated_at < :until`

## DB to Matcher Payload Mapping

### Candidate Payload

Source:

- `job_seeker_profiles.years_of_experience`
- `job_seeker_skills.verified`
- `skills.name`

Target:

```json
{
  "totalExperience": 3.5,
  "skills": [
    { "skillName": "Python", "verified": true },
    { "skillName": "FastAPI", "verified": true }
  ]
}
```

Rules:

- `totalExperience = years_of_experience || 0`
- each skill row becomes `{ "skillName": skill.name, "verified": verified }`

### Direct Job Payload

Source:

- `direct_jobs.experience_level`
- `skills.name`

Target:

```json
{
  "totalExperience": 4,
  "skills": [
    { "skillName": "Node.js" },
    { "skillName": "PostgreSQL" }
  ]
}
```

Experience mapping:

- `ENTRY -> 1`
- `JUNIOR -> 2`
- `MID -> 4`
- `SENIOR -> 6`
- `LEAD -> 8`
- `MANAGER -> 10`

Each skill row becomes:

```json
{ "skillName": "Skill Name" }
```

### Scraped Job Payload

Source:

- `skills.name`

Target:

```json
{
  "totalExperience": null,
  "skills": [
    { "skillName": "React" },
    { "skillName": "TypeScript" }
  ]
}
```

Rule:

- Set `totalExperience = null` so the current matcher uses skills only.

## Matching Execution Flow

### Direct Job Matching

1. Receive `jobId`.
2. Load the published direct job and its skills.
3. Load all active candidates and their skills.
4. Build matcher payloads.
5. Run `SimilaritySkillMatcher.final_score(candidate_payload, job_payload)`.
6. Convert score for storage.
7. Upsert into `direct_job_matches`.
8. Send completion callback.

### Scraped Job Matching

1. Receive `since` and `until`.
2. Load scraped jobs in that window and their skills.
3. Load all active candidates and their skills.
4. Build matcher payloads.
5. Run the current matcher for each candidate-job pair.
6. Convert score for storage.
7. Upsert into `scraped_job_matches`.
8. Send completion callback.

## Score Storage

The current matcher returns `final_score` in the range `0.0` to `1.0`.

Recommended database storage:

- `stored_match_score = round(final_score * 100, 2)`

Examples:

- `0.83 -> 83.00`
- `0.4 -> 40.00`

Why:

- easier to read in SQL and admin tools
- better fit for `Decimal(5, 2)`

If the backend already expects `0-1`, keep the current scale and store it directly. The team should choose one scale and keep it consistent.

## Upsert Rules

### Direct Job Matches

Target table:

- `direct_job_matches`

Unique key:

- `(direct_job_id, job_seeker_id)`

Upsert fields:

- `match_score`
- `updated_at`

### Scraped Job Matches

Target table:

- `scraped_job_matches`

Unique key:

- `(scraped_job_id, job_seeker_id)`

Upsert fields:

- `match_score`
- `updated_at`

This makes matching idempotent for the same trigger window or job ID.

## Recommended Service Structure

Suggested new modules:

- `matcher_service.py`
  - orchestration for direct and scraped flows
- `db.py`
  - database connection and query helpers
- `payload_builders.py`
  - converts DB rows into matcher payloads
- `callback.py`
  - sends completion webhook to backend

Keep:

- `cv_matching.py`
  - scoring engine

Extend:

- `main.py`
  - add matching endpoints, or split parser and matcher APIs into separate files if preferred

## SQL-Level Query Shape

The exact implementation can be SQLAlchemy, psycopg, or raw SQL. The shape should be:

### Candidate Query Result

One row per candidate skill:

- `job_seeker_id`
- `years_of_experience`
- `skill_name`
- `verified`

Then group rows in Python by `job_seeker_id`.

### Direct Job Query Result

One row per job skill:

- `job_id`
- `experience_level`
- `skill_name`

Then group rows in Python by `job_id`.

### Scraped Job Query Result

One row per job skill:

- `job_id`
- `updated_at`
- `skill_name`

Then group rows in Python by `job_id`.

## Environment Variables

Recommended env additions:

- `DATABASE_URL`
- `MATCHING_DIRECT_CALLBACK_URL`
- `MATCHING_DIRECT_CALLBACK_TOKEN`
- `MATCHING_SCRAPED_CALLBACK_URL`
- `MATCHING_SCRAPED_CALLBACK_TOKEN`
- `MATCHING_MODEL_NAME`
- `MATCHING_SIMILARITY_THRESHOLD`
- `MATCHING_LOCAL_FILES_ONLY`

## Important Implementation Notes

- Do not change the scoring formula in `cv_matching.py` for this phase.
- The integration layer is responsible for shaping database rows into matcher input.
- The matcher currently depends on `sentence-transformers`; make sure the model is available in the deployment environment.
- Callback failures should not remove already-written DB matches. Write matches first, then send callback.

## Implementation Order

1. Add DB connection layer.
2. Add candidate and job loaders.
3. Add payload builders that match the current matcher contract.
4. Add direct job matching endpoint.
5. Add scraped jobs matching endpoint.
6. Add upsert logic into match tables.
7. Add completion callback to backend.
