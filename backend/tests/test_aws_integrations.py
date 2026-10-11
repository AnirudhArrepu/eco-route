import json
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import auth, workflows
from app.config import settings
from app.integrations import extract_tasks, infer_replan_updates, parse_intent, search_places_on_route
from app.main import app
from app.auth import authenticated_user
from fastapi.testclient import TestClient


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


def test_workflow_worker_returns_retryable_error_for_planning_http_exception(monkeypatch):
    from fastapi import HTTPException
    from app import workflow_worker
    monkeypatch.setattr(workflow_worker, "run_action", lambda event: (_ for _ in ()).throw(HTTPException(502, "provider details")))
    result=workflow_worker.lambda_handler({"action":"replan"},None)
    assert result["status"] == "error"
    assert "temporarily unavailable" in result["message"]
    assert result["error_code"] == "planning_502"


def test_replan_understands_explicit_meeting_extension():
    stops = [{"id": "meeting-1", "title": "Daily sync", "type": "meeting", "duration_minutes": 30}]
    assert infer_replan_updates("My meeting was extended by 45 minutes", stops) == {"meeting-1": {"duration_minutes": 75}}
    assert parse_intent("My meeting was extended by 45 minutes")["operation"] == "replan"


def test_replan_does_not_guess_which_stop_was_extended():
    stops = [
        {"id": "meeting-1", "title": "Team sync", "type": "meeting", "duration_minutes": 30},
        {"id": "meeting-2", "title": "Client sync", "type": "meeting", "duration_minutes": 30},
    ]
    assert infer_replan_updates("My meeting was extended by 45 minutes", stops) == {}


def test_existing_stop_and_deadline_are_classified_as_replan():
    stops = [{"id": "stop-theatre", "title": "Theatre", "location": {"label": "City Auditorium"}}]
    context = {"stops": stops}
    result = parse_intent("need to be at the theatre by 5pm", "Asia/Kolkata", context)
    assert result["operation"] == "replan"
    assert result["intent_source"] == "existing_schedule_stop"


def test_mantle_intent_request_failure_uses_explicit_phrase_fallback(monkeypatch):
    from pydantic import SecretStr
    from app import integrations

    class FakeCompletions:
        def create(self, **kwargs):
            raise TimeoutError("simulated Mantle timeout")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    result=integrations.parse_intent("Find a pharmacy near Chennai Central", "Asia/Kolkata")
    assert result["operation"] == "add_destination"
    assert result["intent_source"] == "local_fallback"
    assert result["fallback_reason"] == "mantle_request_failed"


def test_replan_parser_maps_arrive_by_time_to_latest_start(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app import integrations

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '```json\n{"updates":{"theatre-1":{"latest_start":"2026-10-12T17:00:00+05:30"}},'
                '"stop_order":null,"optimize_route":false,"clarification_question":null}\n```'
            )))])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    result = integrations.parse_replan_request("need to be at the theatre by 5pm", [
        {"id": "theatre-1", "title": "Theatre", "duration_minutes": 30}
    ], "Asia/Kolkata", {"date": "2026-10-12"})
    assert result["updates"] == {"theatre-1": {"latest_start": "2026-10-12T17:00:00+05:30"}}


def test_replan_parser_recovers_named_deadline_when_mantle_times_out(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app import integrations

    class FakeCompletions:
        def create(self, **kwargs):
            raise TimeoutError("simulated Mantle timeout")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    result=integrations.parse_replan_request("need to be at the theatre by 5pm", [
        {"id": "theatre-1", "title": "Theatre", "duration_minutes": 30}
    ], "Asia/Kolkata", {"date": "2026-10-12"})
    assert result["updates"] == {"theatre-1": {"latest_start": "2026-10-12T17:00:00+05:30"}}
    assert result["source"] == "explicit_rule"


def test_explicit_named_stop_deadline_does_not_depend_on_mantle(monkeypatch):
    from app import integrations

    from pydantic import SecretStr
    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("configured-for-test"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    result = integrations.parse_replan_request(
        "need to be at pharmacy by 5pm",
        [{"id": "pharmacy-1", "title": "Pharmacy", "duration_minutes": 30}],
        "Asia/Kolkata",
        {"date": "2026-10-12"},
    )

    assert result["updates"] == {
        "pharmacy-1": {"latest_start": "2026-10-12T17:00:00+05:30"}
    }
    assert result["source"] == "explicit_rule"


def test_mantle_parses_natural_language_replan_updates(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app import integrations

    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"updates":{"stop-pharmacy":{"fixed_start":"2026-10-12T16:00:00+05:30"}},'
                '"stop_order":null,"optimize_route":false,"clarification_question":null}'
            )))])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    stops = [{"id": "stop-pharmacy", "title": "Pharmacy", "duration_minutes": 30}]

    result = integrations.parse_replan_request("Move the pharmacy to 4 pm", stops, "Asia/Kolkata", {"date": "2026-10-12"})

    assert result["updates"] == {"stop-pharmacy": {"fixed_start": "2026-10-12T16:00:00+05:30"}}
    assert result["clarification_question"] is None
    assert result["source"] == "mantle"
    assert "stop-pharmacy" in captured["request"]["messages"][1]["content"]


