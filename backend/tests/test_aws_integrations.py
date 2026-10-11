import json
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import auth, workflows
from app.config import settings
from app import integrations
from app.integrations import extract_tasks, parse_intent, search_places_on_route
from app.main import app
from app.auth import authenticated_user
from fastapi.testclient import TestClient


def stub_strands_output(monkeypatch, model_name, payload):
    from app import strands_agent

    output_model = getattr(strands_agent, model_name)
    monkeypatch.setattr(
        strands_agent,
        "_run_agent",
        lambda **_kwargs: output_model.model_validate(payload),
    )


def test_cognito_id_token_verification(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_example"
    monkeypatch.setattr(settings, "aws_region", "ap-south-1")
    monkeypatch.setattr(settings, "cognito_user_pool_id", "ap-south-1_example")
    monkeypatch.setattr(settings, "cognito_app_client_id", "local-client")
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(auth, "_jwks_client", lambda _url: SimpleNamespace(get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())))
    token = jwt.encode({"iss": issuer, "sub": "cognito-subject", "aud": "local-client", "token_use": "id", "exp": 4_000_000_000}, private_key, algorithm="RS256")
    assert authenticated_user(f"Bearer {token}") == "cognito-subject"


def test_cognito_rejects_missing_token_when_auth_is_required(monkeypatch):
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "environment", "test")
    with pytest.raises(HTTPException) as error:
        authenticated_user(None)
    assert error.value.status_code == 401


