# EcoRoute

**Plan a day of errands as one practical trip. See the distance and estimated tailpipe CO₂ that the combined route may save.**

EcoRoute is a route-aware day planner for people who need to make several stops around a city. Enter errands in plain language, choose real places near your route, add time windows, and let the planner find a feasible stop order. When plans change, ask EcoRoute to adjust the existing itinerary; review the proposed change before approving it.

## The problem

A person with several errands may make a separate out-and-back trip for each one, even when those stops could fit into one journey. Those extra kilometres mean extra fuel use and tailpipe emissions for people travelling by car.

EcoRoute helps people make that choice visible. It compares one multi-stop journey with a simple separate-trip baseline and shows estimated kilometres and direct tailpipe CO₂ saved. It is designed for everyday urban trips where errands, locations, and deadlines all matter.

## What EcoRoute does

1. **Turn a request into errands.** Enter a request such as “I need to visit the grocery store and pharmacy before 5 pm.” The task extractor identifies the requested stops and supported time constraints.
2. **Find places that fit the route.** EcoRoute searches for real place candidates and ranks them by routed detour. The lowest-detour candidate is preselected, and the user can choose a different location.
3. **Build a feasible day.** The planner evaluates candidate stop orders against the user's day, travel times, deadlines, appointments, and other hard constraints. It shows the itinerary before the user saves it.
4. **Change the plan in context.** In “Ask EcoRoute,” a user can add a stop, set a deadline for an existing stop, change a duration, request a stop order, or ask for route optimization. The system creates a proposal based on the current saved itinerary. Approved changes become the new revision, so later replans build on them.
5. **Review environmental impact.** The plan reports route distance, estimated kilometres saved against a separate-trip baseline, and a transparent CO₂ scenario estimate.

Proposals do not silently overwrite a saved plan. The user reviews the proposed timeline and metrics, then approves or keeps the original.

## Environmental impact

