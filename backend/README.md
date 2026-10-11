# EcoRoute FastAPI backend

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Open `/app` for the day planner or `/docs` for the API. The planner lets users search for start,
end, and stop locations through Amazon Location (or enter coordinates), set durations, deadlines,
and fixed appointment times, then preview a bounded, constraint-checked itinerary before saving.
After saving, the same screen can send a place-search or replan request through the configured agent
workflow, evaluate a selected destination, and approve or reject the resulting proposal.
SQLite is the quick-start default. Startup applies Alembic migrations automatically;
set `AUTO_MIGRATE=false` when migrations are applied by a separate release step. To migrate manually,
run `python -m alembic upgrade head`. `docker compose up --build` runs PostgreSQL.

## AWS
Set `DATABASE_URL` to RDS PostgreSQL and configure `AWS_REGION`, `AWS_INTEGRATIONS_ENABLED=true`,
`BEDROCK_MODEL_ID`, `LOCATION_INDEX_NAME`, and `LOCATION_ROUTE_CALCULATOR_NAME`. Use an ECS task
role; don't put AWS access keys in source code. Enable Bedrock model access and provision an Amazon
Location place index and route calculator in the configured region.
For the OpenAI-compatible Bedrock Mantle API, set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and
`OPENAI_PROJECT_ID`; `BEDROCK_MODEL_ID=openai.gpt-oss-safeguard-20b` selects the model. The pinned
Strands Agents SDK uses `OpenAIModel` with this Mantle endpoint and structured outputs for
natural-language task extraction, intent classification, and replan interpretation. Keep the API
key only in the runtime's secret environment. For an AWS deployment, configure the same variables
on the API and workflow Lambda; setting them in a local PowerShell session does not update Lambda.
When AWS integrations are enabled, route and place provider failures are returned as errors;
the backend does not silently substitute local estimates. With integrations disabled, the
deterministic straight-line travel provider is intended only for local development. Set
`ENVIRONMENT=production` to make missing live route configuration fail closed.

For Cognito, configure `COGNITO_USER_POOL_ID` and `COGNITO_APP_CLIENT_ID`; production mode
requires authentication even if `AUTH_REQUIRED` is false. The planner supports `POST /v1/auth/signup`,
`POST /v1/auth/confirm`, `POST /v1/auth/resend-confirmation`, `POST /v1/auth/login`, and
`POST /v1/auth/refresh`. `GET /v1/auth/me` returns the signed-in Cognito subject as `user_id`.
The web planner stores tokens in browser local storage and sends the ID token as a bearer token.
Requests may omit `user_id` when authenticated; the API uses the verified Cognito `sub` as the
database owner. If a request supplies a different user ID, it is rejected. For local development
without authentication, requests still need an explicit `user_id`. The API verifies token signature,
issuer, expiry, token use, and app client against the pool JWKS. The runtime needs outbound HTTPS
access to the Cognito JWKS endpoint. Sign-up and sign-in use Cognito's public app-client operations;
they do not require IAM permissions on the API role.

For a Lambda and API Gateway deployment, package the API with `infra/lambda-requirements.txt` and
set the Lambda handler to `app.lambda_handler.handler`. This API Lambda is separate from the
Step Functions worker handler `app.workflow_worker.lambda_handler`.
Deploy backend code updates to the API and workflow Lambdas with `./scripts/deploy_backend.ps1` from PowerShell
(or `powershell -ExecutionPolicy Bypass -File .\scripts\deploy_backend.ps1`). The script verifies
the AWS account and Lambda runtime/architecture, builds a Python 3.12 x86_64 Linux package from the
requirements file, updates both functions, and waits for AWS to report each update complete. On
Windows, it uses the installed Ubuntu WSL distribution with Python 3.12 so Linux dependency markers
and Lambda-compatible wheels resolve correctly. It defaults to account `265134560414`, region
`ap-south-1`, and functions `ecoroute-api-286936` and `ecoroute-workflow-286936`; pass `-Profile`,
`-Region`, `-FunctionName` (one function), or `-FunctionNames` (a list) to choose a target. It
removes its temporary package and archive when it finishes.
The planner served from `web/` lets you save the API Gateway base URL in the browser after the
static files are uploaded to Amplify. Configure API Gateway CORS to allow all origins, methods,
and headers as well; the FastAPI CORS middleware cannot answer preflight requests intercepted by
the gateway itself.

To route natural-language requests through the Strands agent, set `STRANDS_AGENT_ENABLED=true` and
configure the Mantle credentials, model, and Amazon Location place index above. The agent uses the
OpenAI-compatible Mantle endpoint for inference and its only application tool searches candidate
places; it cannot write schedules or approve proposals. The deterministic planner and proposal
service remain authoritative. `STRANDS_MAX_TOOL_CALLS` caps place-search tool calls.

