# EcoRoute frontend API and workflows

This is the frontend integration reference for the EcoRoute API. It describes the deployed
prototype behavior and the request bodies accepted by the backend.

## API base and authentication

Deployed API base URL:

```text
https://5dxn3t8sgh.execute-api.ap-south-1.amazonaws.com
```

Use `Content-Type: application/json` for JSON requests. After sign-in, send the Cognito ID token
on protected requests:

```http
Authorization: Bearer <id_token>
```

The signed-in Cognito subject is the database owner. Authenticated calls can omit `user_id`; if
provided, it must match the token subject. Do not use a user ID from a text field as an identity
source. Production requires authentication. The frontend should treat `401` as a sign-in or
token-refresh condition and `403` as an ownership error.

The interactive API schema is available at `/docs`; machine-readable OpenAPI is `/openapi.json`.

## Endpoint index

`Bearer token` means `Authorization: Bearer <id_token>`. The deployed API requires it for
application data endpoints. The auth endpoints and readiness checks are public.

| Method | Path | Input | Authentication |
| --- | --- | --- | --- |
| `GET` | `/` | None | No |
| `GET` | `/health` | None | No |
| `GET` | `/ready` | None | No |
| `POST` | `/v1/auth/signup` | Email and password JSON | No |
| `POST` | `/v1/auth/confirm` | Email and confirmation code JSON | No |
| `POST` | `/v1/auth/resend-confirmation` | Email JSON | No |
| `POST` | `/v1/auth/login` | Email and password JSON | No |
| `POST` | `/v1/auth/refresh` | Refresh token JSON | No |
| `GET` | `/v1/auth/me` | None | Bearer token |
| `POST` | `/v1/schedules/preview` | Schedule JSON plus optional `max_candidate_evaluations` | Bearer token |
| `POST` | `/v1/schedules` | Schedule JSON | Bearer token |
| `GET` | `/v1/schedules/{schedule_id}` | Optional `user_id` query parameter | Bearer token |
| `GET` | `/v1/schedules/{schedule_id}/timeline` | Optional `user_id` query parameter | Bearer token |
| `GET` | `/v1/schedules/{schedule_id}/revisions` | Optional `user_id` query parameter | Bearer token |
| `GET` | `/v1/places/search` | Required `query`; optional paired `latitude` and `longitude` query parameters | Bearer token |
| `POST` | `/v1/agent/requests` | Agent request JSON | Bearer token |
| `POST` | `/v1/agent/extract-tasks` | New-plan text, date, and timezone JSON | Bearer token |
| `GET` | `/v1/workflows/status` | Required `execution_arn`; optional `user_id` query parameter | Bearer token |
| `POST` | `/v1/schedules/{schedule_id}/stops` | Destination and planning options JSON | Bearer token |
| `POST` | `/v1/schedules/{schedule_id}/replan` | Stop updates and planning options JSON | Bearer token |
| `GET` | `/v1/proposals/{proposal_id}` | Optional `user_id` query parameter | Bearer token |
| `POST` | `/v1/proposals/{proposal_id}/approve` | Idempotency key JSON | Bearer token |
| `POST` | `/v1/proposals/{proposal_id}/reject` | Optional rejection reason JSON | Bearer token |
| `GET` | `/v1/preferences` | Optional `user_id` query parameter | Bearer token |
| `POST` | `/v1/preferences` | Preference JSON | Bearer token |
| `PUT` | `/v1/preferences/{key}` | Preference value JSON; optional `user_id` query parameter | Bearer token |
| `DELETE` | `/v1/preferences/{key}` | Optional `user_id` query parameter | Bearer token |
| `GET` | `/v1/routines` | Optional `user_id` query parameter | Bearer token |
| `POST` | `/v1/routines` | Routine JSON | Bearer token |
| `PUT` | `/v1/routines/{routine_id}` | Routine JSON | Bearer token |
| `DELETE` | `/v1/routines/{routine_id}` | Optional `user_id` query parameter | Bearer token |

All JSON request examples and response details follow below. For authenticated requests, omit
`user_id`; if included, it must equal the signed-in Cognito subject.

## Account endpoints

### Sign up

`POST /v1/auth/signup`

```json
{
  "email": "person@example.com",
  "password": "a user supplied password"
}
```

Response includes `user_id`, `confirmation_required`, and email `delivery` details. The deployed
Cognito pool requires at least 12 characters with uppercase, lowercase, number, and symbol.

### Confirm email

`POST /v1/auth/confirm`

```json
{
  "email": "person@example.com",
  "code": "123456"
}
```

### Resend confirmation code

`POST /v1/auth/resend-confirmation`

```json
{
  "email": "person@example.com"
}
```

