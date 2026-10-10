# EcoRoute frontend

A mobile-first React / Vite frontend with a monochrome conversational home, guided scheduling, backend place discovery, an itinerary, and explicit review of plan changes. All application modules, styles, components, hooks, utilities, and API services live under `src/`.

## Preparation by the project owner

1. Supply the four approved dependencies listed in `MISSING_PACKAGES.md`. The implementation targets Tailwind 4 and React Router 7. Package manifests and the lockfile were left unchanged.
2. Copy `.env.example` to a local Vite environment file and fill in `VITE_API_BASE_URL` with an absolute API base URL. The frontend appends `/v1/...` paths; do not include `/v1` in the base. No deployed URL is hardcoded.
3. Use a browser with native dialog, Fetch, AbortController, Intl timezones, and modern CSS support. HTTPS or localhost is needed for browser geolocation and secure identifier generation.
4. Perform your installations, builds, and runtime validation. No commands for these activities were executed during implementation.

Vite is configured with the React and Tailwind plugins. BrowserRouter is used; production hosting must serve `index.html` for client routes such as `/plan` and `/itinerary`.

## Screens and behavior

| Route | Behavior |
| --- | --- |
| `/` | Public conversational home, three quick actions, preserved request text, disabled microphone labeled coming soon |
| `/auth` | Cognito sign-up, email confirmation, resend code, sign-in, return to requested screen |
| `/plan` | Protected four-step builder: date/time, start/end search, individual stops, real preview and confirmed save |
| `/discover` | Protected real place search; optional user-initiated geolocation bias; plan-a-visit handoff |
| `/itinerary` | Protected active plan, saved schedule ID opener, timeline, revisions, proposals, agent assistant, neutral map placeholder |
| `/settings` | Protected travel mode, preferences CRUD, routines CRUD, revision history, sign-out |

Initial free text is a planning checklist; it is not sent to an invented multi-task planning service. Each destination is explicitly selected and configured. The same preview request body is submitted on confirmation. The backend recalculates and validates on creation, so returned travel estimates can change between preview and save.

Stop forms support duration, earliest start, latest start, finish deadline, appointment, priority, and mandatory status. Unsaved draft stops may be removed. Persisted stops expose only the supported replan fields; there is no completion, persisted deletion, or drag-and-drop ordering UI.

Preferences include one travel mode for the entire plan: walking, bicycle, or car. The backend reads the account preference whenever it calculates travel, even for existing plans. Refresh the itinerary after changing mode and review any feasibility changes. Other preference keys are editable in the advanced JSON editor; storage does not imply that they affect routing.

New saved routines use flexible timing, Monday = 0 through Sunday = 6, and are included on matching weekdays when opted into a preview or save. Existing routine time constraints are preserved when editing. The backend stores those as dated timestamps and does not shift them to later weeks.

## Integration and state

- `src/api/client.js` is the only Fetch boundary. It applies Cognito ID-token bearer authentication, JSON parsing, 204 handling, request cancellation, a 30-second request timeout, and API errors with backend validation conflicts. A protected 401 triggers one shared token-refresh operation and one retry. Other mutations are not automatically retried.
- Auth tokens remain in React-provider memory and are never logged or written to browser storage. Reloading requires sign-in again. Additional Cognito sign-in challenges and password reset have no supported backend workflows in the provided reference.
- Active schedule IDs are remembered in `sessionStorage`, scoped by authenticated subject. No schedule list or fabricated backend history is maintained. A known schedule ID can be pasted to reopen it. Draft forms and the original request stay in memory across navigation, survive guest-to-sign-in navigation, and clear on sign-out or reload.
- `useWorkflowPolling` checks one execution every two seconds while running, stops after roughly two minutes of client checking, cancels requests on unmount, and supports pausing and resuming the same execution. Pausing stops browser checking, not the backend workflow. The active ARN is retained in session storage until success or a new request; diagnostics show that ARN. Synchronous backend responses are also accepted.
- The assistant displays the latest independent request and result. Clarification answers must be incorporated into a revised complete request. It does not simulate server conversation memory. Place candidates require explicit selection, a title, and a duration before creating an add-stop proposal.
- The latest proposal ID per schedule is stored for reopening after dismissing the review or reloading. Opening it uses `GET /v1/proposals/{id}`. Proposal approval refreshes the proposal and current schedule first, checks expiry and revision, and sends a secure 8–128 character idempotency key. Uncertain retries reuse the same key, including after reloading when session storage is available. An already approved proposal is reconciled by refreshing the itinerary. Infeasible proposals cannot be approved. Rejection preserves the saved plan. Closing a review leaves the proposal pending for later review.
- Approval refreshes schedule and timeline; revision history fetches its endpoint whenever opened and when an open history view observes a new revision. Mismatched schedule/timeline revisions produce a refreshable error instead of combining inconsistent responses.
- Place search debounces by 350 ms, aborts superseded requests, handles empty and error results, supports keyboard selection, and supplies paired latitude/longitude bias when available. It never generates fallback places.

Newly entered timestamps are serialized with a timezone (`Z`), derived from local wall-clock inputs in the plan's IANA timezone. Unchanged existing timestamps retain their original offset and precision. New plans use the browser timezone; existing plans display and edit in their stored timezone. Nonexistent daylight-saving times are rejected through an Intl round trip. Ambiguous repeated times resolve deterministically; selecting a specific DST occurrence is not exposed.

## Layout and accessibility

Tailwind utilities provide the primary styling, including shared `@apply` styles in `src/index.css`. Layouts use fluid widths, small-screen columns, content-oriented breakpoints, safe-area padding, `100dvh`, wrapping text, and minimum touch-target sizes. Desktop itineraries show the complete plan on the left and the map placeholder on the right. Mobile offers collapsed, upcoming, and complete sheet states via accessible buttons; no gesture dependency is used.

Native modal dialogs contain focus and support Escape and focus restoration. Dialog bodies scroll within the viewport, including short landscape screens. The assistant scrolls its results independently of its bottom composer. Home and planner sticky controls remain in document flow. Reduced motion disables transitions and the loading indicator's rotation. Actual keyboard, assistive-technology, browser, and device behavior still requires runtime validation.

## Extension points and current limits

`ChatInput` is the future voice entry point; the mic is currently disabled. `MapPlaceholder` is the future real-map boundary. API modules isolate future backend capabilities. No voice, map provider, multi-task extraction, conversational memory, public transport instructions, or EV/fuel optimization is mocked.

The backend does not expose schedule listing or schedule deletion. Schedule creation and proposal creation have no documented idempotency contract: a manual retry after an uncertain network failure may create another resource. Only proposal approval has documented idempotency. Browser storage is optional; if unavailable, active state works in memory but cannot survive a reload. Only the most recent proposal/workflow is remembered for each schedule.

Travel is shown as an estimate. A `local_mock` response is explicitly labeled as a local development estimate. Neither place results nor the frontend verify business hours, inventory, or prices. The map intentionally contains no route geometry.

## Validation boundary

Every created or modified application source file was manually inspected for imports, JSX, hooks, API payloads, form validation, cancellation, navigation, responsiveness, dialog scrolling, and proposal approval behavior. No packages were installed, network requests made, application code executed, servers started, or tests, linters, type checkers, or builds run. The backend and Docker configuration were not modified. Source review is not runtime proof; see `IMPLEMENTATION_STATUS.md` for the handoff checklist and file inventory.
