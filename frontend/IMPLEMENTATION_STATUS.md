# EcoRoute implementation status

Frontend source implementation is complete for the supported workflows described below. Validation is manual source review only; runtime, browser rendering, backend connectivity, and executable checks are unverified.

## Implemented

- Minimal black-and-white home with a conversational composer and three quick actions.
- Account sign-up, confirmation, resend, sign-in, ID-token authentication, shared token refresh, protected routes, and sign-out.
- Progressive four-step schedule creation, individually configured destinations, backend preview, conflicts, metrics, and explicit save confirmation.
- Debounced real place search with cancellation, keyboard selection, loading/error/empty states, and optional coordinate bias.
- Active schedule recovery by account-scoped session storage or manually entered schedule ID.
- Saved schedule/timeline reads, feasibility, estimated travel, arrival/start/departure times, individual expandable stop details, and return leg.
- Three mobile itinerary sheet states; complete desktop itinerary on the left and a reusable neutral map placeholder on the right.
- Independent agent requests, clarification prompts, real destination candidates, duration capture, synchronous responses, asynchronous polling, resumable workflow checks, and ARN diagnostics.
- Add-stop and replan proposals, proposed ordering, before/after start-time differences, travel metrics, conflict display, explicit approval/rejection, expiry and revision checks, and idempotent approval recovery.
- Reopen the latest proposal and reload the itinerary after approval. Fetch actual revision history on demand.
- Walking/bicycle/car account preference, preference create/read/update/delete, routine create/read/update/delete and activation, and saved revision access.
- Fluid layouts, safe-area padding, dynamic viewport heights, short-screen scrolling, independently scrolling assistant results, native dialog focus containment, and reduced-motion styles.

## Files created

```text
.env.example
MISSING_PACKAGES.md
FRONTEND_README.md
IMPLEMENTATION_STATUS.md
src/api/client.js
src/api/auth.js
src/api/schedules.js
src/api/places.js
src/api/agent.js
src/api/proposals.js
src/api/preferences.js
src/api/routines.js
src/context/AuthContext.jsx
src/context/PlanContext.jsx
src/hooks/useWorkflowPolling.js
src/utils/dateTime.js
src/utils/formatters.js
src/utils/storage.js
src/components/ui/Button.jsx
src/components/ui/Input.jsx
src/components/ui/Modal.jsx
src/components/ui/BottomSheet.jsx
src/components/ui/LoadingState.jsx
src/components/ui/ErrorMessage.jsx
src/components/layout/AppLayout.jsx
src/components/layout/Header.jsx
src/components/layout/Navigation.jsx
src/components/chat/ChatInput.jsx
src/components/chat/ChatMessage.jsx
src/components/chat/ChatPanel.jsx
src/components/chat/DestinationSuggestions.jsx
src/components/planning/ScheduleForm.jsx
src/components/planning/PlaceSearch.jsx
src/components/planning/StopForm.jsx
src/components/planning/StopCard.jsx
src/components/planning/SchedulePreview.jsx
src/components/itinerary/ItinerarySheet.jsx
src/components/itinerary/Timeline.jsx
src/components/itinerary/TimelineStop.jsx
src/components/itinerary/ProposalReview.jsx
src/components/itinerary/ScheduleMetrics.jsx
src/components/itinerary/RevisionHistory.jsx
src/components/maps/MapPlaceholder.jsx
src/components/settings/PreferenceEditor.jsx
src/components/settings/RoutineForm.jsx
src/pages/AuthPage.jsx
src/pages/HomePage.jsx
src/pages/PlannerPage.jsx
src/pages/ItineraryPage.jsx
src/pages/DiscoverPage.jsx
src/pages/SettingsPage.jsx
```

Modified: `src/App.jsx`, `src/index.css`, `vite.config.js`, and `index.html`.

Removed: the unused starter `src/App.css`.

`src/main.jsx` was inspected and retained. Starter image assets are retained but no longer imported. Package manifests, lockfile, backend files, and Docker configuration are unchanged.

## Missing dependencies

`tailwindcss`, `@tailwindcss/vite`, `react-router-dom`, and `lucide-react`. See `MISSING_PACKAGES.md` for the expected APIs. Dependency installation is required before executable validation.

## Manual review performed

Reviewed every new or changed application source module and stylesheet directly, including follow-up edits. Compared endpoint paths, request fields, response arrays, timeline keys, nested proposal metrics, and supported update fields against `eco-route/backend/docs/frontend-api-workflows.md`, `app/schemas.py`, `app/main.py`, `app/service.py`, `app/planner.py`, and workflow/auth source. Reviewed Vite and HTML entry configuration.

Corrected account-change isolation, restoration of route state after sign-in, the complete desktop timeline, numbering in partial timelines, stale search cancellation, independent workflow resets, modal scroll locking, blank form values, proposal expiry/revision checks, and uncertain approval recovery by source inspection.

No executable validation was performed. No claims are made about successful compilation, measured responsiveness, accessibility conformance, backend success, performance, or browser compatibility.

## Known limitations

- The four dependencies and the API URL must be supplied by the project owner.
- Tokens are memory-only; reload requires sign-in. Draft forms also reset on reload.
- There is no backend schedule list/delete contract. Only the active ID is remembered; users can reopen a known ID.
- The latest workflow ARN and proposal ID are remembered per schedule, not a full activity history. Closing a review leaves it pending until resolved or expired.
- Schedule creation and proposal creation lack documented idempotency, so manual retry after an uncertain failure may create another resource.
- New routines use flexible timing. Existing routine timestamps are absolute and the backend does not rebase them for future dates.
- New plans use the browser timezone and a same-day window. Existing plans use their stored timezone. An explicit DST-occurrence selector is not provided.
- No fake voice, maps, route geometry, task extraction, chat memory, business verification, public transport, or EV features are present. The backend may return local development travel estimates, which are labeled.
- Modern browser APIs are assumed. Rendered layouts, mobile keyboards, dialog behavior, screen readers, and actual API responses have not been exercised.

## Suggested runtime handoff for the project owner

After supplying dependencies and environment configuration, validate sign-up/confirmation/sign-in, refresh and 401/403 handling, a real place search, feasible/infeasible previews, confirmed creation, route reload and ID restoration, agent clarification and workflow retry, destination addition, supported stop edits, approve/reject/expiry/stale-revision behavior, uncertain approval retries, preferences and routines CRUD, and revision refresh. Inspect narrow portrait and short landscape views, desktop split layout, keyboard-open composer behavior, native dialog focus, long place labels, and reduced motion. These checks remain unperformed.