def test_cognito_rejects_wrong_app_client(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = "https://cognito-idp.ap-south-1.amazonaws.com/ap-south-1_example"
    monkeypatch.setattr(settings, "aws_region", "ap-south-1")
    monkeypatch.setattr(settings, "cognito_user_pool_id", "ap-south-1_example")
    monkeypatch.setattr(settings, "cognito_app_client_id", "expected-client")
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(auth, "_jwks_client", lambda _url: SimpleNamespace(get_signing_key_from_jwt=lambda _token: SimpleNamespace(key=private_key.public_key())))
    token = jwt.encode({"iss": issuer, "sub": "cognito-subject", "aud": "other-client", "token_use": "id", "exp": 4_000_000_000}, private_key, algorithm="RS256")
    with pytest.raises(HTTPException) as error:
        authenticated_user(f"Bearer {token}")
    assert error.value.status_code == 401


def test_authenticated_subject_overrides_or_rejects_client_user_id(client, schedule_payload):
    app.dependency_overrides[auth.authenticated_user] = lambda: "cognito-subject"
    matching = {**schedule_payload, "user_id": "cognito-subject"}
    response = client.post("/v1/schedules", json=matching)
    assert response.status_code == 200
    rejected = client.post("/v1/schedules", json={**schedule_payload, "user_id": "someone-else"})
    assert rejected.status_code == 403
    app.dependency_overrides.pop(auth.authenticated_user, None)


def test_production_requires_cognito_token(client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    response = client.get("/v1/preferences", params={"user_id": "local-user"})
    assert response.status_code == 401


def test_step_functions_start_and_user_scoped_status(monkeypatch):
    monkeypatch.setattr(settings, "step_functions_enabled", True)
    monkeypatch.setattr(settings, "step_functions_state_machine_arn", "arn:aws:states:ap-south-1:123:stateMachine:planning")

    class FakeClient:
        def start_execution(self, **kwargs):
            self.input = json.loads(kwargs["input"])
            return {"executionArn": "arn:execution:one", "startDate": datetime(2026, 10, 9, tzinfo=timezone.utc)}

        def describe_execution(self, **kwargs):
            return {"executionArn": kwargs["executionArn"], "input": json.dumps(self.input), "output": json.dumps({"status": "proposal_pending"}), "status": "SUCCEEDED", "startDate": datetime(2026, 10, 9, tzinfo=timezone.utc), "stopDate": datetime(2026, 10, 9, 0, 1, tzinfo=timezone.utc)}

    fake = FakeClient()
    monkeypatch.setattr(workflows, "_step_functions_client", lambda: fake)
    started = workflows.start_planning_execution(user_id="user-1", text="add a pharmacy", schedule_id="schedule-1", timezone="UTC")
    assert started["status"] == "running"
    result = workflows.get_planning_execution(started["execution_arn"], "user-1")
    assert result["status"] == "SUCCEEDED"
    assert result["result"] == {"status": "proposal_pending"}
    with pytest.raises(HTTPException) as error:
        workflows.get_planning_execution(started["execution_arn"], "user-2")
    assert error.value.status_code == 404


def test_agent_endpoint_dispatches_to_step_functions(client, monkeypatch):
    from app import main

    monkeypatch.setattr(settings, "step_functions_enabled", True)
    monkeypatch.setattr(main, "start_planning_execution", lambda **kwargs: {"status": "running", "request": kwargs})
    response = client.post("/v1/agent/requests", json={"user_id": "local-user", "text": "replan", "schedule_id": "schedule-1"})
    assert response.status_code == 200
    assert response.json()["request"]["schedule_id"] == "schedule-1"


def test_strands_agent_uses_typed_place_tool_and_validates_intent(monkeypatch):
    import sys
    import types
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "strands_agent_enabled", True)
    monkeypatch.setattr(settings, "bedrock_model_id", "configured-model")
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr(settings, "openai_project_id", "default")
    monkeypatch.setattr(settings, "aws_integrations_enabled", True)
    monkeypatch.setattr(settings, "location_index_name", "places")
    calls = []
    monkeypatch.setattr("app.strands_agent.search_places", lambda query, bias, max_results: calls.append((query, bias, max_results)) or [{"id": "place-1"}])

    class FakeAgent:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]
            self.model = kwargs["model"]

        def __call__(self, _prompt):
            self.tools[0]("phone charger")
            return '{"operation":"add_destination","destination_query":"phone charger","budget_inr":800,"clarification_needed":false,"clarification_question":null}'

    fake_strands = types.ModuleType("strands")
    fake_strands.Agent = FakeAgent
    fake_strands.tool = lambda function: function
    monkeypatch.setitem(sys.modules, "strands", fake_strands)
    fake_models = types.ModuleType("strands.models")
    fake_openai_model = types.ModuleType("strands.models.openai")

    class FakeOpenAIModel:
        def __init__(self, **kwargs):
            self.config = kwargs

    fake_openai_model.OpenAIModel = FakeOpenAIModel
    monkeypatch.setitem(sys.modules, "strands.models", fake_models)
    monkeypatch.setitem(sys.modules, "strands.models.openai", fake_openai_model)
    from app.strands_agent import interpret_with_strands

    parsed = interpret_with_strands("charger under ₹800", "Asia/Kolkata", [80.2, 13.0])
    assert parsed["budget_inr"] == 800
    assert calls == [("phone charger", [80.2, 13.0], 10)]


def test_strands_agent_requires_mantle_credentials(monkeypatch):
    from app.strands_agent import interpret_with_strands

    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "openai_base_url", "")
    with pytest.raises(HTTPException, match="OPENAI_API_KEY and OPENAI_BASE_URL"):
        interpret_with_strands("find coffee")


def test_step_functions_definition_and_worker_interpret_contract(monkeypatch):
    from pathlib import Path
    from app import workflow_worker

    definition = json.loads(Path("infra/step-functions/planning.asl.json").read_text(encoding="utf-8"))
    assert definition["StartAt"] == "InterpretRequest"
    assert definition["States"]["CreateReplanProposal"]["End"] is True
    monkeypatch.setattr(workflow_worker, "parse_intent", lambda text, timezone: {"operation": "replan", "raw": text, "timezone": timezone})
    result = workflow_worker.run_action({"action": "interpret", "request_text": "meeting extended", "timezone": "Asia/Kolkata", "user_id": "user-1"})
    assert result["intent"]["operation"] == "replan"
    assert result["user_id"] == "user-1"