### Sign in

`POST /v1/auth/login`

```json
{
  "email": "person@example.com",
  "password": "the user's password"
}
```

Response:

```json
{
  "access_token": "<cognito access token>",
  "id_token": "<cognito id token>",
  "refresh_token": "<cognito refresh token>",
  "expires_in": 3600,
  "token_type": "Bearer"
}
```

Use `id_token` for API bearer authentication. Store tokens carefully; never log them.

### Refresh tokens

`POST /v1/auth/refresh`

```json
{
  "refresh_token": "<cognito refresh token>"
}
```

### Current account

`GET /v1/auth/me`

Requires the bearer token. Returns `{ "user_id": "<cognito subject>" }`.

## Plan creation and preview

Locations use latitude and longitude in decimal degrees. Schedule timestamps must include a UTC
offset. The `date` is the local calendar date for the selected timezone.

### Preview a plan

`POST /v1/schedules/preview`

The body is the schedule body below, with optional `max_candidate_evaluations` (1-5000). Preview
does not save the schedule. It returns `feasible`, the ordered `stops`, `timeline`, `metrics`,
`conflicts`, `explanation_facts`, `evaluated_orders`, `search_truncated`, and
`travel_estimate_source`. An infeasible preview is returned with `feasible: false` and its conflicts.
When stops are present, `metrics.distance_savings` reports estimated km saved by combining errands.
Its baseline is one separate start-to-finish journey per stop, compared with one combined itinerary.
This is a route-distance comparison. It also includes `public_transport_scenario`, a same-distance
CO₂/CO₂e comparison of a solo gasoline-car trip and an illustrative public-transport passenger-km
factor. This is not a transit route or timetable. The estimate includes the car factor source and a
warning that transit mode, occupancy, and electricity mix can change actual emissions.

### Extract errands from a new-plan request

Before previewing a new plan, the frontend can ask the task extractor to split the request into
distinct errands and explicit time constraints. Route-search candidates can be ranked and
preselected between the planned start and end locations; the user can still choose an exact place
with `/v1/places/search`.

`POST /v1/agent/extract-tasks`

```json
{
  "text": "I need to visit the grocery store and pharmacy before 5 pm",
  "date": "2026-10-11",
  "timezone": "Asia/Kolkata"
}
```

Response:

```json
{
  "tasks": [
    {
      "title": "Grocery store",
      "destination_query": "grocery store",
      "type": "errand",
      "duration_minutes": null,
      "latest_start": null,
      "latest_end": "2026-10-11T17:00:00+05:30",
      "fixed_start": null
    },
    {
      "title": "Pharmacy",
      "destination_query": "pharmacy",
      "type": "errand",
      "duration_minutes": null,
      "latest_start": null,
      "latest_end": "2026-10-11T17:00:00+05:30",
      "fixed_start": null
    }
  ],
  "clarification_question": null
}
```

The response is produced by the Strands agent using the configured OpenAI-compatible Bedrock Mantle
endpoint. Appointment tasks have `type: "appointment"` even when no appointment time was given.
Only explicit durations and times should be treated as extracted facts. If duration is omitted, the
frontend may offer a clearly marked editable estimate. Include each selected destination in the
schedule `stops` array, then use the existing preview and create sequence.
An arrival request such as “be at the pharmacy by 5 pm” maps to `latest_start`; a completion
deadline maps to `latest_end`; an exact appointment time maps to `fixed_start`. Keep those fields
distinct when constructing stops so the planner can validate the requested semantics.

### Create a plan

`POST /v1/schedules`

```json
{
  "date": "2026-10-11",
  "timezone": "Asia/Kolkata",
  "start_at": "2026-10-11T09:00:00+05:30",
  "end_at": "2026-10-11T18:00:00+05:30",
  "start_location": {
    "latitude": 13.0827,
    "longitude": 80.2707,
    "label": "Chennai Central"
  },
  "end_location": {
    "latitude": 13.0827,
    "longitude": 80.2707,
    "label": "Chennai Central"
  },
  "stops": [
    {
      "id": "appointment-stop-id",
      "title": "Doctor appointment",
      "type": "appointment",
      "location": {
        "latitude": 13.0674,
        "longitude": 80.2376,
        "label": "Clinic"
      },
      "duration_minutes": 45,
      "fixed_start": "2026-10-11T11:00:00+05:30",
      "priority": 5,
      "mandatory": true
    },
    {
      "id": "grocery-stop-id",
      "title": "Pick up groceries",
      "type": "errand",
      "location": {
        "latitude": 13.0569,
        "longitude": 80.2425,
        "label": "Grocery store"
      },
      "duration_minutes": 30,
      "latest_end": "2026-10-11T17:00:00+05:30",
      "priority": 3,
      "mandatory": false
    }
  ],
  "constraints": [
    {
      "type": "precedence",
      "hardness": "hard",
      "parameters": {
        "before": "appointment-stop-id",
        "after": "grocery-stop-id"
      }
    }
  ],
  "include_routines": true
}
```

