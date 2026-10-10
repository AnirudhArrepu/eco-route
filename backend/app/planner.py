from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from itertools import permutations
from math import factorial
from math import asin, cos, radians, sin, sqrt
from typing import Any, Protocol


@dataclass(frozen=True)
class Leg:
    minutes: float
    distance_km: float


class TravelProvider(Protocol):
    def leg(self, origin: dict, destination: dict, mode: str = "Walking") -> Leg: ...


class MockTravelProvider:
    """Deterministic local estimate. Never use as a production route source."""

    SPEED = {"Walking": 4.5, "Bicycle": 15.0, "Car": 25.0}

    def leg(self, a: dict, b: dict, mode: str = "Walking") -> Leg:
        lat1, lon1 = radians(float(a["latitude"])), radians(float(a["longitude"]))
        lat2, lon2 = radians(float(b["latitude"])), radians(float(b["longitude"]))
        h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
        km = 6371 * 2 * asin(sqrt(min(1.0, h))) * 1.25
        return Leg(km / self.SPEED.get(mode, self.SPEED["Walking"]) * 60 + (2 if km else 0), km)


def _dt(value: Any, reference: datetime) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        if reference.tzinfo is not None:
            raise ValueError("Stop timestamps must include a timezone")
        return parsed
    if reference.tzinfo is None:
        raise ValueError("Schedule timestamps must include a timezone")
    return parsed.astimezone(reference.tzinfo)


def _opening_window(hours: dict, start: datetime) -> tuple[datetime, datetime] | None:
    """Read a trusted, simple same-day {open, close} local-time window."""
    if not hours or not hours.get("open") or not hours.get("close"):
        return None
    opening = time.fromisoformat(hours["open"])
    closing = time.fromisoformat(hours["close"])
    return (
        datetime.combine(start.date(), opening, tzinfo=start.tzinfo),
        datetime.combine(start.date(), closing, tzinfo=start.tzinfo),
    )