def test_mantle_replan_parser_recovers_from_unknown_stop_ids(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app import integrations

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"updates":{"not-a-stop":{"duration_minutes":60}},"optimize_route":false,"clarification_question":null}'
            )))])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    result=integrations.parse_replan_request("Make the stop longer", [{"id": "stop-1", "title": "Pharmacy", "duration_minutes": 30}])
    assert result["source"] == "local_fallback"
    assert result["clarification_question"]


def test_parse_intent_uses_bedrock_mantle_openai_client(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app import integrations

    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            message = SimpleNamespace(content=(
                '{"operation":"add_destination","destination_query":"coffee shop in Connaught Place",'
                '"budget_inr":null,"clarification_needed":false,"clarification_question":null}'
            ))
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr(integrations.settings, "openai_project_id", "default")
    monkeypatch.setattr(integrations.settings, "bedrock_model_id", "openai.gpt-oss-safeguard-20b")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    result = parse_intent("Find a coffee shop in Connaught Place", "Asia/Kolkata")

    assert result["operation"] == "add_destination"
    assert result["destination_query"] == "coffee shop in Connaught Place"
    assert captured["client"]["base_url"] == "https://mantle.example/v1"
    assert captured["client"]["project"] == "default"
    assert captured["request"]["model"] == "openai.gpt-oss-safeguard-20b"


def test_explicit_place_search_does_not_require_clarification(monkeypatch):
    from types import SimpleNamespace
    from pydantic import SecretStr
    from app import integrations

    class FakeCompletions:
        def create(self, **kwargs):
            message = SimpleNamespace(content=(
                '{"operation":"clarify","destination_query":"Chennai Central",'
                '"budget_inr":null,"clarification_needed":true,'
                '"clarification_question":"List or directions?"}'
            ))
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    result = integrations.parse_intent("Find a pharmacy near Chennai Central", "Asia/Kolkata")

    assert result["operation"] == "add_destination"
    assert result["destination_query"] == "pharmacy near Chennai Central"
    assert result["clarification_needed"] is False


def test_task_extraction_uses_mantle_and_marks_its_source(monkeypatch):
    from pydantic import SecretStr
    from app import integrations

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=(
                '{"tasks":[{"title":"Grocery store","destination_query":"grocery store",'
                '"duration_minutes":null},{"title":"Pharmacy","destination_query":"pharmacy",'
                '"duration_minutes":null}],"clarification_question":null}'
            )))])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    result = extract_tasks("I need to visit the grocery store and the pharmacy", "2026-10-12", "Asia/Kolkata")

    assert result["extraction_source"] == "mantle"
    assert [task["destination_query"] for task in result["tasks"]] == ["grocery store", "pharmacy"]


def test_task_extraction_marks_local_fallback_when_mantle_returns_invalid_json(monkeypatch):
    from pydantic import SecretStr
    from app import integrations

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(integrations.settings, "openai_api_key", SecretStr("not-a-real-key"))
    monkeypatch.setattr(integrations.settings, "openai_base_url", "https://mantle.example/v1")
    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)

    result=extract_tasks("I need to visit the grocery store and the pharmacy", "2026-10-12", "Asia/Kolkata")
    assert result["extraction_source"] == "local_fallback"
    assert result["fallback_reason"] == "mantle_response_invalid"
    assert [task["destination_query"] for task in result["tasks"]] == ["grocery store", "pharmacy"]


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