Each stop accepts `id` (optional), `title`, `type`, `location`, `duration_minutes`, `earliest_start`,
`latest_start`, `latest_end`, `fixed_start`, `opening_hours`, `priority` (1-5), `mandatory`,
`status`, `source`, and `attributes`. Use timezone offsets on all stop time fields. A simple
`opening_hours` value is `{ "open": "09:00", "close": "18:00" }`.

Constraints have `type`, `hardness` (`hard` or `soft`), optional `weight`, and a `parameters` object.
For example, `max_travel_minutes` uses `{ "minutes": 90 }` in `parameters`.

`include_routines` defaults to `true`; set it to `false` if the user opts out of saved routines.
The create response includes `id`, `current_revision`, `status`, `metrics`, `timeline`, and
`travel_estimate_source`.

### Read a saved plan

- `GET /v1/schedules/{schedule_id}`  -  schedule data, stops, constraints, and current revision.
- `GET /v1/schedules/{schedule_id}/timeline`  -  recalculated feasible timeline and metrics.
- `GET /v1/schedules/{schedule_id}/revisions`  -  saved plan revision history.

These calls derive the owner from the bearer token; `user_id` query parameter is optional.

## Place search and agent workflow

### Search places directly (autocomplete)

`GET /v1/places/search?query=pharmacy%20near%20Chennai%20Central&latitude=13.0827&longitude=80.2707`

`query` is required. Supply both `latitude` and `longitude` to bias search near a location, or omit
both. Response is `{ "places": [...] }`; each place includes `id`, `title`, `label`, `latitude`,
`longitude`, and `categories` when available.

### Rank places by route detour

`POST /v1/places/route-search` accepts a place query and the planned start/end locations:

```json
{
  "query": "pharmacy",
  "start_location": { "latitude": 13.0827, "longitude": 80.2707 },
  "end_location": { "latitude": 13.0827, "longitude": 80.2707 },
  "max_results": 3
}
```

The response contains real place candidates ranked by added routed distance. Each candidate includes
`route_rank`, `route_km`, and `detour_km` alongside its place identity and coordinates. Natural-
language requests to add a stop return the same route-ranked candidate shape.

### Ask the agent to find a destination or replan

`POST /v1/agent/requests`

```json
{
  "schedule_id": "<schedule_id>",
  "text": "Find a pharmacy near Chennai Central",
  "timezone": "Asia/Kolkata"
}
```

The API starts the Step Functions workflow and responds with an `execution_arn`, `started_at`, and
`status: "running"`. Continue polling the status endpoint; do not expect candidate results in the
start response.

### Poll workflow status

`GET /v1/workflows/status?execution_arn=<url-encoded execution ARN>`

Poll every 1-3 seconds while `status` is `RUNNING`, with a reasonable client timeout. The response
contains `status`, `result`, `error`, and `cause`. On success, a place search result looks like:

```json
{
  "status": "SUCCEEDED",
  "result": {
    "status": "destination_candidates",
    "intent": {
      "operation": "add_destination",
      "destination_query": "pharmacy near Chennai Central"
    },
    "candidates": [
      {
        "id": "<place id>",
        "title": "<place name>",
        "label": "<formatted address>",
        "latitude": 13.08,
        "longitude": 80.27,
        "route_rank": 1,
        "route_km": 3.42,
        "detour_km": 0.61,
        "categories": []
      }
    ],
    "message": "Place results do not verify product stock or price."
  }
}
```

Other successful `result.status` values include `clarification_required` and
`needs_destination_selection`. Show the clarification question from `result.question` or the
intent's `clarification_question`. If the workflow status is `FAILED`, show a retry/error state and
retain the execution ARN for diagnostics. The model and place search do not verify inventory, price,
opening hours, or other live business facts.

## Add a stop and approve the proposed plan

Selecting a candidate does not modify the schedule. Submit it as a proposed stop:

`POST /v1/schedules/{schedule_id}/stops`

```json
{
  "destination": {
    "title": "<candidate title>",
    "type": "errand",
    "location": {
      "id": "<candidate place id>",
      "latitude": 13.08,
      "longitude": 80.27,
      "label": "<candidate address>"
    },
    "duration_minutes": 30,
    "priority": 3,
    "mandatory": true,
    "source": "amazon_location"
  },
  "allow_reordering_flexible_stops": true,
  "max_reordered_stops": 3
}
```