def validate(stops, start_at, end_at, start_location, end_location, provider, mode, constraints):
    conflicts: list[dict] = []
    timing: list[dict] = []
    ids = [s["id"] for s in stops]
    if end_at <= start_at:
        conflicts.append({"constraint_type": "schedule_horizon", "reason": "Schedule end must be after its start"})

    index = {stop_id: i for i, stop_id in enumerate(ids)}
    for constraint in constraints:
        if constraint.get("hardness", "hard") != "hard":
            continue
        params = constraint.get("parameters", {})
        if constraint["type"] == "precedence":
            before, after = params.get("before"), params.get("after")
            if before in index and after in index and index[before] >= index[after]:
                conflicts.append({"constraint_type": "precedence", "reason": f"{before} must precede {after}"})
        elif constraint["type"] == "max_travel_minutes":
            maximum = params.get("minutes")
            if maximum is not None and float(maximum) < 0:
                conflicts.append({"constraint_type": "max_travel_minutes", "reason": "Maximum travel time cannot be negative"})

    current_time, current_loc = start_at, start_location
    travel_total = 0.0
    for stop in stops:
        try:
            leg = provider.leg(current_loc, stop["location"], mode)
            if leg.minutes < 0 or leg.distance_km < 0:
                raise ValueError("Travel estimates cannot be negative")
            arrival = current_time + timedelta(minutes=leg.minutes)
            earliest = _dt(stop.get("earliest_start"), start_at)
            latest = _dt(stop.get("latest_start"), start_at)
            latest_end = _dt(stop.get("latest_end"), start_at)
            fixed = _dt(stop.get("fixed_start"), start_at)
        except (KeyError, TypeError, ValueError) as exc:
            conflicts.append({"constraint_type": "invalid_input", "stop_id": stop.get("id"), "reason": str(exc)})
            continue

        start = max(arrival, earliest) if earliest else arrival
        if fixed is not None:
            if arrival > fixed:
                conflicts.append({"constraint_type": "fixed_appointment", "stop_id": stop["id"], "reason": "Cannot arrive before fixed appointment"})
            start = fixed
            if earliest is not None and fixed < earliest:
                conflicts.append({"constraint_type": "time_window", "stop_id": stop["id"], "reason": "Fixed start is before earliest start"})
            if latest is not None and fixed > latest:
                conflicts.append({"constraint_type": "time_window", "stop_id": stop["id"], "reason": "Fixed start is after latest start"})
        if latest is not None and start > latest:
            conflicts.append({"constraint_type": "time_window", "stop_id": stop["id"], "reason": "Latest start exceeded"})
        finish = start + timedelta(minutes=stop["duration_minutes"])
        if latest_end is not None and finish > latest_end:
            conflicts.append({"constraint_type": "latest_end", "stop_id": stop["id"], "reason": "Latest end exceeded"})
        try:
            window = _opening_window(stop.get("opening_hours") or {}, start)
        except ValueError as exc:
            conflicts.append({"constraint_type": "opening_hours", "stop_id": stop["id"], "reason": str(exc)})
            window = None
        if window and (start < window[0] or finish > window[1]):
            conflicts.append({"constraint_type": "opening_hours", "stop_id": stop["id"], "reason": "Visit does not fit opening hours"})
        if start < start_at or finish > end_at:
            conflicts.append({"constraint_type": "schedule_horizon", "stop_id": stop["id"], "reason": "Stop outside schedule horizon"})
        timing.append({"departure": current_time, "arrival": arrival, "start": start, "end": finish, "travel": leg.minutes, "distance": leg.distance_km, "wait": max(0, (start - arrival).total_seconds() / 60)})
        travel_total += leg.minutes
        current_time, current_loc = finish, stop["location"]

    try:
        final_leg = provider.leg(current_loc, end_location, mode)
        if final_leg.minutes < 0 or final_leg.distance_km < 0:
            raise ValueError("Travel estimates cannot be negative")
        travel_total += final_leg.minutes
        if current_time + timedelta(minutes=final_leg.minutes) > end_at:
            conflicts.append({"constraint_type": "schedule_horizon", "reason": "End journey exceeds schedule horizon"})
    except (KeyError, TypeError, ValueError) as exc:
        final_leg = Leg(0, 0)
        conflicts.append({"constraint_type": "provider_error", "reason": str(exc)})
    for constraint in constraints:
        if constraint.get("hardness", "hard") == "hard" and constraint.get("type") == "max_travel_minutes":
            maximum = constraint.get("parameters", {}).get("minutes")
            if maximum is not None and travel_total > float(maximum):
                conflicts.append({"constraint_type": "max_travel_minutes", "reason": "Maximum travel time exceeded"})
    return not conflicts, conflicts, timing


def metrics(stops, req, provider, mode):
    ok, conflicts, timing = validate(stops, req["start_at"], req["end_at"], req["start_location"], req["end_location"], provider, mode, req.get("constraints", []))
    last_loc = stops[-1]["location"] if stops else req["start_location"]
    try:
        endleg = provider.leg(last_loc, req["end_location"], mode)
    except (KeyError, TypeError, ValueError):
        endleg = Leg(0, 0)
    travel = sum(x["travel"] for x in timing) + endleg.minutes
    distance = sum(x["distance"] for x in timing) + endleg.distance_km
    timeline = []
    for stop, item in zip(stops, timing):
        timeline.append({
            "stop_id": stop["id"],
            "title": stop["title"],
            "location": stop["location"],
            "departed_at": item["departure"].isoformat(),
            "arrival_at": item["arrival"].isoformat(),
            "start_at": item["start"].isoformat(),
            "end_at": item["end"].isoformat(),
            "travel_minutes": round(item["travel"], 2),
            "distance_km": round(item["distance"], 2),
            "waiting_minutes": round(item["wait"], 2),
        })
    return_departure = timing[-1]["end"] if timing else req["start_at"]
    return {"feasible": ok, "travel_minutes": round(travel, 2), "distance_km": round(distance, 2), "waiting_minutes": round(sum(x["wait"] for x in timing), 2), "stop_count": len(stops), "timeline": timeline, "return_departure_at": return_departure.isoformat(), "return_arrival_at": (return_departure + timedelta(minutes=endleg.minutes)).isoformat(), "return_travel_minutes": round(endleg.minutes, 2)} , conflicts