For asynchronous orchestration, set `STEP_FUNCTIONS_ENABLED=true` and
`STEP_FUNCTIONS_STATE_MACHINE_ARN`. `POST /v1/agent/requests` then starts an execution and returns
its ARN; `GET /v1/workflows/status?execution_arn=...&user_id=...` returns status and the state
machine's JSON result for that user. The state machine input includes `user_id`, `request_text`,
`schedule_id`, `timezone`, and `request_id`. Configure its definition and execution role to call
the backend planning tasks and return a JSON result. The API task role needs
`states:StartExecution` and `states:DescribeExecution` for that state machine. State machine
workers need their own least-privilege access to the database and any AWS integrations they use.
Step Functions stores execution input and output in its execution history; set retention and
logging policies accordingly. The sample definition is `infra/step-functions/planning.asl.json`;
replace `${workflow_lambda_arn}` with the deployed Lambda ARN before creating the state machine.
Deploy `app.workflow_worker.lambda_handler` as that Lambda (with the same application package and
configuration), and grant its role only the database, Bedrock, and Amazon Location access needed
by the workflow. The state machine role needs `lambda:InvokeFunction` on that worker. The sample
definition retries transient Lambda service errors and separates place discovery from replan
proposal generation. Give the worker role only the database-secret and Amazon Location permissions
it needs, and provide its Bedrock Mantle API key through protected Lambda configuration.

## Current MVP boundaries
The schedule planner validates hard appointment and time-window constraints before schedule creation,
checks precedence and maximum travel-time constraints, includes the return leg in route metrics, and
uses a bounded deterministic insertion search. New-schedule previews evaluate candidate stop orders,
cache route estimates for repeated legs, and return the timed itinerary, travel distance, and waiting
time. Previews do not persist a schedule; save only after reviewing the result. Proposals are
persisted without changing a schedule;
approval checks ownership, expiration, revision, and plan feasibility in a transaction. Explicit
travel-mode preferences affect route estimates. Weekly routines can be managed under `/v1/routines`
and included when creating a schedule.

Local development accepts `user_id` fields and query parameters when authentication is not
required. Production mode validates Cognito tokens. The service does not provision AWS resources
or a Step Functions state machine; the state machine definition and worker deployment must be
configured in your AWS account. Alembic migrations are included and applied on startup by default;
production deployments should apply them as a controlled release step with `AUTO_MIGRATE=false`.
The local development configuration uses SQLite and mock routing; it does not validate live AWS
permissions or resources. Local API and planner tests run with `python -m pytest -q`.

## Endpoints
- `POST /v1/auth/signup`
- `POST /v1/auth/confirm`
- `POST /v1/auth/resend-confirmation`
- `POST /v1/auth/login`
- `POST /v1/auth/refresh`
- `GET /v1/auth/me`
- `POST /v1/schedules/preview`
- `POST /v1/schedules`
- `GET /v1/places/search?query=...&latitude=...&longitude=...`
- `POST /v1/places/route-search` with `query`, `start_location`, and `end_location`; returns up to three matching places ranked by routed detour
- `POST /v1/agent/extract-tasks` with `text`, `date`, and `timezone`
- `GET /v1/schedules/{id}?user_id=...`
- `GET /v1/schedules/{id}/timeline?user_id=...`
- `POST /v1/schedules/{id}/stops?user_id=...`
- `POST /v1/schedules/{id}/replan?user_id=...`
- `POST /v1/agent/requests`
- `GET /v1/proposals/{id}?user_id=...`
- `POST /v1/proposals/{id}/approve`
- `POST /v1/proposals/{id}/reject`
- `GET /v1/schedules/{id}/revisions?user_id=...`
- `GET /v1/preferences?user_id=...`
- `POST /v1/preferences`
- `PUT /v1/preferences/{key}?user_id=...`
- `DELETE /v1/preferences/{key}?user_id=...`
- `GET /v1/routines?user_id=...`
- `POST /v1/routines`
- `PUT /v1/routines/{routine_id}`
- `DELETE /v1/routines/{routine_id}?user_id=...`
- `GET /ready`
- `GET /v1/workflows/status?execution_arn=...&user_id=...`

Route-aware place search accepts this body:

```json
{
  "query": "grocery store",
  "start_location": { "latitude": 13.0827, "longitude": 80.2707 },
  "end_location": { "latitude": 13.0569, "longitude": 80.2425 },
  "max_results": 3
}
```

The response is `{ "places": [...] }`. Each place includes its coordinates, `route_km`,
`detour_km`, and `route_rank`. The picker preselects the lowest-detour result, while the user
can choose another candidate or search for a different place. The schedule preview then optimizes
the order of all selected stops together.

Schedule metrics include an estimated direct tailpipe CO2 scenario alongside route kilometres. In
Car mode, the estimate uses 0.140 kg CO2 per vehicle-kilometre for a gasoline hatchback under 1,400
cc, including the 8% uplift factor from the 2015 India-specific road transport factor study. Walking
and Bicycle modes assume zero direct tailpipe CO2. This is a comparison scenario, not a vehicle
specific or lifecycle emissions measurement; the API includes the factor and source URL with the
distance savings metric.
