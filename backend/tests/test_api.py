def create_schedule(client, payload):
    response = client.post("/v1/schedules", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_schedule_proposal_approval_and_revision_flow(client, schedule_payload, destination):
    schedule_id = create_schedule(client, schedule_payload)
    proposal_response = client.post(
        f"/v1/schedules/{schedule_id}/stops",
        json={"user_id": "local-user", "destination": destination},
    )
    assert proposal_response.status_code == 200, proposal_response.text
    proposal = proposal_response.json()
    assert proposal["status"] == "pending"

    unchanged = client.get(f"/v1/schedules/{schedule_id}", params={"user_id": "local-user"}).json()
    assert unchanged["current_revision"] == 1
    assert unchanged["stops"] == []

    approved = client.post(
        f"/v1/proposals/{proposal['id']}/approve",
        json={"user_id": "local-user", "idempotency_key": "approve-grocery-001"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["revision"] == 2
    replay = client.post(
        f"/v1/proposals/{proposal['id']}/approve",
        json={"user_id": "local-user", "idempotency_key": "approve-grocery-001"},
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True

    saved = client.get(f"/v1/schedules/{schedule_id}", params={"user_id": "local-user"}).json()
    assert saved["current_revision"] == 2
    assert [stop["title"] for stop in saved["stops"]] == ["grocery store"]
    revisions = client.get(f"/v1/schedules/{schedule_id}/revisions", params={"user_id": "local-user"})
    assert [r["revision_number"] for r in revisions.json()] == [2, 1]


def test_complete_create_modify_and_add_stop_workflow(client, schedule_payload, destination):
    schedule_payload["stops"] = [{**destination, "id": "first-stop"}]
    created = client.post("/v1/schedules", json=schedule_payload)
    assert created.status_code == 200, created.text
    schedule_id = created.json()["id"]
    assert created.json()["current_revision"] == 1

    # Modify the existing plan through a proposal, then approve it.
    modified = client.post(
        f"/v1/schedules/{schedule_id}/replan",
        json={"user_id": "local-user", "updates": {"first-stop": {"duration_minutes": 45}}, "reason": "meeting ran long"},
    )
    assert modified.status_code == 200, modified.text
    proposal_id = modified.json()["id"]
    assert client.get(f"/v1/proposals/{proposal_id}", params={"user_id": "local-user"}).status_code == 200
    accepted_modify = client.post(
        f"/v1/proposals/{proposal_id}/approve",
        json={"user_id": "local-user", "idempotency_key": "workflow-modify-001"},
    )
    assert accepted_modify.status_code == 200, accepted_modify.text

    # Add a second stop to the now-existing plan and approve that proposal too.
    second_stop = {**destination, "title": "pharmacy", "location": {"latitude": 13.03, "longitude": 80.23}}
    added = client.post(
        f"/v1/schedules/{schedule_id}/stops",
        json={"user_id": "local-user", "destination": second_stop},
    )
    assert added.status_code == 200, added.text
    accepted_add = client.post(
        f"/v1/proposals/{added.json()['id']}/approve",
        json={"user_id": "local-user", "idempotency_key": "workflow-add-stop-001"},
    )
    assert accepted_add.status_code == 200, accepted_add.text

    saved = client.get(f"/v1/schedules/{schedule_id}", params={"user_id": "local-user"})
    assert saved.status_code == 200
    assert saved.json()["current_revision"] == 3
    saved_stops = saved.json()["stops"]
    assert {stop["title"]: stop["duration_minutes"] for stop in saved_stops} == {
        "grocery store": 45,
        "pharmacy": 30,
    }
    timeline = client.get(f"/v1/schedules/{schedule_id}/timeline", params={"user_id": "local-user"})
    assert timeline.status_code == 200
    assert timeline.json()["revision"] == 3
    assert [item["title"] for item in timeline.json()["timeline"]] == [stop["title"] for stop in saved_stops]
    revisions = client.get(f"/v1/schedules/{schedule_id}/revisions", params={"user_id": "local-user"})
    assert [revision["revision_number"] for revision in revisions.json()] == [3, 2, 1]


def test_rejected_proposal_does_not_change_schedule(client, schedule_payload, destination):
    schedule_id = create_schedule(client, schedule_payload)
    proposal = client.post(
        f"/v1/schedules/{schedule_id}/stops",
        json={"user_id": "local-user", "destination": destination},
    ).json()
    rejected = client.post(
        f"/v1/proposals/{proposal['id']}/reject",
        json={"user_id": "local-user", "reason": "not today"},
    )
    assert rejected.status_code == 200
    schedule = client.get(f"/v1/schedules/{schedule_id}", params={"user_id": "local-user"}).json()
    assert schedule["current_revision"] == 1
    assert schedule["stops"] == []


def test_stale_proposal_cannot_overwrite_a_newer_revision(client, schedule_payload, destination):
    schedule_id = create_schedule(client, schedule_payload)
    request = {"user_id": "local-user", "destination": destination}
    first = client.post(f"/v1/schedules/{schedule_id}/stops", json=request).json()
    second = client.post(f"/v1/schedules/{schedule_id}/stops", json={**request, "destination": {**destination, "title": "pharmacy"}}).json()
    accepted = client.post(
        f"/v1/proposals/{first['id']}/approve",
        json={"user_id": "local-user", "idempotency_key": "approve-first-001"},
    )
    assert accepted.status_code == 200
    stale = client.post(
        f"/v1/proposals/{second['id']}/approve",
        json={"user_id": "local-user", "idempotency_key": "approve-second-01"},
    )
    assert stale.status_code == 409
    current = client.get(f"/v1/schedules/{schedule_id}", params={"user_id": "local-user"}).json()
    assert current["current_revision"] == 2
    assert [stop["title"] for stop in current["stops"]] == ["grocery store"]


def test_preference_and_routine_crud_and_routine_schedule_inclusion(client, schedule_payload, destination):
    preference = client.post(
        "/v1/preferences",
        json={"user_id": "local-user", "key": "travel_mode", "value": {"mode": "Bicycle"}, "confidence": 0.9},
    )
    assert preference.status_code == 200
    updated_preference = client.put(
        "/v1/preferences/travel_mode",
        params={"user_id": "local-user"},
        json={"value": {"mode": "Walking"}, "confidence": 1, "source": "explicit"},
    )
    assert updated_preference.status_code == 200
    assert updated_preference.json()["value"]["mode"] == "Walking"
    routine = client.post(
        "/v1/routines",
        json={"user_id": "local-user", "routine": {"name": "weekday groceries", "weekday": 0, "stop": destination}},
    )
    assert routine.status_code == 201, routine.text
    routine_id = routine.json()["id"]
    assert len(client.get("/v1/routines", params={"user_id": "local-user"}).json()) == 1

    schedule_id = create_schedule(client, schedule_payload)
    scheduled = client.get(f"/v1/schedules/{schedule_id}", params={"user_id": "local-user"}).json()
    assert scheduled["stops"][0]["title"] == "grocery store"

    changed = client.put(
        f"/v1/routines/{routine_id}",
        json={"user_id": "local-user", "routine": {"name": "weekday errands", "weekday": 0, "stop": destination, "active": False}},
    )
    assert changed.status_code == 200
    assert client.delete(f"/v1/routines/{routine_id}", params={"user_id": "local-user"}).status_code == 204


def test_health_readiness_and_ownership(client, schedule_payload):
    schedule_id = create_schedule(client, schedule_payload)
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    hidden = client.get(f"/v1/schedules/{schedule_id}", params={"user_id": "someone-else"})
    assert hidden.status_code == 404


def test_agent_interpretation_requires_a_schedule_for_destination(client):
    response = client.post("/v1/agent/requests", json={"user_id": "local-user", "text": "buy charger under ₹800"})
    assert response.status_code == 422


def test_infeasible_schedule_is_rejected_before_persistence(client, schedule_payload):
    schedule_payload["end_at"] = "2026-10-12T09:10:00+05:30"
    schedule_payload["stops"] = [{
        "title": "long appointment",
        "location": {"latitude": 13.02, "longitude": 80.22},
        "duration_minutes": 120,
        "fixed_start": "2026-10-12T09:00:00+05:30",
        "mandatory": True,
    }]
    response = client.post("/v1/schedules", json=schedule_payload)
    assert response.status_code == 422
    assert response.json()["detail"]["conflicts"]


def test_replan_creates_a_proposal_without_mutating_schedule(client, schedule_payload, destination):
    schedule_payload["stops"] = [{**destination, "id": "stop-1"}]
    schedule_id = create_schedule(client, schedule_payload)
    response = client.post(
        f"/v1/schedules/{schedule_id}/replan",
        json={"user_id": "local-user", "updates": {"stop-1": {"duration_minutes": 45}}, "reason": "appointment changed"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending"
    assert response.json()["proposed_stops"][0]["duration_minutes"] == 45
    unchanged = client.get(f"/v1/schedules/{schedule_id}", params={"user_id": "local-user"}).json()
    assert unchanged["current_revision"] == 1
    assert unchanged["stops"][0]["duration_minutes"] == 30


def test_agent_returns_place_candidates_or_explicit_local_unavailability(client, schedule_payload):
    schedule_id = create_schedule(client, schedule_payload)
    response = client.post(
        "/v1/agent/requests",
        json={"user_id": "local-user", "schedule_id": schedule_id, "text": "find a phone charger under ₹800"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["intent"]["budget_inr"] == 800
    assert result["status"] in {"destination_candidates", "needs_destination_selection"}
    assert "verify" in result["message"].lower()


def test_schedule_preview_returns_optimized_timeline_without_persisting(client, schedule_payload, destination):
    schedule_payload["include_routines"] = False
    destination["location"] = {"latitude": 13.02, "longitude": 80.22, "label": "shop"}
    destination["latest_end"] = "2026-10-12T11:00:00+05:30"
    schedule_payload["stops"] = [destination]
    response = client.post("/v1/schedules/preview", json={**schedule_payload, "max_candidate_evaluations": 100})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["feasible"] is True
    assert result["timeline"][0]["title"] == "grocery store"
    assert result["timeline"][0]["start_at"]
    assert result["metrics"]["distance_km"] >= 0


def test_place_search_requires_coordinate_bias_pair(client):
    response = client.get("/v1/places/search", params={"query": "coffee", "latitude": 13})
    assert response.status_code == 422


def test_remaining_service_discovery_and_crud_endpoints(client, monkeypatch):
    from app import main
    from app.config import settings

    assert client.get("/").json()["docs"] == "/docs"
    assert client.get("/app").status_code == 200
    assert client.get("/app/app.js").status_code == 200
    assert client.get("/app/style.css").status_code == 200

    monkeypatch.setattr(main, "search_places", lambda query, bias, limit: [{"title": query, "bias": bias, "limit": limit}])
    places = client.get("/v1/places/search", params={"query": "coffee", "latitude": 13, "longitude": 80})
    assert places.status_code == 200
    assert places.json()["places"][0]["title"] == "coffee"

    created = client.post("/v1/preferences", json={"user_id": "local-user", "key": "coffee", "value": {"milk": False}})
    assert created.status_code == 200
    assert client.get("/v1/preferences", params={"user_id": "local-user"}).json()[0]["key"] == "coffee"
    updated = client.put(
        "/v1/preferences/coffee",
        params={"user_id": "local-user"},
        json={"value": {"milk": True}, "confidence": 1, "source": "explicit"},
    )
    assert updated.status_code == 200
    assert updated.json()["value"]["milk"] is True
    assert client.delete("/v1/preferences/coffee", params={"user_id": "local-user"}).status_code == 204
    assert client.get("/v1/preferences", params={"user_id": "local-user"}).json() == []

    monkeypatch.setattr(settings, "step_functions_enabled", True)
    monkeypatch.setattr(main, "get_planning_execution", lambda arn, user: {"execution_arn": arn, "user_id": user, "status": "SUCCEEDED"})
    status = client.get(
        "/v1/workflows/status",
        params={"execution_arn": "arn:local:test", "user_id": "local-user"},
    )
    assert status.status_code == 200
    assert status.json()["status"] == "SUCCEEDED"