def plan(req, provider=None, mode="Walking"):
    provider = CachedTravelProvider(provider or MockTravelProvider())
    existing = req["existing_stops"]
    before, before_conflicts = metrics(existing, req, provider, mode)
    if not before["feasible"]:
        return {"feasible": False, "stops": existing, "metrics": {"before": before, "after": None}, "conflicts": before_conflicts, "explanation_facts": ["The existing schedule violates one or more hard constraints."]}
    candidates, evals = [], 0
    limit = max(0, int(req.get("max_candidate_evaluations", 500)))
    destinations = req.get("candidate_stops", [])
    if not destinations:
        candidates.append(existing)
        if req.get("allow_reordering_flexible_stops", False):
            flexible = [i for i, stop in enumerate(existing) if not stop.get("fixed_start")]
            max_reordered = max(0, int(req.get("max_reordered_stops", 3)))
            for a, b in zip(flexible, flexible[1:]):
                if evals >= limit or evals >= max_reordered:
                    break
                alt = list(existing)
                alt[a], alt[b] = alt[b], alt[a]
                candidates.append(alt)
                evals += 1
    else:
        for destination in destinations:
            for i in range(len(existing) + 1):
                if evals >= limit:
                    break
                alt = list(existing)
                alt.insert(i, destination)
                candidates.append(alt)
                evals += 1
            if evals >= limit:
                break
    if not candidates:
        return {"feasible": False, "stops": existing, "metrics": {"before": before, "after": None}, "conflicts": [{"constraint_type": "candidate_limit", "reason": "No candidate positions were evaluated"}], "explanation_facts": ["Increase the candidate evaluation limit and try again."]}

    valid = []
    weights = req.get("weights", {"travel_time": 5, "distance": 1, "disruption": 4})
    original_ids = [s["id"] for s in existing]
    for candidate in candidates:
        after, _ = metrics(candidate, req, provider, mode)
        if not after["feasible"]:
            continue
        common = [s["id"] for s in candidate if s["id"] in original_ids]
        disruption = sum(a != b for a, b in zip(original_ids, common))
        score = weights.get("travel_time", 5) * after["travel_minutes"] / max(60, before["travel_minutes"]) + weights.get("distance", 1) * after["distance_km"] / max(10, before["distance_km"]) + weights.get("disruption", 4) * disruption / max(1, len(existing))
        valid.append((score, candidate, after))
    if not valid:
        return {"feasible": False, "stops": existing, "metrics": {"before": before, "after": None}, "conflicts": [{"constraint_type": "no_feasible_candidate", "reason": "No candidate plan satisfies hard constraints"}], "explanation_facts": ["Try another destination or adjust a user-approved constraint."]}
    score, best, after = min(valid, key=lambda item: (item[0], [s["id"] for s in item[1]]))
    return {"feasible": True, "stops": best, "metrics": {"before": before, "after": after, "score": score}, "conflicts": [], "explanation_facts": [f"Travel time changes by {after['travel_minutes'] - before['travel_minutes']:+.1f} minutes.", "All configured hard constraints passed validation."]}


class CachedTravelProvider:
    """Memoize route legs so each distinct pair is fetched at most once per plan."""

    def __init__(self, provider):
        self.provider = provider
        self.cache = {}

    @staticmethod
    def _key(location):
        return (round(float(location["latitude"]), 7), round(float(location["longitude"]), 7))

    def leg(self, origin, destination, mode="Walking"):
        key = (self._key(origin), self._key(destination), mode)
        if key not in self.cache:
            self.cache[key] = self.provider.leg(origin, destination, mode)
        return self.cache[key]


