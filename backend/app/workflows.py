import json
from uuid import uuid4

import boto3
from botocore.config import Config
from fastapi import HTTPException

from app.config import settings


def _step_functions_client():
    return boto3.client(
        "stepfunctions",
        region_name=settings.aws_region,
        config=Config(connect_timeout=3, read_timeout=10, retries={"max_attempts": 2}),
    )


def start_planning_execution(*, user_id: str, text: str, schedule_id: str | None, timezone: str) -> dict:
    if not settings.step_functions_enabled:
        raise HTTPException(503, "Step Functions workflow is disabled")
    if not settings.step_functions_state_machine_arn:
        raise HTTPException(503, "STEP_FUNCTIONS_STATE_MACHINE_ARN is required")
    payload = {
        "user_id": user_id,
        "request_text": text,
        "schedule_id": schedule_id,
        "timezone": timezone,
        "request_id": str(uuid4()),
    }
    try:
        result = _step_functions_client().start_execution(
            stateMachineArn=settings.step_functions_state_machine_arn,
            name=f"ecoroute-{payload['request_id']}",
            input=json.dumps(payload, separators=(",", ":")),
        )
    except Exception as exc:
        raise HTTPException(502, "Could not start the planning workflow") from exc
    return {"execution_arn": result["executionArn"], "started_at": result["startDate"].isoformat(), "status": "running"}


def get_planning_execution(execution_arn: str, user_id: str) -> dict:
    if not settings.step_functions_enabled:
        raise HTTPException(503, "Step Functions workflow is disabled")
    try:
        result = _step_functions_client().describe_execution(executionArn=execution_arn)
    except Exception as exc:
        raise HTTPException(502, "Could not retrieve the planning workflow") from exc
    try:
        request = json.loads(result.get("input", "{}"))
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(502, "Workflow returned invalid execution input") from exc
    if request.get("user_id") != user_id:
        raise HTTPException(404, "Workflow not found")
    response = None
    if result.get("output"):
        try:
            response = json.loads(result["output"])
        except (TypeError, json.JSONDecodeError):
            response = None
    return {
        "execution_arn": result.get("executionArn"),
        "status": result.get("status"),
        "started_at": result.get("startDate").isoformat() if result.get("startDate") else None,
        "stopped_at": result.get("stopDate").isoformat() if result.get("stopDate") else None,
        "result": response,
        "error": result.get("error"),
        "cause": result.get("cause"),
    }