def test_workflow_interpreter_uses_enabled_strands_agent(monkeypatch):
    from app import workflow_worker

    captured = {}

    def interpret(text, timezone, bias, schedule_context):
        captured.update({
            "text": text,
            "timezone": timezone,
            "bias": bias,
            "schedule_context": schedule_context,
        })
        return {"operation": "clarify"}

    monkeypatch.setattr(workflow_worker.settings, "strands_agent_enabled", True)
    monkeypatch.setattr("app.strands_agent.interpret_with_strands", interpret)
    result = workflow_worker.run_action({
        "action": "interpret",
        "request_text": "What should I change?",
        "timezone": "Asia/Kolkata",
    })

    assert result["intent"]["operation"] == "clarify"
    assert captured == {
        "text": "What should I change?",
        "timezone": "Asia/Kolkata",
        "bias": None,
        "schedule_context": None,
    }


def test_workflow_worker_returns_retryable_error_for_planning_http_exception(monkeypatch):
    from fastapi import HTTPException
    from app import workflow_worker
    monkeypatch.setattr(workflow_worker, "run_action", lambda event: (_ for _ in ()).throw(HTTPException(502, "provider details")))
    result=workflow_worker.lambda_handler({"action":"replan"},None)
    assert result["status"] == "error"
    assert "temporarily unavailable" in result["message"]
    assert result["error_code"] == "planning_502"


def test_existing_stop_and_deadline_are_classified_by_strands(monkeypatch):
    stub_strands_output(monkeypatch, "ParsedIntent", {
        "operation": "replan",
        "clarification_needed": False,
    })
    stops = [{"id": "stop-theatre", "title": "Theatre", "location": {"label": "City Auditorium"}}]
    context = {"stops": stops}
    result = parse_intent("need to be at the theatre by 5pm", "Asia/Kolkata", context)
    assert result["operation"] == "replan"
    assert result["intent_source"] == "strands_agent"


def test_strands_interpretation_failure_is_reported_without_local_parsing(monkeypatch):
    from app import strands_agent

    def fail(**_kwargs):
        raise HTTPException(502, "The Strands agent could not interpret this request.")

    monkeypatch.setattr(strands_agent, "_run_agent", fail)
    with pytest.raises(HTTPException, match="Strands agent could not interpret"):
        parse_intent("Find a pharmacy near Chennai Central", "Asia/Kolkata")


def test_strands_replan_maps_arrive_by_time_to_latest_start(monkeypatch):
    stub_strands_output(monkeypatch, "ReplanInterpretation", {
        "updates": {"theatre-1": {"latest_start": "2026-10-12T17:00:00+05:30"}},
        "stop_order": None,
        "optimize_route": False,
        "clarification_question": None,
    })
    result = integrations.parse_replan_request("need to be at the theatre by 5pm", [
        {"id": "theatre-1", "title": "Theatre", "duration_minutes": 30}
    ], "Asia/Kolkata", {"date": "2026-10-12"})
    assert result["updates"] == {"theatre-1": {"latest_start": "2026-10-12T17:00:00+05:30"}}


def test_strands_replan_timeout_is_not_converted_to_a_guessed_update(monkeypatch):
    from app import strands_agent

    def fail(**_kwargs):
        raise HTTPException(502, "The Strands agent could not interpret this request.")

    monkeypatch.setattr(strands_agent, "_run_agent", fail)
    with pytest.raises(HTTPException, match="Strands agent could not interpret"):
        integrations.parse_replan_request(
            "need to be at the theatre by 5pm",
            [{"id": "theatre-1", "title": "Theatre", "duration_minutes": 30}],
            "Asia/Kolkata",
            {"date": "2026-10-12"},
        )