def optimize_schedule(req, provider=None, mode="Walking"):
    """Find the lowest-cost feasible ordering within a bounded search budget."""
    provider = CachedTravelProvider(provider or MockTravelProvider())
    stops = req["existing_stops"]
    # A separate journey for each errand from the same start to the same finish is
    # the comparison baseline for the combined itinerary.
    savings = calculate_distance_savings(stops, req, provider, mode, None)
    separate_trip_km = savings["baseline_km"]
    budget = max(1, int(req.get("max_candidate_evaluations", 500)))
    # A schedule with many stops can still be planned safely: enumerate a bounded
    # subset of stable input-order permutations, and tell callers when search was capped.
    possibilities = permutations(stops) if len(stops) <= 8 else iter([tuple(stops)])
    search_truncated = len(stops) > 8 or factorial(len(stops)) > budget
    best = None
    evaluated = 0
    all_conflicts = []
    for candidate in possibilities:
        if evaluated >= budget:
            break
        evaluated += 1
        after, conflicts = metrics(list(candidate), req, provider, mode)
        if not after["feasible"]:
            all_conflicts.extend(conflicts)
            continue
        disruption = sum(a != b for a, b in zip([s["id"] for s in stops], [s["id"] for s in candidate]))
        score = after["travel_minutes"] + after["distance_km"] * 0.1 + disruption * 2 + after["waiting_minutes"] * 0.25
        tie_break = tuple(s["id"] for s in candidate)
        if best is None or (score, tie_break) < (best[0], best[1]):
            best = (score, tie_break, list(candidate), after)

    if best is None:
        unique_conflicts = []
        seen = set()
        for conflict in all_conflicts:
            marker = (conflict.get("constraint_type"), conflict.get("stop_id"), conflict.get("reason"))
            if marker not in seen:
                seen.add(marker)
                unique_conflicts.append(conflict)
        if evaluated == 0:
            unique_conflicts = [{"constraint_type": "candidate_limit", "reason": "No schedule order was evaluated"}]
        return {"feasible": False, "stops": stops, "metrics": {"before": None, "after": None}, "conflicts": unique_conflicts, "explanation_facts": ["No ordering in the evaluated search budget satisfies all hard constraints."], "evaluated_orders": evaluated, "search_truncated": search_truncated}

    _, _, ordered, after = best
    savings = calculate_distance_savings(ordered, req, provider, mode, after["distance_km"])
    after["distance_savings"] = savings
    return {"feasible": True, "stops": ordered, "metrics": {"before": {"distance_km": round(separate_trip_km, 2)}, "after": after, "distance_savings": savings, "score": round(best[0], 3)}, "conflicts": [], "explanation_facts": [f"Evaluated {evaluated} itinerary order(s).", f"Estimated travel: {after['travel_minutes']:.1f} minutes over {after['distance_km']:.1f} km.", "All configured hard constraints passed validation."], "evaluated_orders": evaluated, "search_truncated": search_truncated}


def calculate_distance_savings(stops, req, provider, mode, planned_km):
    separate_trip_km = 0.0
    try:
        for stop in stops:
            separate_trip_km += provider.leg(req["start_location"], stop["location"], mode).distance_km
            separate_trip_km += provider.leg(stop["location"], req["end_location"], mode).distance_km
    except (KeyError, TypeError, ValueError):
        separate_trip_km = 0.0
    if planned_km is None:
        return {"baseline_km": round(separate_trip_km, 2), "planned_km": None,
                "saved_km": None, "saved_percent": None,
                "baseline": "one separate start-to-finish journey per stop"}
    difference = round(separate_trip_km - planned_km, 2)
    return {"baseline_km": round(separate_trip_km, 2), "planned_km": round(planned_km, 2),
            "saved_km": max(0, difference), "additional_km": max(0, -difference),
            "saved_percent": round(max(0, difference) / separate_trip_km * 100, 1) if separate_trip_km else 0,
            "separate_trips": len(stops), "combined_trips": 1 if stops else 0,
            "trips_saved": max(0, len(stops) - 1),
            "baseline": "one separate start-to-finish journey per stop"}
