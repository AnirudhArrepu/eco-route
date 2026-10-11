"""Step Functions Lambda task handler for EcoRoute planning requests."""

from typing import Any
from sqlalchemy import select
from fastapi import HTTPException
import logging

from app.db import SessionLocal
from app import models
from app.integrations import parse_replan_request, parse_intent, search_places
from app.schemas import ReplanRequest
from app.service import get_schedule, replan, row_stop

logger=logging.getLogger(__name__)


def run_action(event: dict[str, Any], db=None) -> dict[str, Any]:
    action = event.get("action")
    if action == "interpret":
        user_id = event.get("user_id")
        schedule_id = event.get("schedule_id")
        context = None
        if user_id and schedule_id:
            owns_session = db is None
            session = db or SessionLocal()
            try:
                schedule = get_schedule(session, schedule_id, user_id)
                stop_rows=session.scalars(select(models.Stop).where(models.Stop.schedule_id==schedule.id).order_by(models.Stop.order_index)).all()
                context = {
                    "date": schedule.schedule_date.isoformat(),
                    "start_location": (schedule.start_location or {}).get("label"),
                    "end_location": (schedule.end_location or {}).get("label"),
                    "stops": [{"id":row.id,"title":row.title,"type":row.type,"location":row.location} for row in stop_rows],
                }
            finally:
                if owns_session:
                    session.close()
        if context is None:
            intent = parse_intent(event.get("request_text", ""), event.get("timezone", "UTC"))
        else:
            intent = parse_intent(event.get("request_text", ""), event.get("timezone", "UTC"), context)
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
                "message": ("Mantle was unavailable; this request used simple phrase matching. Review the suggestions carefully. " if intent.get("intent_source")=="local_fallback" else "") + "Place results do not verify product stock or price.",
            }

        if action == "replan":
            rows=session.scalars(select(models.Stop).where(models.Stop.schedule_id==schedule_id).order_by(models.Stop.order_index)).all()
            stops=[row_stop(row) for row in rows]
            parsed_change=parse_replan_request(event.get("request_text", ""),stops,schedule.timezone or event.get("timezone", "UTC"),{
                "date":schedule.schedule_date.isoformat(),
                "start_at":schedule.start_at.isoformat(),
                "end_at":schedule.end_at.isoformat(),
                "start_location":(schedule.start_location or {}).get("label"),
                "end_location":(schedule.end_location or {}).get("label"),
            })
            if parsed_change["clarification_question"]:
                return {"status":"clarification_required","question":parsed_change["clarification_question"]}
            if not parsed_change["updates"] and parsed_change.get("stop_order") is None and not parsed_change.get("optimize_route"):
                return {"status":"clarification_required","question":"What should change? You can adjust a stop's time or duration, choose a stop order, or ask me to optimize the route."}
            request = ReplanRequest(user_id=user_id, updates=parsed_change["updates"], stop_order=parsed_change.get("stop_order"), reason=event.get("request_text") or "User requested replanning")
            proposal = replan(session, schedule_id, request)
            explanation_facts=proposal.explanation_facts
            if parsed_change["source"]=="local_fallback":
                explanation_facts=explanation_facts+["Mantle was unavailable; this change was interpreted with simple rules. Review the proposed timing and stop order carefully."]
            return {
                "id": proposal.id,
                "schedule_id": proposal.schedule_id,
                "status": proposal.status,
                "feasible": proposal.status in ("pending", "approved"),
                "base_revision": proposal.base_revision,
                "proposed_stops": proposal.proposed_stops,
                "metrics": proposal.metrics,
                "conflicts": proposal.conflicts,
                "explanation_facts": explanation_facts,
                "expires_at": proposal.expires_at.isoformat(),
            }

        raise ValueError("Unsupported workflow action")
    finally:
        if owns_session:
            session.close()


def lambda_handler(event: dict[str, Any], _context) -> dict[str, Any]:
    if event.get("action") == "migrate":
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config("alembic.ini"), "head")
        return {"status": "migrated"}
    try:
        return run_action(event)
    except HTTPException as exc:
        logger.error("Planning workflow action rejected: action=%s status=%s detail_type=%s",
                     event.get("action"),exc.status_code,type(exc.detail).__name__)
        if exc.status_code == 404:
            message="This saved plan could not be found for your account. Refresh the itinerary and try again."
        elif exc.status_code == 422:
            message="The proposed change does not fit the current schedule. Try a different time or stop order."
        elif exc.status_code in (502,503):
            message="A planning service is temporarily unavailable. Your saved plan was not changed; please retry."
        else:
            message="EcoRoute could not complete this request. Your saved plan was not changed; please retry."
        return {"status":"error","message":message,"error_code":f"planning_{exc.status_code}"}
