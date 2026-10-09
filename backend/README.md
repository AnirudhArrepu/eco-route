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

