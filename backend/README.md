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
Open `/docs`. SQLite is the quick-start default. `docker compose up --build` runs PostgreSQL.

## AWS
Set `DATABASE_URL` to RDS PostgreSQL, `AWS_REGION`, `AWS_INTEGRATIONS_ENABLED=true`,
`BEDROCK_MODEL_ID`, `LOCATION_INDEX_NAME`, and `LOCATION_ROUTE_CALCULATOR_NAME`.
Use an ECS task role; don't put AWS access keys in source code. Enable Bedrock model access
and provision an Amazon Location place index and route calculator in the same region.
When AWS integrations are enabled, route and place provider failures are returned as errors;
the backend does not silently substitute local estimates. With integrations disabled, the
deterministic straight-line travel provider is intended only for local development. Set
`ENVIRONMENT=production` to make missing live route configuration fail closed.

## Current MVP boundaries
The schedule planner validates hard appointment and time-window constraints, checks precedence
and maximum travel-time constraints, includes the return leg in route metrics, and uses a
bounded deterministic insertion search. Proposals are persisted without changing a schedule;
approval checks ownership, expiration, revision, and plan feasibility in a transaction.

Authentication is not yet wired to Cognito: current endpoints accept `user_id` fields or query
parameters for local development, so deploy this API only behind a trusted identity layer until
JWT verification is implemented. Database tables are currently initialized with SQLAlchemy
`create_all()`; production deployment still needs Alembic migrations and an initial migration.
The local development configuration uses SQLite and mock routing; it does not validate live AWS
permissions or resources.

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
