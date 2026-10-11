import logging

import boto3
from botocore.config import Config
from fastapi import HTTPException

from app.config import settings
from app.planner import Leg, MockTravelProvider

logger = logging.getLogger(__name__)


class AmazonLocation:
    def __init__(self):
        self.client = boto3.client(
            "location",
            region_name=settings.aws_region,
            config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}),
        )

    def search(self, text, bias=None, max_results=10):
        args = {
            "IndexName": settings.location_index_name,
            "Text": text,
            "MaxResults": min(max(1, max_results), 20),
        }
        if bias:
            args["BiasPosition"] = bias
        output = self.client.search_place_index_for_text(**args)
        rows = []
        for item in output.get("Results", []):
            place = item.get("Place", {})
            point = place.get("Geometry", {}).get("Point")
            if point:
                rows.append({
                    "id": item.get("PlaceId"),
                    "title": place.get("Label", text),
                    "label": place.get("Label"),
                    "longitude": point[0],
                    "latitude": point[1],
                    "categories": place.get("Categories", []),
                })
        return rows

    def route(self, origin, destination, mode="Walking"):
        output = self.client.calculate_route(
            CalculatorName=settings.location_route_calculator_name,
            DeparturePosition=[origin["longitude"], origin["latitude"]],
            DestinationPosition=[destination["longitude"], destination["latitude"]],
            TravelMode=mode,
            IncludeLegGeometry=False,
        )
        summary = output.get("Summary", {})
        return Leg(float(summary.get("DurationSeconds", 0)) / 60, float(summary.get("Distance", 0)))


class TravelProvider:
    def __init__(self):
        self.mock = MockTravelProvider()
        self.aws = AmazonLocation() if settings.aws_integrations_enabled else None

    def leg(self, origin, destination, mode="Walking"):
        if settings.aws_integrations_enabled:
            if not settings.location_route_calculator_name:
                raise RuntimeError("LOCATION_ROUTE_CALCULATOR_NAME is required when AWS integrations are enabled")
            return self.aws.route(origin, destination, mode)
        if settings.environment == "production":
            raise RuntimeError("Live Amazon Location routing must be configured in production")
        return self.mock.leg(origin, destination, mode)


def search_places(text, bias=None, max_results=10):
    if not settings.aws_integrations_enabled:
        return []
    if not settings.location_index_name:
        raise HTTPException(503, "LOCATION_INDEX_NAME is required when AWS integrations are enabled")
    try:
        return AmazonLocation().search(text, bias, max_results)
    except Exception as exc:
        raise HTTPException(502, "Amazon Location place search failed") from exc


def search_places_on_route(text, start_location, end_location, mode="Walking", max_results=5):
    """Rank real place matches by the extra routed distance they add to a trip."""
    if not settings.aws_integrations_enabled:
        return []
    midpoint = [
        (start_location["longitude"] + end_location["longitude"]) / 2,
        (start_location["latitude"] + end_location["latitude"]) / 2,
    ]
    candidates = search_places(text, midpoint, max_results)
    if not candidates:
        return []
    provider = TravelProvider()
    try:
        direct_km = provider.leg(start_location, end_location, mode).distance_km
        ranked = []
        for place in candidates:
            place_location = {"latitude": place["latitude"], "longitude": place["longitude"]}
            to_place = provider.leg(start_location, place_location, mode).distance_km
            from_place = provider.leg(place_location, end_location, mode).distance_km
            route_km = to_place + from_place
            ranked.append({
                **place,
                "route_km": round(route_km, 2),
                "detour_km": round(max(0.0, route_km - direct_km), 2),
            })
        ranked.sort(key=lambda place: (
            place["detour_km"],
            place["route_km"],
            place["label"] or "",
        ))
        for index, place in enumerate(ranked):
            place["route_rank"] = index + 1
        return ranked
    except Exception as exc:
        logger.error("Amazon Location route-aware place ranking failed: type=%s", type(exc).__name__)
        raise HTTPException(502, "Could not compare place candidates against the planned route") from exc


def parse_intent(text, timezone="UTC", schedule_context=None):
    from app.strands_agent import interpret_with_strands

    bias = None
    if schedule_context:
        start = schedule_context.get("start_location")
        if isinstance(start, dict) and start.get("longitude") is not None and start.get("latitude") is not None:
            bias = [start["longitude"], start["latitude"]]
    return interpret_with_strands(text, timezone, bias, schedule_context)


def extract_tasks(text, plan_date, timezone="UTC"):
    from app.strands_agent import extract_tasks_with_strands

    return extract_tasks_with_strands(text, plan_date, timezone)


def parse_replan_request(text, stops, timezone="UTC", schedule_context=None):
    from app.strands_agent import parse_replan_with_strands

    return parse_replan_with_strands(text, stops, timezone, schedule_context)
