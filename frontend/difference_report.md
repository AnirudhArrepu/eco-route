# EcoRoute: actual implementation and feature gaps

Audit date: 2026-10-10. Backend inspected: `/home/niranjanm/main/projects/ev_hacks/eco-route/backend`.

## Scope and evidence

- Findings come from route handlers, schemas, services, planner, integrations, models, deployment files, and test source. Documentation was not treated as proof.
- **IMPLEMENTED** means a concrete executable code path exists for the stated scope; **PARTIAL** means significant workflow behavior is absent or limited; **MISSING** means no implementation was found. **MOCKED** identifies simulated data explicitly.
- Verification: source inspection, AST enumeration of **32 explicit HTTP route definitions**, and **7 passing isolated synthetic planner checks**. No backend source was changed.
- No server, supplied pytest suite, AWS calls, database integration tests, model inference, or deployment checks were run. Working credentials, provisioned resources, model availability, and production behavior remain **unverified**.
- Backend source references below are relative to `eco-route/backend/`; React references beginning `src/` are relative to this workspace.

## Main finding

The backend implements a structured, single-mode itinerary planner with persisted schedules, destination search integration, and human-approved change proposals. It does **not** implement an end-to-end conversational multi-task planner, public-transit routing, voice transcription, or fuel/EV optimization.

- New schedules can reorder supplied stops and enforce supported deadlines. Changes use a smaller insertion/swap search and require explicit approval.
- The AI produces **one intent and one destination query**. Recognizing `create_schedule` does not create a schedule.
- Default development behavior uses **mock travel estimates**, **empty place-search results**, and **regex intent parsing**. AWS/LLM functionality requires configuration.
- The workspace React app is still a Vite starter. A separate plain-JavaScript planner exists at backend `/app`.