Response is a proposal with `id`, `schedule_id`, `status`, `feasible`, `base_revision`,
`proposed_stops`, `metrics`, `conflicts`, `explanation_facts`, and `expires_at`. Present the
proposal and conflicts to the user before committing it. If `feasible` is false, explain the
conflicts and do not offer approval; infeasible proposals cannot be committed.
Use `GET /v1/proposals/{proposal_id}` to reload a proposal before approval if needed; it returns
the same proposal fields.

Approve:

`POST /v1/proposals/{proposal_id}/approve`

```json
{
  "idempotency_key": "<unique key for this approval>"
}
```

The key must be 8-128 characters. Response contains `schedule_id`, `revision`, and
`idempotent_replay`. Use a new unique key for each approval intent; retrying the same approval may
reuse the same key safely.

Reject instead:

`POST /v1/proposals/{proposal_id}/reject`

```json
{
  "reason": "The suggested stop does not fit the day"
}
```

## Modify a plan and approve the replan

Submit a replan proposal. Keys in `updates` are stop IDs from the saved schedule. Allowed update
fields are `duration_minutes`, `earliest_start`, `latest_start`, `latest_end`, `fixed_start`,
`priority`, and `mandatory`.

`POST /v1/schedules/{schedule_id}/replan`

```json
{
  "updates": {
    "<stop_id>": {
      "duration_minutes": 45
    }
  },
  "reason": "The appointment was extended",
  "allow_reordering_flexible_stops": true,
  "max_reordered_stops": 3
}
```

The response is a proposal with the same shape as an add-stop proposal. Show the proposed itinerary,
then approve it through `/v1/proposals/{proposal_id}/approve` or reject it. After approval, reload the
schedule and timeline; approval increments `current_revision`.

## Preferences and routines

### Preferences

- `GET /v1/preferences`
- `POST /v1/preferences`
- `PUT /v1/preferences/{key}`
- `DELETE /v1/preferences/{key}` (204 response)

The optional `user_id` on read, update, and delete operations is a query parameter. Leave it out
when using a bearer token.

Create body:

```json
{
  "key": "travel_mode",
  "value": { "mode": "walking" },
  "confidence": 1,
  "source": "explicit"
}
```

Update body:

```json
{
  "value": { "mode": "bicycle" },
  "confidence": 1,
  "source": "explicit"
}
```

### Routines

- `GET /v1/routines`
- `POST /v1/routines` (201 response)
- `PUT /v1/routines/{routine_id}`
- `DELETE /v1/routines/{routine_id}` (204 response)

Create and update use this body shape:

```json
{
  "routine": {
    "name": "Morning walk",
    "weekday": 0,
    "active": true,
    "stop": {
      "title": "Park walk",
      "type": "routine",
      "location": {
        "latitude": 13.0827,
        "longitude": 80.2707,
        "label": "Local park"
      },
      "duration_minutes": 30,
      "fixed_start": "2026-10-12T07:00:00+05:30",
      "mandatory": false
    }
  }
}
```

`weekday` uses Monday = 0 through Sunday = 6. Active routines for the schedule date are included
when `include_routines` is true.

## Typical frontend sequence

1. Sign up, confirm the email, and sign in. Keep the returned ID token for bearer authentication.
2. Call `/v1/auth/me` to display the signed-in account. The returned `user_id` is informational;
   authenticated schedule calls can omit it.
3. Use `/v1/places/search` for start/end and manually entered stop autocomplete.
4. For a natural-language new plan, call `/v1/agent/extract-tasks`, let the user pick exact locations,
   then build the schedule body. Call `/v1/schedules/preview`, display the candidate timeline and conflicts,
   then call `/v1/schedules` to save it.
5. Submit a natural-language request to `/v1/agent/requests`, poll `/v1/workflows/status`, and let
   the user select a returned candidate.
6. Submit the selected place to `/v1/schedules/{id}/stops`; show the proposed order, timings, and
   conflicts. Commit only after the user approves.
7. For edits, call `/v1/schedules/{id}/replan`, show the revised proposal, then approve or reject.
   Reload the schedule, timeline, and revisions after approval.

## Errors and prototype notes

Validation and API errors normally use `{ "detail": ... }`. Common status codes are `401` for
missing/invalid authentication, `403` for a user ID mismatch, `404` for a resource not owned by the
signed-in account, `409` for stale or non-pending proposals, `422` for invalid request data or
infeasible schedule constraints, and `502` for an AWS integration failure.

There is currently no schedule-delete endpoint. The API's CORS policy permits browser origins for
this prototype; requests still require a valid bearer token in production.
