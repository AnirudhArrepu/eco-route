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
Open `/docs`. SQLite is the quick-start default. Startup applies Alembic migrations automatically;
set `AUTO_MIGRATE=false` when migrations are applied by a separate release step. To migrate manually,
run `python -m alembic upgrade head`. `docker compose up --build` runs PostgreSQL.

## AWS
Set `DATABASE_URL` to RDS PostgreSQL and configure `AWS_REGION`, `AWS_INTEGRATIONS_ENABLED=true`,
`BEDROCK_MODEL_ID`, `LOCATION_INDEX_NAME`, and `LOCATION_ROUTE_CALCULATOR_NAME`. Use an ECS task
role; don't put AWS access keys in source code. Enable Bedrock model access and provision an Amazon
Location place index and route calculator in the configured region.
When AWS integrations are enabled, route and place provider failures are returned as errors;
the backend does not silently substitute local estimates. With integrations disabled, the
deterministic straight-line travel provider is intended only for local development. Set
`ENVIRONMENT=production` to make missing live route configuration fail closed.

For Cognito, configure `COGNITO_USER_POOL_ID` and `COGNITO_APP_CLIENT_ID`, then set
`AUTH_REQUIRED=true` (production mode requires authentication even if this flag is false). Send
the Cognito ID or access token as `Authorization: Bearer <token>`. The API verifies its signature
against the pool JWKS, issuer, expiry, token use, and app client. The authenticated `sub` must match
the requested `user_id`; a client cannot use another user's ID. ECS needs outbound HTTPS access to
the Cognito JWKS endpoint. The task role does not need Cognito API permissions for token checks.

To route natural-language requests through Strands, set `STRANDS_AGENT_ENABLED=true` and configure
the Bedrock model and Amazon Location place index. Its only application tool searches candidate
places; the agent cannot write schedules or approve proposals. The deterministic planner and
proposal service remain authoritative. `STRANDS_MAX_TOOL_CALLS` caps place-search tool calls.

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
proposal generation.

## Current MVP boundaries
The schedule planner validates hard appointment and time-window constraints before schedule creation,
checks precedence and maximum travel-time constraints, includes the return leg in route metrics, and
uses a bounded deterministic insertion search. Proposals are persisted without changing a schedule;
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
- `POST /v1/schedules`
- `GET /v1/schedules/{id}?user_id=...`
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
