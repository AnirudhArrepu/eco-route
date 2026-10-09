import json
from datetime import datetime, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app import auth, workflows
from app.config import settings
from app.integrations import infer_replan_updates, parse_intent
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

    monkeypatch.setattr(settings, "strands_agent_enabled", True)
    monkeypatch.setattr(settings, "bedrock_model_id", "configured-model")
    monkeypatch.setattr(settings, "aws_integrations_enabled", True)
    monkeypatch.setattr(settings, "location_index_name", "places")
    calls = []
    monkeypatch.setattr("app.strands_agent.search_places", lambda query, bias, max_results: calls.append((query, bias, max_results)) or [{"id": "place-1"}])

    class FakeAgent:
        def __init__(self, **kwargs):
            self.tools = kwargs["tools"]

        def __call__(self, _prompt):
            self.tools[0]("phone charger")
            return '{"operation":"add_destination","destination_query":"phone charger","budget_inr":800,"clarification_needed":false,"clarification_question":null}'

    fake_strands = types.ModuleType("strands")
    fake_strands.Agent = FakeAgent
    fake_strands.tool = lambda function: function
    monkeypatch.setitem(sys.modules, "strands", fake_strands)
    from app.strands_agent import interpret_with_strands

    parsed = interpret_with_strands("charger under ₹800", "Asia/Kolkata", [80.2, 13.0])
    assert parsed["budget_inr"] == 800
    assert calls == [("phone charger", [80.2, 13.0], 10)]


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