Evidence: [main.py:86–161](eco-route/backend/app/main.py#L86-L161), [planner.py:168–277](eco-route/backend/app/planner.py#L168-L277), [config.py:4–30](eco-route/backend/app/config.py#L4-L30), [src/App.jsx:7–30](src/App.jsx#L7-L30).

## 1. API endpoint inventory

### Authentication and shared contracts

| Code | Actual requirement |
|---|---|
| Public | No bearer dependency. Cognito operations still require configured pool/client. |
| Token | Bearer token always needed for `/v1/auth/me`; otherwise it returns 401. |
| P | Bearer required when `AUTH_REQUIRED=true` or environment is production; optional in development. A supplied token is always validated. |
| O | P plus owner identity: with a token, use Cognito `sub` and reject a different supplied `user_id` (403). Without a token, require explicit `user_id` (422). Wrong-owner schedules/proposals return 404. |

JWT validation uses Cognito JWKS, RS256, issuer, and app audience/client checks; accepts Cognito ID or access tokens. Development `user_id` is client asserted, so it is not secure identity. Evidence: [auth.py:11–71](eco-route/backend/app/auth.py#L11-L71), [service.py:109–112](eco-route/backend/app/service.py#L109-L112), [service.py:171–174](eco-route/backend/app/service.py#L171-L174).

Shared request/response shapes:

- **Location**: `latitude`, `longitude`; optional `id`, `label`. Coordinates are bounded; extra location fields are forbidden.
- **Stop**: `title`, `location`, `duration_minutes` (1–1440); optional `id`, `type`, `earliest_start`, `latest_start`, `latest_end`, `fixed_start`, `opening_hours`, `priority` (1–5), `mandatory`, `status`, `source`, `attributes`. Returned stops have generated IDs when omitted.
- **ScheduleCreate**: `date`, `start_at`, `end_at`, `start_location`, `end_location`; optional `user_id`, `timezone="UTC"`, `stops=[]`, `constraints=[]`, `include_routines=true`. Timestamps must include offsets on creation. Constraint shape: `type`, `hardness="hard"`, `weight=1`, `parameters={}`.
- **Proposal**: `id`, `schedule_id`, `status`, `feasible`, `base_revision`, `proposed_stops`, `metrics`, `conflicts`, `explanation_facts`, `expires_at`. Metrics normally contain `before`/`after`; each metrics object includes travel, distance, waiting, stop count, timeline, and return timing. Proposed stops also contain `order_index`.
- **AgentRequest**: `text`; optional `user_id`, `schedule_id`, `timezone="UTC"`. No audio, history, conversation ID, or task array.

Evidence: [schemas.py:5–105](eco-route/backend/app/schemas.py#L5-L105), [main.py:58–59](eco-route/backend/app/main.py#L58-L59), [planner.py:141–165](eco-route/backend/app/planner.py#L141-L165).

### Authentication endpoints

All bodies are JSON. These are real Cognito wrappers, not local account mocks; missing configuration returns 503.

| Method / endpoint | Purpose and inputs | Output | Auth | Status / evidence |
|---|---|---|---|---|
| POST `/v1/auth/signup` | Create account: `email`, `password` | `user_id`, `confirmation_required`, `delivery` | Public | IMPLEMENTED, configured Cognito required. [main.py:32–34](eco-route/backend/app/main.py#L32-L34), [cognito.py:28–40](eco-route/backend/app/cognito.py#L28-L40) |
| POST `/v1/auth/confirm` | Confirm email: `email`, `code` | `confirmed: true` | Public | IMPLEMENTED. [main.py:36–38](eco-route/backend/app/main.py#L36-L38), [cognito.py:43–50](eco-route/backend/app/cognito.py#L43-L50) |
| POST `/v1/auth/resend-confirmation` | Resend code: `email` | `delivery` | Public | IMPLEMENTED. [main.py:40–42](eco-route/backend/app/main.py#L40-L42), [cognito.py:53–59](eco-route/backend/app/cognito.py#L53-L59) |
| POST `/v1/auth/login` | Password login: `email`, `password` | `access_token`, `id_token`, `refresh_token`, `expires_in`, `token_type` | Public | PARTIAL: password flow exists; additional Cognito challenges return 400, with no completion endpoint. [main.py:44–46](eco-route/backend/app/main.py#L44-L46), [cognito.py:62–81](eco-route/backend/app/cognito.py#L62-L81) |
| POST `/v1/auth/refresh` | Refresh session: `refresh_token` | Same token shape; refresh token may be null | Public | IMPLEMENTED for refresh flow. [main.py:48–50](eco-route/backend/app/main.py#L48-L50), [cognito.py:84–93](eco-route/backend/app/cognito.py#L84-L93) |
| GET `/v1/auth/me` | Resolve bearer identity; no body | `user_id` (Cognito subject) | Token | IMPLEMENTED. [main.py:52–56](eco-route/backend/app/main.py#L52-L56) |

No password-reset, challenge-response, token-revocation, or server logout endpoints. [main.py:32–56](eco-route/backend/app/main.py#L32-L56).

### Schedules, discovery, agent, proposals, and workflows

`sid` and `pid` are path IDs. Read endpoints with O authentication accept `user_id` as a query parameter; write endpoints below accept it in their body.

| Method / endpoint | Purpose and inputs | Output | Auth | Status / evidence |
|---|---|---|---|---|
| POST `/v1/schedules` | Optimize and immediately save ScheduleCreate | `id`, `user_id`, `date`, `current_revision`, `status`, `metrics`, `timeline`, `travel_estimate_source` | O | IMPLEMENTED for supported constraints; travel MOCKED by default; infeasibility → 422. [main.py:86–90](eco-route/backend/app/main.py#L86-L90), [service.py:32–76](eco-route/backend/app/service.py#L32-L76) |
| POST `/v1/schedules/preview` | Nonpersisting ScheduleCreate plus `max_candidate_evaluations` (1–5000; default 500) | `feasible`, ordered `stops`, `timeline`, `metrics`, `conflicts`, `explanation_facts`, `evaluated_orders`, `search_truncated`, `travel_estimate_source` | O | IMPLEMENTED bounded search; travel MOCKED by default. Infeasible preview is a normal 200 payload. [main.py:92–95](eco-route/backend/app/main.py#L92-L95), [service.py:78–107](eco-route/backend/app/service.py#L78-L107) |
| GET `/v1/places/search` | Query `query`; optional paired `latitude`, `longitude` bias | `places: [{id,title,label,longitude,latitude,categories}]` | P | PARTIAL overall: actual AWS search when configured; otherwise `places: []`. No local place fixtures or ranking logic. [main.py:97–108](eco-route/backend/app/main.py#L97-L108), [integrations.py:11–23](eco-route/backend/app/integrations.py#L11-L23), [integrations.py:42–50](eco-route/backend/app/integrations.py#L42-L50) |
| GET `/v1/schedules/{sid}` | Read saved schedule | Identity/date/timezone/horizon/locations/status/revision, ordered `stops`, `constraints` | O | IMPLEMENTED. Does not return calculated timeline; use timeline route. [main.py:110–116](eco-route/backend/app/main.py#L110-L116) |
| GET `/v1/schedules/{sid}/timeline` | Recalculate saved order's timeline | `schedule_id`, `revision`, `feasible`, `timeline`, `metrics`, `conflicts`, `travel_estimate_source` | O | IMPLEMENTED calculation, travel MOCKED by default; does not optimize/persist a new order. [main.py:118–121](eco-route/backend/app/main.py#L118-L121), [service.py:114–124](eco-route/backend/app/service.py#L114-L124) |
| POST `/v1/schedules/{sid}/stops` | Propose one insertion: `destination: Stop`, optional `constraints`, `allow_reordering_flexible_stops=true`, `max_reordered_stops=3` (0–8) | Proposal, including `pending` or `infeasible` | O | PARTIAL: insertion works; advertised reordering flags have no effect on insertion branch. No commit until approval. [main.py:123–126](eco-route/backend/app/main.py#L123-L126), [planner.py:190–199](eco-route/backend/app/planner.py#L190-L199) |
| POST `/v1/schedules/{sid}/replan` | Propose changes: `updates={stop_id:{field:value}}`, optional constraints/reordering flags and `reason` | Proposal | O | PARTIAL: limited updates/search; cannot repair an already infeasible input order. [main.py:128–131](eco-route/backend/app/main.py#L128-L131), [service.py:153–169](eco-route/backend/app/service.py#L153-L169), [planner.py:168–188](eco-route/backend/app/planner.py#L168-L188) |
| POST `/v1/agent/requests` | Interpret AgentRequest | Clarification, place candidates, replan Proposal, **or** `{execution_arn,started_at,status:"running"}` | O | PARTIAL: single-intent dispatch; no natural-language schedule creation or task decomposition. [main.py:133–161](eco-route/backend/app/main.py#L133-L161) |
| GET `/v1/proposals/{pid}` | Read owned proposal | Proposal | O | IMPLEMENTED. Reading does not expire/revalidate it. [main.py:163–166](eco-route/backend/app/main.py#L163-L166) |
| POST `/v1/proposals/{pid}/approve` | Commit pending proposal: `idempotency_key` (8–128 chars) | `schedule_id`, incremented `revision`, `idempotent_replay` | O | IMPLEMENTED approval safeguards, subject to limitations below. Expired → 410; nonpending/stale/failed validation/key collision → 409. [main.py:168–172](eco-route/backend/app/main.py#L168-L172), [service.py:176–220](eco-route/backend/app/service.py#L176-L220) |
| POST `/v1/proposals/{pid}/reject` | Reject pending proposal: optional `reason` | `proposal_id`, `status:"rejected"` | O | IMPLEMENTED; other statuses → 409. [main.py:174–178](eco-route/backend/app/main.py#L174-L178), [service.py:222–227](eco-route/backend/app/service.py#L222-L227) |
| GET `/v1/schedules/{sid}/revisions` | Read history | Array of `{id,revision_number,snapshot,reason,created_at}`, newest first | O | IMPLEMENTED read-only history; no restore endpoint. [main.py:180–185](eco-route/backend/app/main.py#L180-L185) |
| GET `/v1/workflows/status` | Query `execution_arn`, optional `user_id` | `execution_arn`, AWS `status`, `started_at`, `stopped_at`, `result`, `error`, `cause` | O | PARTIAL/config-dependent: actual Step Functions status call; disabled → 503; owner checked from execution input. [main.py:254–257](eco-route/backend/app/main.py#L254-L257), [workflows.py:42–69](eco-route/backend/app/workflows.py#L42-L69) |

### Preferences, routines, and utility endpoints

| Method / endpoint | Purpose and inputs | Output | Auth | Status / evidence |
|---|---|---|---|---|
| GET `/v1/preferences` | List user's preferences; query `user_id` | Array `{id,key,value,confidence,source,updated_at}` | O | IMPLEMENTED. [main.py:187–191](eco-route/backend/app/main.py#L187-L191) |
| POST `/v1/preferences` | Upsert `key`, `value` object; optional `confidence` (0–1), `source`, `user_id` | `{id,user_id,key,value,confidence,source}` | O | IMPLEMENTED storage; only `travel_mode` affects planning. [main.py:193–202](eco-route/backend/app/main.py#L193-L202), [service.py:126–129](eco-route/backend/app/service.py#L126-L129) |
| PUT `/v1/preferences/{key}` | Replace existing value/confidence/source; query `user_id` | `{id,key,value,confidence,source,updated_at}` | O | IMPLEMENTED; missing → 404. [main.py:204–212](eco-route/backend/app/main.py#L204-L212) |
| DELETE `/v1/preferences/{key}` | Delete key; query `user_id` | 204, no body | O | IMPLEMENTED; missing → 404. [main.py:214–220](eco-route/backend/app/main.py#L214-L220) |
| GET `/v1/routines` | List routines; query `user_id` | Array `{id,name,weekday,stop,active,created_at}` | O | IMPLEMENTED CRUD. [main.py:222–226](eco-route/backend/app/main.py#L222-L226) |
| POST `/v1/routines` | `routine:{name,weekday:0..6,stop:Stop,active:true}`, optional `user_id` | 201 `{id,name,weekday,stop,active}` | O | IMPLEMENTED storage; schedule expansion has limitations below. [main.py:228–234](eco-route/backend/app/main.py#L228-L234), [schemas.py:18–22](eco-route/backend/app/schemas.py#L18-L22) |
| PUT `/v1/routines/{routine_id}` | Replace full `routine` object, optional `user_id` | `{id,name,weekday,stop,active}` | O | IMPLEMENTED; owner/missing → 404. [main.py:236–244](eco-route/backend/app/main.py#L236-L244) |
| DELETE `/v1/routines/{routine_id}` | Delete routine; query `user_id` | 204, no body | O | IMPLEMENTED. [main.py:246–252](eco-route/backend/app/main.py#L246-L252) |
| GET `/` | API identity; no input | `{name:"EcoRoute API",docs:"/docs"}` | Public | IMPLEMENTED. [main.py:64–65](eco-route/backend/app/main.py#L64-L65) |
| GET `/app` | Serve bundled planner | HTML file | Public | IMPLEMENTED static UI. [main.py:67–68](eco-route/backend/app/main.py#L67-L68) |
| GET `/app/{asset}` | Serve `app.js` or `style.css` only | JS/CSS file; other assets → 404 | Public | IMPLEMENTED allowlist. [main.py:70–74](eco-route/backend/app/main.py#L70-L74) |
| GET `/health` | Process health; no input | `{status:"ok"}` | Public | IMPLEMENTED, no dependency check. [main.py:75–76](eco-route/backend/app/main.py#L75-L76) |
| GET `/ready` | DB connectivity check; no input | `{status:"ready"}`; DB failure → 503 | Public | IMPLEMENTED `SELECT 1`; does not check schema, AI, Cognito, or routing. [main.py:78–84](eco-route/backend/app/main.py#L78-L84) |

FastAPI is instantiated with default documentation settings: framework-provided GET `/openapi.json`, `/docs`, `/docs/oauth2-redirect`, and `/redoc` are expected, public utility routes; they are not among the 32 explicit handlers. No source override disables them. CORS middleware handles qualifying OPTIONS preflights with all origins/methods/headers allowed and credentials disabled. Evidence: [main.py:29–30](eco-route/backend/app/main.py#L29-L30). These framework routes were not runtime enumerated.

No explicit endpoints for schedule listing/deletion/general editing, stop deletion/completion, arbitrary order submission, conversation sessions, audio, transit itineraries, route geometry, or EV data. The explicit route inventory above is exhaustive for `app/main.py`.

## 2. AI capabilities

| Capability | Verified implementation | Limit |
|---|---|---|
| Understand text | Mantle via OpenAI-compatible `chat.completions.create`; typed intent validation. Without credentials, local regex/keyword parser. | Model accuracy is untested. Local parser routes most nonempty text to destination search. [integrations.py:52–151](eco-route/backend/app/integrations.py#L52-L151) |
| Execute actions | Destination search or create a replan proposal on an existing schedule. | No autonomous selection, schedule commit, approval, or tool for task creation. [main.py:146–161](eco-route/backend/app/main.py#L146-L161) |
| Extract multiple vague tasks | **MISSING**: schema has one `operation`, one `destination_query`, optional `budget_inr` and clarification fields. | A request like “groceries, pharmacy, then office before 10” has no task-list output/execution loop. Actual model response to that wording was not tested. [strands_agent.py:11–16](eco-route/backend/app/strands_agent.py#L11-L16) |
| Create a schedule conversationally | Can classify `create_schedule`. | Handler returns clarification; worker state machine asks for details. Neither converts text into ScheduleCreate or calls `create_schedule`. [main.py:149–161](eco-route/backend/app/main.py#L149-L161), [planning.asl.json:139–146](eco-route/backend/infra/step-functions/planning.asl.json#L139-L146) |
| Clarification | Returns `status:"clarification_required"`, `question`, `intent`. | Stateless: no history or linkage to previous question. Frontend must retain context/resubmit a self-contained request. No targeted clarification if replan matching is ambiguous. [schemas.py:72–77](eco-route/backend/app/schemas.py#L72-L77), [main.py:146–161](eco-route/backend/app/main.py#L146-L161), [integrations.py:153–174](eco-route/backend/app/integrations.py#L153-L174) |
| Destination suggestions | Text search with bias toward schedule **start location**, at most 10 results through API routes. | No along-route search, user-current-position tracking, feasibility/price/stock/open-hours ranking, or automatic best-place selection. [main.py:151–154](eco-route/backend/app/main.py#L151-L154), [integrations.py:14–23](eco-route/backend/app/integrations.py#L14-L23) |
| Natural-language replanning | Regex extracts a positive duration extension in minutes and matches exactly one stop by title/type, or a single fixed appointment fallback. | “Meeting moved to 3pm” / “running late” may classify as replan but produce `{}` updates; no time parsing or delay application. Ambiguous duration requests also produce `{}`. [integrations.py:143–144](eco-route/backend/app/integrations.py#L143-L144), [integrations.py:153–174](eco-route/backend/app/integrations.py#L153-L174) |
| Budget understanding | Extracts/returns `budget_inr`. | Budget is not applied to place search or planner constraints. [integrations.py:147–151](eco-route/backend/app/integrations.py#L147-L151), [main.py:149–160](eco-route/backend/app/main.py#L149-L160) |
| Strands agent | Optional new agent per request; only tool is `search_places_tool`, default max 8 search calls; structured final intent. | Search tool results are not returned as the endpoint's candidate list; handler searches again using final query. Requires Mantle and Amazon Location. [strands_agent.py:19–78](eco-route/backend/app/strands_agent.py#L19-L78), [main.py:138–154](eco-route/backend/app/main.py#L138-L154) |

Dispatch priority is **Step Functions → Strands → direct intent parser**. The Step Functions worker always calls `parse_intent`, so enabling Step Functions bypasses Strands even if both flags are true. The asynchronous workflow ends after clarification, discovery, or proposal creation; it does not wait for approval or execute stops. [main.py:136–145](eco-route/backend/app/main.py#L136-L145), [workflow_worker.py:13–17](eco-route/backend/app/workflow_worker.py#L13-L17), [planning.asl.json:30–156](eco-route/backend/infra/step-functions/planning.asl.json#L30-L156).

## 3. Planning and optimization

### Destination selection and ordering algorithms

| Operation | Actual algorithm | Scope / consequence |
|---|---|---|
| Destination discovery | Return Amazon Location text-search results in provider order; user chooses coordinates/place. | Planner does not select shops for tasks or jointly optimize alternative destinations. [integrations.py:14–23](eco-route/backend/app/integrations.py#L14-L23), [main.py:149–154](eco-route/backend/app/main.py#L149-L154) |
| Preview / create | `optimize_schedule`: bounded enumeration of stop permutations for ≤8 stops. Preview default 500 evaluations, configurable to 5000; create fixed at 500. | More than 8 stops: **only input order** evaluated. Search truncation may hide feasible/better orders; no global optimality guarantee. [planner.py:238–277](eco-route/backend/app/planner.py#L238-L277), [service.py:55](eco-route/backend/app/service.py#L55), [schemas.py:54–55](eco-route/backend/app/schemas.py#L54-L55) |
| Initial-plan objective | Minimize `travel_minutes + 0.1*distance_km + 2*disruption + 0.25*waiting_minutes`; ties by stop-ID sequence. | Hardcoded weights; disruption counts positions changed from input. Not fuel/emissions/transit cost. [planner.py:258–262](eco-route/backend/app/planner.py#L258-L262) |
| Add one destination | `plan`: test insertion at each position in current order, bounded by 500 in service. | Existing stops are not reordered, even with reordering enabled. [planner.py:190–199](eco-route/backend/app/planner.py#L190-L199), [service.py:131–150](eco-route/backend/app/service.py#L131-L150) |
| Replan | Check input order first, then unchanged order plus independent swaps between consecutive entries in the flexible-index list. Fixed-start stops are excluded from swapping. | At most `max_reordered_stops` swap candidates (default 3); these are single swaps from original, not iterative search or a bound on moved stops. Flexible indices may be separated by fixed stops. [planner.py:168–188](eco-route/backend/app/planner.py#L168-L188) |
| Change-proposal objective | Weighted normalized travel time (5), distance (1), disruption (4). | Waiting is not directly scored here. Replan `before` metrics are computed after applying requested updates, not from the original saved plan. [planner.py:170–173](eco-route/backend/app/planner.py#L170-L173), [planner.py:204–217](eco-route/backend/app/planner.py#L204-L217), [service.py:153–164](eco-route/backend/app/service.py#L153-L164) |
| Route caching | Cache directed coordinate pairs + mode inside a planning call. | No persistent cache or departure-time key; approval recalculates separately. [planner.py:220–235](eco-route/backend/app/planner.py#L220-L235) |

### Travel data and transport support

| Item | Actual support |
|---|---|
| Default travel | **MOCKED**: Haversine distance ×1.25; 4.5 km/h walking, 15 cycling, 25 car, plus 2 minutes for nonzero legs. [planner.py:21–31](eco-route/backend/app/planner.py#L21-L31) |
| AWS travel | Real `calculate_route` requests when AWS enabled and route calculator configured. Converts `DurationSeconds` to minutes, reads summary `Distance`. These are provider route estimates, not measured travel. [integrations.py:24–40](eco-route/backend/app/integrations.py#L24-L40) |
| Traffic / departure-aware travel | No departure timestamp, `DepartNow`, traffic options, or time-dependent route calculation supplied. No live incident/delay ingestion. Source labels `amazon_location` do not establish live traffic. [integrations.py:24–27](eco-route/backend/app/integrations.py#L24-L27) |
| Walking, bicycle, car | Implemented as one user preference `travel_mode:{mode:"Walking"\|"Bicycle"\|"Car"}` for the entire plan; unknown values silently fall back to Walking. No per-leg mode mixing/comparison. [service.py:13](eco-route/backend/app/service.py#L13), [service.py:126–135](eco-route/backend/app/service.py#L126-L135) |
| Bus, metro, suburban train | **MISSING**: no supported modes, transit feed/API, timetables, station/line/transfer data, fares, or boarding instructions. Mode whitelist and route adapter are the only transport implementations. |
| EV / fuel efficiency | **MISSING**: car mode has no battery, range, consumption, vehicle, charging-stop, fuel-cost, elevation, or emissions model. [planner.py:12–14](eco-route/backend/app/planner.py#L12-L14), [service.py:13](eco-route/backend/app/service.py#L13), [planner.py:212](eco-route/backend/app/planner.py#L212) |
| Map data | Ordered stop coordinates and start/end locations are available. No polyline, geometry, turn instructions, map tiles, or map-specific endpoint; `IncludeLegGeometry=False`. Summary distance is labeled km internally; request does not explicitly set/check returned distance units. [integrations.py:24–27](eco-route/backend/app/integrations.py#L24-L27), [planner.py:151–165](eco-route/backend/app/planner.py#L151-L165) |

When AWS routing is enabled but missing/malfunctioning, errors propagate to 502/503 paths; there is no automatic fallback to mocks. Exact `environment == "production"` blocks local mock routing, while authentication checks environment case-insensitively. Use lowercase production configuration. [integrations.py:29–50](eco-route/backend/app/integrations.py#L29-L50), [auth.py:23](eco-route/backend/app/auth.py#L23).

### Deadlines, durations, and constraints

| Input | Actual enforcement |
|---|---|
| `earliest_start` | Wait until earliest start after travel. |
| `latest_start`, `latest_end` | Reject an order if start/finish exceeds deadline. |
| `fixed_start` | Must arrive by appointment time; wait when early; check earliest/latest compatibility. |
| `duration_minutes` | Explicit user-supplied service time added at each stop; not inferred from task/place. Validated in StopIn, but **not revalidated in replan updates**. |
| Schedule horizon | Stop times and final journey must fit `start_at`–`end_at`. Return travel counts toward travel total. |
| `opening_hours` | Only caller-supplied same-day `{open,close}` times. Does not fetch hours or wait automatically for opening; no weekly/overnight windows. |
| Hard `precedence` | Enforced only when both referenced stop IDs occur in plan. |
| Hard `max_travel_minutes` | Enforced including final leg; negative maximum is a conflict. |
| Other hard constraint types | **Ignored**; type is an arbitrary string, with no unsupported-type error. |
| Soft constraints / `weight` | Stored/accepted, but not enforced or included in objective. |
| `priority`, `mandatory` | Stored and editable, but do not drive scoring, optional-stop removal, or task selection. All supplied stops remain. |
| `status`, `attributes` | Stored metadata; no skip-completed or execution semantics. |
| Timezone / routine date | Offset-aware creation required. `timezone` string is stored/passed to AI, not used to convert planner times via a timezone database. Routine selection uses `date.weekday()` (Monday=0), without rebasing routine timestamps onto the new date. |

Evidence: [planner.py:34–138](eco-route/backend/app/planner.py#L34-L138), [schemas.py:12–52](eco-route/backend/app/schemas.py#L12-L52), [service.py:32–55](eco-route/backend/app/service.py#L32-L55), [service.py:153–164](eco-route/backend/app/service.py#L153-L164), [planner.py:204–217](eco-route/backend/app/planner.py#L204-L217), [planner.py:258–259](eco-route/backend/app/planner.py#L258-L259).

## 4. Human-in-the-loop behavior

1. User supplies a structured initial schedule; optional preview does not save it. `POST /v1/schedules` commits immediately as revision 1, without a proposal approval step.
2. Agent/place-search returns candidates. User must choose one and supply a full Stop, including duration, to `/schedules/{sid}/stops`.
3. Adding or replanning saves a separate proposal with `base_revision`; schedule remains unchanged. Feasible proposals are `pending`; others are `infeasible`.
4. Approval accepts only pending proposals, checks expiry (default 30 minutes), owner and revision, revalidates current/proposed plans, uses locking plus a conditional revision update, replaces stops, and records a new revision. Idempotency key replays return the earlier revision.
5. Rejection changes proposal status; it does not change schedule. Other pending proposals become stale when approval detects a revision mismatch. No proactive expiry/staleness worker.

Evidence: [service.py:32–76](eco-route/backend/app/service.py#L32-L76), [service.py:137–169](eco-route/backend/app/service.py#L137-L169), [service.py:176–227](eco-route/backend/app/service.py#L176-L227), [config.py:25](eco-route/backend/app/config.py#L25).

| User change | Available now? |
|---|---|
| Choose a destination / add another stop | Yes, one chosen stop per proposal. |
| Change stop duration, earliest/latest start/end, fixed start, priority, mandatory | Yes, by stop ID in `replan.updates`; priority/mandatory have no optimization effect. |
| Ask to extend one identifiable meeting | Yes, limited minutes-extension regex. |
| Change global travel mode | Yes, via preference; applies to later computations without proposal approval. |
| Change routine/preferences | Yes, CRUD; does not update already saved schedules automatically. |
| Edit proposal contents directly | No; reject/regenerate using supported inputs. |
| Delete an existing stop, replace its location/title, mark complete, drag to an exact order | No endpoint/update field. |
| Edit existing schedule's date/horizon/start/end locations or persisted constraints | No general edit endpoint. Request constraints affect proposal computation only. |
| Restore an older revision / automatically react to GPS, traffic, missed task | No restore/event-driven replan implementation. |

Evidence: [service.py:153–164](eco-route/backend/app/service.py#L153-L164), [main.py:123–257](eco-route/backend/app/main.py#L123-L257).

### Material limitations and source-backed defects

| Finding | Evidence and practical impact | Verification level |
|---|---|---|
| Replan cannot rescue an infeasible current order | `plan` returns before generating swaps if input order violates constraints. Duration changes can make an otherwise repairable schedule immediately `infeasible`. [planner.py:170–188](eco-route/backend/app/planner.py#L170-L188) | Source + synthetic: A→B fails; B→A feasible under `optimize_schedule`, but `plan` refuses search. |
| Replan value validation bypass | Allowed field names are checked, but values are assigned from `dict[str,Any]` without StopIn validation. Negative durations can pass; bad types can cause a generic 502. [schemas.py:64–70](eco-route/backend/app/schemas.py#L64-L70), [service.py:157–168](eco-route/backend/app/service.py#L157-L168) | Source + synthetic planner acceptance of `duration_minutes=-10`; full endpoint not executed. |
| Added constraints are not saved or rechecked at approval | Request constraints are merged for planning, but proposal stores no constraint set; approval revalidates only persisted ScheduleConstraint rows and writes no new constraints. They do not govern future replans. [service.py:131–139](eco-route/backend/app/service.py#L131-L139), [service.py:194–216](eco-route/backend/app/service.py#L194-L216), [models.py:73–87](eco-route/backend/app/models.py#L73-L87) | Verified source behavior. |
| Ambiguous/moved/late request can create a no-op proposal | `infer_replan_updates` returns `{}` without clarification; handler still calls replan. It may propose unchanged stops. [integrations.py:153–174](eco-route/backend/app/integrations.py#L153-L174), [main.py:155–160](eco-route/backend/app/main.py#L155-L160) | Source + synthetic unchanged-plan feasibility. |
| Routine-generated stop IDs conflict with persistence design | ID is `routine-` + UUID (44 chars), while Stop PK is `String(36)`; same routine ID is reused across schedules despite a global Stop PK. [service.py:43–49](eco-route/backend/app/service.py#L43-L49), [models.py:23–26](eco-route/backend/app/models.py#L23-L26) | Source-backed DB failure risk: PostgreSQL length enforcement and second-schedule PK collision not integration-tested. |
| SQLite timezone round-trip risk | DB fields use DateTime(timezone=True), default DB is SQLite, and `row_stop` only calls `.isoformat()`. No offset-restoration logic exists; planner rejects naive schedule + aware stop combinations. [db.py:36–39](eco-route/backend/app/db.py#L36-L39), [models.py:15–16](eco-route/backend/app/models.py#L15-L16), [service.py:20–21](eco-route/backend/app/service.py#L20-L21), [planner.py:34–44](eco-route/backend/app/planner.py#L34-L44) | Synthetic planner mismatch reproduced; actual SQLite round trip not run. |
| Preview is not an immutable offer | Preview budget can be 5000; create always reruns at 500 and does not accept a preview token. Result may differ or fail; saving preview stop IDs also risks reuse against global Stop PK. [schemas.py:54–55](eco-route/backend/app/schemas.py#L54-L55), [service.py:50–55](eco-route/backend/app/service.py#L50-L55), [models.py:25](eco-route/backend/app/models.py#L25) | Verified source design; runtime outcome depends on inputs. |
| Invalid timing rows can misalign infeasible timeline | `validate` skips a stop on parsing errors; `metrics` pairs original stops with timing rows using `zip`. An invalid earlier stop can shift later timing attribution. [planner.py:92–94](eco-route/backend/app/planner.py#L92-L94), [planner.py:150–163](eco-route/backend/app/planner.py#L150-L163) | Source-backed edge case; not exercised. |

## 5. Infrastructure, external APIs, and persistence

### Integrated services

| Service / component | Actual integration | Configuration / limitations |
|---|---|---|
| Amazon Location Service | boto3 `search_place_index_for_text`, `calculate_route` | AWS flag plus place index/route calculator; no provisioned-resource verification. [integrations.py:11–50](eco-route/backend/app/integrations.py#L11-L50) |
| Amazon Bedrock Mantle | OpenAI-compatible Chat Completions; configurable API key/base URL/model/project; optional Strands OpenAIModel | Default base URL targets ap-south-1 Mantle; default model `openai.gpt-oss-safeguard-20b`. No boto3 Bedrock invoke path. A configurable URL could target another compatible service; no separate OpenAI-hosted service is proven. [config.py:15–22](eco-route/backend/app/config.py#L15-L22), [integrations.py:52–89](eco-route/backend/app/integrations.py#L52-L89) |
| Amazon Cognito | Signup/confirm/resend/password-login/refresh, JWKS verification | Pool and client IDs; no local account DB, MFA completion, or password-reset flow. [cognito.py:8–93](eco-route/backend/app/cognito.py#L8-L93), [auth.py:11–61](eco-route/backend/app/auth.py#L11-L61) |
| AWS Step Functions | `start_execution`, `describe_execution`; ASL routes interpret/discover/replan to Lambda | Disabled by default; ARN and deployed definition required. No human callback/approval state. [workflows.py:19–69](eco-route/backend/app/workflows.py#L19-L69), [planning.asl.json:1–158](eco-route/backend/infra/step-functions/planning.asl.json#L1-L158) |
| AWS Lambda / API Gateway compatibility | Mangum ASGI handler and separate workflow Lambda handler | API Gateway is compatible hosting, not an SDK integration or verified deployment. ASL contains `${workflow_lambda_arn}` requiring substitution. [lambda_handler.py:1–6](eco-route/backend/app/lambda_handler.py#L1-L6), [workflow_worker.py:67–74](eco-route/backend/app/workflow_worker.py#L67-L74), [planning.asl.json:9](eco-route/backend/infra/step-functions/planning.asl.json#L9) |
| AWS Secrets Manager / PostgreSQL | Fetch JSON DB credentials, construct psycopg URL; default SQLite fallback | Cached secret retrieval at module initialization; not RDS Data API, no automatic rotation refresh. RDS can host this Postgres DB; RDS deployment not established by code. [db.py:14–39](eco-route/backend/app/db.py#L14-L39) |
| Docker / Alembic | Python container, Postgres 16 compose service, startup migration | Compose explicitly disables AWS; no named persistent Postgres volume. Initial migration uses current model metadata `create_all`; no follow-up schema-evolution migrations. [docker-compose.yml:1–23](eco-route/backend/docker-compose.yml#L1-L23), [Dockerfile:1–11](eco-route/backend/Dockerfile#L1-L11), [main.py:19–27](eco-route/backend/app/main.py#L19-L27), [0001_initial.py:1–15](eco-route/backend/migrations/versions/0001_initial.py#L1-L15) |

No executable integrations found for Google Maps, Mapbox, transit feeds/GTFS, OpenRouteService, speech/transcription services, EV/charging APIs, DynamoDB, S3, queues, or event-triggered replanning. No complete Terraform/CloudFormation/CDK deployment definition exists in the inspected backend file inventory; `infra/` contains Lambda requirements and the workflow JSON.

### Persisted data

| SQL table | Stored content | Evidence |
|---|---|---|
| `schedules` | Owner, date/timezone/horizon, start/end coordinates, status/revision, creation timestamp | [models.py:9–21](eco-route/backend/app/models.py#L9-L21) |
| `schedule_stops` | Ordered stops, location, duration, windows/fixed time, opening hours, priority/mandatory/status/source/attributes | [models.py:23–41](eco-route/backend/app/models.py#L23-L41) |
| `schedule_constraints` | Type, hardness, weight, parameter JSON | [models.py:43–50](eco-route/backend/app/models.py#L43-L50) |
| `preferences` | Per-user key/value JSON, confidence/source/update time; unique user/key | [models.py:52–61](eco-route/backend/app/models.py#L52-L61) |
| `routines` | Per-user weekday, serialized stop, active flag, creation time | [models.py:63–71](eco-route/backend/app/models.py#L63-L71) |
| `plan_proposals` | Owner/schedule/base revision, status/operation, proposed stops, metrics/timelines, conflicts/facts, unique idempotency key, expiry | [models.py:73–87](eco-route/backend/app/models.py#L73-L87) |
| `plan_revisions` | Schedule/revision, snapshot JSON, reason, creation time; unique schedule/revision | [models.py:89–97](eco-route/backend/app/models.py#L89-L97) |

- Initial schedule metrics/timeline/source are transient Python attributes returned after creation, **not schedule-table columns**; GET timeline recomputes. Proposal metrics are persisted. [service.py:73–75](eco-route/backend/app/service.py#L73-L75), [service.py:114–124](eco-route/backend/app/service.py#L114-L124).
- Revision snapshots omit constraints and preferences; original replan `reason` is not saved as the revision reason—approval stores `Approved proposal <id>`. [service.py:28–30](eco-route/backend/app/service.py#L28-L30), [service.py:169](eco-route/backend/app/service.py#L169), [service.py:216](eco-route/backend/app/service.py#L216).
- No application tables for chat history, extracted tasks, audio, place-search cache, vehicles, transit services, or GPS events. Workflow payload includes raw request text in AWS execution input; local regex/LLM intent results are not separately persisted in SQL. [models.py:9–97](eco-route/backend/app/models.py#L9-L97), [workflows.py:24–35](eco-route/backend/app/workflows.py#L24-L35).

### Mocked, hardcoded, or incomplete

- **Default mock:** local travel formula/speeds; local keyword intent parser; place search returns empty rather than fake destinations. Auth, Strands, and Step Functions default off. [config.py:4–26](eco-route/backend/app/config.py#L4-L26), [integrations.py:29–44](eco-route/backend/app/integrations.py#L29-L44).
- **Hardcoded:** optimization weights, create/change budget 500, API candidate limit 10, mode whitelist; bundled UI gives suggested stops 30 minutes and uses a 5000-order preview. [service.py:13](eco-route/backend/app/service.py#L13), [service.py:55](eco-route/backend/app/service.py#L55), [service.py:135](eco-route/backend/app/service.py#L135), [web/app.js:263](eco-route/backend/web/app.js#L263), [web/app.js:355](eco-route/backend/web/app.js#L355).
- **Deployment assumptions:** PowerShell scripts name particular Lambda/location/database resources; these are configuration scripts, not evidence those services are healthy. Lambda requirements omit `strands-agents`, which is present in general requirements; a Lambda package built only from that manifest needs dependency changes before enabling Strands. [scripts/configure_aws_mantle.ps1:19–45](eco-route/backend/scripts/configure_aws_mantle.ps1#L19-L45), [scripts/start_mantle_smoke.ps1:17–31](eco-route/backend/scripts/start_mantle_smoke.ps1#L17-L31), [infra/lambda-requirements.txt:1–10](eco-route/backend/infra/lambda-requirements.txt#L1-L10), [requirements.txt:12](eco-route/backend/requirements.txt#L12).

## 6. Feature gap analysis against the vision

| Vision feature | Status | Implemented portion / gap | Evidence |
|---|---|---|---|
| Conversational task planning | **PARTIAL** | Stateless single-intent requests and clarification responses; no dialogue state or conversational schedule construction. | [main.py:133–161](eco-route/backend/app/main.py#L133-L161), [schemas.py:72–77](eco-route/backend/app/schemas.py#L72-L77) |
| Voice transcription | **MISSING** | Text input only; no audio endpoint, speech SDK, or browser speech integration found. | [schemas.py:72–77](eco-route/backend/app/schemas.py#L72-L77), [main.py:133–161](eco-route/backend/app/main.py#L133-L161) |
| Automatic task extraction | **MISSING** | Intent/query classification exists; no multiple-task schema, extraction loop, or conversion to stops with durations/deadlines. | [strands_agent.py:11–16](eco-route/backend/app/strands_agent.py#L11-L16) |
| Intelligent nearby destination suggestions | **PARTIAL** | AWS text-search candidates with start-location bias; no along-route, feasibility, availability, price, or preference ranking. | [main.py:149–154](eco-route/backend/app/main.py#L149-L154), [integrations.py:14–23](eco-route/backend/app/integrations.py#L14-L23) |
| Multi-stop transit optimization | **PARTIAL** | Multi-stop ordering exists for one walking/bicycle/car mode. Public-transit optimization itself is **missing**. | [planner.py:238–277](eco-route/backend/app/planner.py#L238-L277), [service.py:13](eco-route/backend/app/service.py#L13) |
| Bus/metro/train recommendations | **MISSING** | No transit mode, provider, schedule, transfer, station, fare, or recommendation implementation. | [service.py:13](eco-route/backend/app/service.py#L13), [integrations.py:24–40](eco-route/backend/app/integrations.py#L24-L40) |
| Fuel/EV efficiency | **MISSING** | Generic car travel estimates only; no efficiency/energy/charging model. | [planner.py:12–31](eco-route/backend/app/planner.py#L12-L31), [planner.py:258–259](eco-route/backend/app/planner.py#L258-L259) |
| Map waypoints | **PARTIAL** | Ordered coordinates ready for frontend markers; no backend route geometry/map view. | [main.py:110–116](eco-route/backend/app/main.py#L110-L116), [integrations.py:25](eco-route/backend/app/integrations.py#L25) |
| Dynamic replanning | **PARTIAL** | Explicit duration/time-window update proposals, limited swaps, approval and revisions. No continuous triggers; infeasible-input early exit limits repair. | [service.py:153–169](eco-route/backend/app/service.py#L153-L169), [planner.py:168–188](eco-route/backend/app/planner.py#L168-L188) |
| Structured schedule preview/create | **IMPLEMENTED** | Bounded order optimization, supported hard deadlines, timeline, persistence; development routes mocked. | [service.py:32–107](eco-route/backend/app/service.py#L32-L107) |
| Human approval/rejection/history | **IMPLEMENTED** | Proposals, ownership, expiry/revision checks, idempotency and history; caveats above. | [service.py:176–227](eco-route/backend/app/service.py#L176-L227), [main.py:180–185](eco-route/backend/app/main.py#L180-L185) |

## 7. React frontend integration

**Current React state:** `src/App.jsx` renders a Vite starter/counter, not EcoRoute features. No API client or EcoRoute integration exists there. Backend `web/app.js` is a separate vanilla-JavaScript implementation with `fetch`, auth, place search, preview/save, workflow polling, and proposal handling. [src/App.jsx:1–122](src/App.jsx#L1-L122), [web/app.js:22–48](eco-route/backend/web/app.js#L22-L48), [web/app.js:330–409](eco-route/backend/web/app.js#L330-L409), [web/app.js:435–465](eco-route/backend/web/app.js#L435-L465).

| Integrate immediately | Frontend work and constraints |
|---|---|
| Structured itinerary form and timeline | Collect coordinates, offset-aware time window, explicit stops/durations/deadlines. Call preview, show feasibility/conflicts/source/truncation, then create. Read persisted order and recalculate timeline after saving. |
| Walking / bicycle / car selector | Upsert `travel_mode` preference **before** preview/create/replan. Mode is user-global, not in ScheduleCreate. |
| Place picker | Call search with coordinate bias; handle empty local results and configuration/service failures. Map selected result to Location fields only: do not pass `title`/`categories` inside Location, whose schema forbids extra fields. |
| Text agent panel | Send complete text plus existing schedule ID. Render clarification, candidate list, or Proposal. If `execution_arn` appears, poll workflow status and unwrap `result` on `SUCCEEDED`. Initial response `running` is lowercase; poll statuses are AWS uppercase. |
| Review and approval | User picks destination, supplies duration/deadlines, requests insertion, then approves/rejects. Retain one idempotency key per approval action across retries; refetch saved schedule/timeline after approval. Handle 409/410 explicitly. |
| Preferences, routines, revisions | CRUD and history screens can use existing endpoints. Apply routine-ID/date cautions; retain created schedule IDs because no list endpoint exists. |
| Cognito account forms | Connect signup/confirmation/login/refresh/me once configured. Handle unsupported additional challenges; retain old refresh token if refresh returns null. Development can use explicit local `user_id` without bearer. |
| Map markers | Use saved ordered stop coordinates plus schedule start/end; map SDK/rendering is frontend work. Do not present straight marker connections as computed road/transit geometry. |

Relevant contracts and existing examples: [schemas.py:5–105](eco-route/backend/app/schemas.py#L5-L105), [main.py:86–257](eco-route/backend/app/main.py#L86-L257), [web/app.js:153–202](eco-route/backend/web/app.js#L153-L202), [web/app.js:349–409](eco-route/backend/web/app.js#L349-L409).

| Requires backend changes | Concrete requirement |
|---|---|
| Conversational planning / vague multiple tasks | Task-list extraction schema, durations/deadlines/location resolution, dialogue state and clarification continuation, structured schedule creation dispatch. |
| Better destination recommendations | Multiple candidate places per task, nearby/along-route search, explicit suitability/feasibility ranking and verified opening/availability data where needed. |
| Reliable dynamic replanning | Search even when updated input order is infeasible; improve search scope, validate update values, return clarification for ambiguous/no-op updates. |
| Consistent approvals and constraints | Persist proposal constraint changes and revalidate them at approval; support intentional edits to stored constraints. |
| Rich editing | Schedule list/edit/delete, stop remove/relocate/title/status updates, explicit order and revision restore endpoints. |
| Transit / EV / route display | Transit provider/feed integration and transfer/time-aware model; EV/fuel inputs and objectives; route geometry response. |
| Voice | Add transcription endpoint/provider if server-side speech is required. A separately implemented browser speech path could produce text without changing existing agent input. |
| Routine / deployment robustness | Fix generated stop IDs/global reuse, rebase routine windows, verify SQLite/Postgres timezone handling, package Strands for Lambda if enabled. |

**Temporary mocks for a demo:** clearly label place candidates when AWS is unavailable; extracted multi-task lists and ongoing dialogue until task extraction exists; transcription if no speech provider is connected; bus/metro/train lines, fares/ETAs/transfers; EV consumption/charging/CO₂; traffic/GPS-triggered changes; geometry if showing a route before a real geometry integration. Use the real structured planner, proposals, approval flow, and CRUD where supported. Mock outputs must not be presented as measured travel or live service data.

### Validation record

| Check performed in this audit | Result |
|---|---|
| AST route enumeration of `app/main.py` | **PASS:** 32 explicit handlers accounted for in the inventory. |
| Infeasible input order vs repairable alternative | **PASS:** isolated `plan` rejected A→B while `optimize_schedule` found B→A feasible. |
| Unvalidated negative stop duration | **PASS:** planner accepted -10 minutes, confirming need for replan value validation. |
| Unsupported hard constraint | **PASS:** ignored by planner. |
| Arrival before opening | **PASS:** rejected rather than waiting for opening. |
| Nine-stop optimizer | **PASS:** evaluated one order and reported truncation. |
| Naive horizon + offset-aware stop | **PASS:** produced invalid-input conflict; database round trip remains untested. |
| Unchanged replan input | **PASS:** returned a feasible result, supporting no-op proposal risk. |
| Supplied test source review | SQLite fixtures and mocked AWS/Strands/Mantle clients found; tests were **not run**. [tests/conftest.py:13–38](eco-route/backend/tests/conftest.py#L13-L38), [tests/test_aws_integrations.py:70–167](eco-route/backend/tests/test_aws_integrations.py#L70-L167), [tests/test_aws_integrations.py:185–247](eco-route/backend/tests/test_aws_integrations.py#L185-L247). |
| Live AWS, actual AI quality, PostgreSQL, HTTP app, concurrency | **NOT VERIFIED.** Source integration and mocked tests do not establish operational readiness. |