def test_strands_extracts_combined_errands_and_appointment(monkeypatch):
    stub_strands_output(monkeypatch, "ExtractedTaskList", {
        "tasks": [
            {"title": "Pharmacy", "destination_query": "pharmacy", "type": "errand"},
            {"title": "Grocery store", "destination_query": "grocery store", "type": "errand"},
            {"title": "Dentist appointment", "destination_query": "dentist", "type": "appointment"},
        ],
    })
    result = extract_tasks(
        "need to visit the pharmacy, grocery store and also have a dentist appointment",
        "2026-10-12",
        "Asia/Kolkata",
    )
    assert [task["destination_query"] for task in result["tasks"]] == [
        "pharmacy", "grocery store", "dentist",
    ]
    assert [task["type"] for task in result["tasks"]] == ["errand", "errand", "appointment"]
    assert result["extraction_source"] == "strands_agent"


def test_strands_maps_arrival_deadline_separately_from_fixed_appointment(monkeypatch):
    stub_strands_output(monkeypatch, "ExtractedTaskList", {
        "tasks": [
            {
                "title": "Pharmacy", "destination_query": "pharmacy",
                "latest_start": "2026-10-12T17:00:00+05:30",
            },
            {
                "title": "Dentist appointment", "destination_query": "dentist",
                "fixed_start": "2026-10-12T18:00:00+05:30",
            },
        ],
    })
    result = extract_tasks(
        "need to be at pharmacy by 5pm and have a dentist appointment at 6 pm",
        "2026-10-12",
        "Asia/Kolkata",
    )
    assert result["tasks"][1]["fixed_start"] == "2026-10-12T18:00:00+05:30"
    assert result["tasks"][0]["latest_start"] == "2026-10-12T17:00:00+05:30"


def test_strands_parses_natural_language_appointment_move(monkeypatch):
    stub_strands_output(monkeypatch, "ReplanInterpretation", {
        "updates": {"stop-dentist": {"fixed_start": "2026-10-12T18:30:00+05:30"}},
        "stop_order": None,
        "optimize_route": False,
        "clarification_question": None,
    })
    stops = [
        {"id": "stop-pharmacy", "title": "Pharmacy", "duration_minutes": 30},
        {
            "id": "stop-dentist", "title": "Dentist appointment", "type": "appointment",
            "duration_minutes": 45, "fixed_start": "2026-10-12T18:00:00+05:30",
        },
    ]
    result = integrations.parse_replan_request(
        "my dentist appointment moved to 6:30pm",
        stops,
        "Asia/Kolkata",
        {"date": "2026-10-12"},
    )
    assert result["updates"] == {
        "stop-dentist": {"fixed_start": "2026-10-12T18:30:00+05:30"}
    }
    assert result["clarification_question"] is None
    assert result["source"] == "strands_agent"


def test_strands_replan_parser_rejects_unknown_stop_ids(monkeypatch):
    from app import integrations

    stub_strands_output(monkeypatch, "ReplanInterpretation", {
        "updates": {"not-a-stop": {"duration_minutes": 60}},
    })
    with pytest.raises(HTTPException, match="not in the active plan"):
        integrations.parse_replan_request(
            "Make the stop longer",
            [{"id": "stop-1", "title": "Pharmacy", "duration_minutes": 30}],
        )


def test_parse_intent_sends_natural_language_context_to_strands(monkeypatch):
    from app import strands_agent

    captured = {}
    monkeypatch.setattr(settings, "aws_integrations_enabled", True)
    monkeypatch.setattr(settings, "location_index_name", "places")

    def parse(**kwargs):
        captured.update(kwargs)
        return strands_agent.ParsedIntent(
            operation="add_destination",
            destination_query="pharmacy near Chennai Central",
            clarification_needed=False,
        )

    monkeypatch.setattr(strands_agent, "_run_agent", parse)
    result = parse_intent(
        "Find a pharmacy near Chennai Central",
        "Asia/Kolkata",
        {"start_location": {"latitude": 13.08, "longitude": 80.27}},
    )

    assert result["operation"] == "add_destination"
    assert result["destination_query"] == "pharmacy near Chennai Central"
    assert result["clarification_needed"] is False
    assert captured["output_model"] is strands_agent.ParsedIntent
    assert '"user_request": "Find a pharmacy near Chennai Central"' in captured["prompt"]
    assert captured["tools"][0].__name__ == "search_places_tool"


