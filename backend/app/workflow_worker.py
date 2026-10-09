"""Step Functions Lambda task handler for EcoRoute planning requests."""

from typing import Any

from app.db import SessionLocal
from app.integrations import parse_intent, search_places
from app.schemas import ReplanRequest
from app.service import get_schedule, replan


def run_action(event: dict[str, Any], db=None) -> dict[str, Any]:
    action = event.get("action")
    if action == "interpret":
        intent = parse_intent(event.get("request_text", ""), event.get("timezone", "UTC"))
        return {**event, "intent": intent}

    owns_session = db is None
    session = db or SessionLocal()
    try:
        user_id = event.get("user_id")
        schedule_id = event.get("schedule_id")
        if not user_id or not schedule_id:
            raise ValueError("user_id and schedule_id are required")
        schedule = get_schedule(session, schedule_id, user_id)

        if action == "discover":
            intent = event.get("intent") or {}
            query = intent.get("destination_query") or event.get("request_text", "")
            places = search_places(
                query,
                [schedule.start_location["longitude"], schedule.start_location["latitude"]],
                10,
            )
            return {
                "status": "destination_candidates" if places else "needs_destination_selection",
                "intent": intent,
                "candidates": places,
                "message": "Place results do not verify product stock or price.",
            }

        if action == "replan":
            request = ReplanRequest(user_id=user_id, reason=event.get("request_text") or "User requested replanning")
            proposal = replan(session, schedule_id, request)
            return {
                "id": proposal.id,
                "schedule_id": proposal.schedule_id,
                "status": proposal.status,
                "feasible": proposal.status in ("pending", "approved"),
                "base_revision": proposal.base_revision,
                "proposed_stops": proposal.proposed_stops,
                "metrics": proposal.metrics,
                "conflicts": proposal.conflicts,
                "explanation_facts": proposal.explanation_facts,
                "expires_at": proposal.expires_at.isoformat(),
            }

        raise ValueError("Unsupported workflow action")
    finally:
        if owns_session:
            session.close()


def lambda_handler(event: dict[str, Any], _context) -> dict[str, Any]:
    return run_action(event)