EcoRoute fits the **Waste and Energy** track of [Environmental Hacks](https://www.wemakedevs.org/aws/env), whose examples include nudging people out of cars and supporting public transport. The hackathon judging criteria are **idea and impact, built on AWS, design and usability, execution, and a three-minute demo video**. EcoRoute addresses these with a concrete urban mobility problem, an AWS-backed route-planning workflow, a user-reviewed itinerary, and a measurable (but explicitly estimated) comparison.

### How the estimate works

- For each stop, the baseline adds a separate start-to-stop-to-finish journey.
- The planned distance is the route from the start, through selected stops in the proposed order, to the finish.
- **Estimated kilometres saved** is the positive difference between the baseline and combined route. If the combined route is longer, EcoRoute reports additional distance instead of claiming savings.
- In **Car** mode, the CO₂ scenario multiplies the distance difference by **0.140 kg CO₂ per vehicle-kilometre**. This factor represents a gasoline hatchback under 1,400 cc with an 8% uplift from the [WRI India-specific road transport emission factors study](https://shaktifoundation.in/wp-content/uploads/2022/04/WRI-2015-India-Specific-Road-Transport-Emission-Factors.pdf).
- Walking and Bicycle modes assume zero direct tailpipe CO₂.

This is a planning estimate, not a measurement of actual fuel use or a lifecycle emissions calculation. It does not account for the user's exact vehicle, occupancy, traffic, fuel mix, or emissions from vehicle and infrastructure manufacture. Route distance is a proxy for fuel use. The UI displays the baseline and factor source so users can interpret the estimate.

## How it is built

### AWS services

- **Amazon API Gateway** receives frontend API requests.
- **AWS Lambda** runs the FastAPI API and planning workflow worker.
- **AWS Step Functions** orchestrates natural-language interpretation, destination discovery, and replanning.
- **Amazon RDS for PostgreSQL** stores schedules, stops, proposals, preferences, routines, and revisions.
- **Amazon Cognito** handles sign-up, confirmation, sign-in, and token-based identity.
- **Amazon Location Service** provides place search and route estimates.
- **Amazon Bedrock Mantle** provides the OpenAI-compatible model endpoint used for task extraction, intent parsing, and plan changes. The configured model is **openai.gpt-oss-safeguard-20b**.

The application uses the Strands Agents SDK for its optional tool-using agent path. The agent can search for place candidates; schedule persistence, route optimization, and proposal approval remain application responsibilities.

### Application flow

```text
React + Vite frontend
        |
        v
Amazon API Gateway
        |
        v
FastAPI on AWS Lambda ---- Amazon Cognito
        |                  Amazon Bedrock Mantle
        |                  Amazon Location
        |
        +---- AWS Step Functions ---- planning worker Lambda
        |
        v
Amazon RDS for PostgreSQL
```

For a natural-language request, the API starts a Step Functions execution when enabled. The workflow interprets the request with the current schedule as context, then either finds route-relevant destinations or creates a replan proposal. The route planner remains deterministic and checks feasibility; the language model does not approve or persist schedule changes.

When Mantle cannot be reached or returns an unusable response, the backend has limited rule-based fallbacks for common explicit requests. The UI identifies fallback interpretation so users can review it.

## Stack

- **Frontend:** React, Vite, Tailwind CSS
- **Backend:** Python, FastAPI, SQLAlchemy, Alembic
- **Data:** PostgreSQL in AWS; SQLite for the local quick start
- **Planning:** constraint-aware schedule planner and route-distance optimization
- **AWS:** API Gateway, Lambda, Step Functions, RDS PostgreSQL, Cognito, Amazon Location, Bedrock Mantle
- **Tests:** pytest

## Current scope and limitations

- Place suggestions identify locations; they do not verify inventory, prices, or opening hours.
- Route and emissions estimates depend on the configured travel provider and travel mode. Local mock routing is for development, not a live travel recommendation.
- CO₂ is a scenario estimate for direct tailpipe emissions in Car mode, not an audited carbon accounting result.
- Public-transit routing, vehicle-specific fuel economy, live traffic-aware emissions, shared-trip matching, and measured real-world impact are not currently modeled.
- If a place or constraint cannot be resolved safely, EcoRoute asks the user to clarify or select a candidate.

## Running checks

From the **backend** directory:

```powershell
python -m pytest -q
```

The tests cover schedule creation, feasibility, task parsing, place ranking, workflow behavior, proposals, approvals, and revisions. They use local fixtures and do not verify AWS permissions or live external-service responses.

## Develop locally

The following starts the API and web client on your machine. It uses SQLite and local/mock routing unless AWS integrations are configured. No AWS deployment is needed for the local API.

### 1. Start the backend

In PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API applies local Alembic migrations on startup. Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for interactive API documentation and [http://127.0.0.1:8000/ready](http://127.0.0.1:8000/ready) for the readiness check.

The default **.env.example** keeps AWS integrations, Step Functions, and required authentication disabled. For API development without Cognito, include a **user_id** in requests. For the frontend sign-in flow, set **COGNITO_USER_POOL_ID** and **COGNITO_APP_CLIENT_ID** in **backend/.env** to a Cognito pool and public app client you control. Set **OPENAI_API_KEY** to enable Mantle parsing; never commit real credentials.

To use live AWS place search and route calculations locally, also configure the AWS integration variables in **backend/.env** and provide AWS credentials through your normal AWS CLI profile or environment. Keep credentials out of source files.

### 2. Start the frontend

Open a second PowerShell terminal:

```powershell
cd frontend
npm ci
'VITE_API_BASE_URL=http://127.0.0.1:8000' | Set-Content .env.local
npm run dev
```

Open the local URL printed by Vite. The web app signs users in through the backend's Cognito endpoints, so configure a Cognito pool and app client in the backend before using the UI sign-in flow. You can call the unauthenticated local API through Swagger when Cognito is not configured.

### 3. Make a change and verify it

- Update backend code, then rerun **python -m pytest -q** from **backend**.
- Update frontend code, then run **npm run build** from **frontend** to check the production bundle.
- Keep local secrets in **backend/.env**; do not add them to commits.
- For AWS deployment and configuration, see [backend/README.md](backend/README.md).