def test_task_extraction_uses_structured_strands_output(monkeypatch):
    from app import strands_agent

    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return strands_agent.ExtractedTaskList.model_validate({
            "tasks": [
                {"title": "Grocery store", "destination_query": "grocery store"},
                {"title": "Pharmacy", "destination_query": "pharmacy"},
                {"title": "Dentist appointment", "destination_query": "dentist"},
            ],
        })

    monkeypatch.setattr(strands_agent, "_run_agent", parse)
    result = extract_tasks(
        "need to visit the pharmacy, grocery store and also have a dentist appointment",
        "2026-10-12",
        "Asia/Kolkata",
    )
    assert result["extraction_source"] == "strands_agent"
    assert [task["destination_query"] for task in result["tasks"]] == [
        "grocery store", "pharmacy", "dentist",
    ]
    assert captured["output_model"] is strands_agent.ExtractedTaskList
    assert "separate task for each errand or appointment" in captured["system_prompt"]


def test_task_extraction_rejects_timezone_naive_agent_times(monkeypatch):
    from app import strands_agent

    stub_strands_output(monkeypatch, "ExtractedTaskList", {
        "tasks": [{
            "title": "Dentist appointment",
            "destination_query": "dentist",
            "fixed_start": "2026-10-12T18:00:00",
        }],
    })
    with pytest.raises(HTTPException, match="without a timezone offset"):
        extract_tasks("I have a dentist appointment at 6 pm", "2026-10-12", "Asia/Kolkata")


def test_route_place_search_ranks_by_actual_route_detour(monkeypatch):
    from app import integrations

    monkeypatch.setattr(integrations.settings, "aws_integrations_enabled", True)
    candidates = [
        {"id": "far", "title": "Far shop", "label": "Far shop", "latitude": 2, "longitude": 2},
        {"id": "near", "title": "Near shop", "label": "Near shop", "latitude": 1, "longitude": 1},
    ]
    monkeypatch.setattr(integrations, "search_places", lambda query, bias, max_results: candidates)

    class FakeProvider:
        def leg(self, origin, destination, mode):
            assert mode == "Car"
            if destination["latitude"] == 0:
                return SimpleNamespace(distance_km=10 if origin["latitude"] == 0 else 5 if origin["latitude"] == 1 else 4)
            return SimpleNamespace(distance_km=3 if destination["latitude"] == 1 else 8)

    monkeypatch.setattr(integrations, "TravelProvider", FakeProvider)
    start = {"latitude": 0, "longitude": 0}
    end = {"latitude": 0, "longitude": 10}

    result = search_places_on_route("grocery store", start, end, "Car", 2)

    assert [place["id"] for place in result] == ["near", "far"]
    assert result[0]["detour_km"] == 0
    assert result[0]["route_rank"] == 1


def test_route_place_search_endpoint_returns_candidates(client, monkeypatch):
    from app import main

    def fake_search(query, start, end, mode, limit):
        assert query == "pharmacy"
        assert start["latitude"] == 13.0
        assert end["longitude"] == 80.3
        assert mode == "Walking"
        assert limit == 3
        return [{"id": "place-1", "detour_km": 0.7, "route_rank": 1}]

    monkeypatch.setattr(main, "search_places_on_route", fake_search)
    response = client.post("/v1/places/route-search", json={
        "query": "pharmacy",
        "start_location": {"latitude": 13.0, "longitude": 80.2},
        "end_location": {"latitude": 13.1, "longitude": 80.3},
    })

    assert response.status_code == 200
    assert response.json()["places"][0]["id"] == "place-1"
