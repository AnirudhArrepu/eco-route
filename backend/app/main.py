from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.config import settings
from app.db import Base, engine, get_db
from app import models
from app.schemas import ScheduleCreate, SchedulePreview, AddStopRequest, ReplanRequest, AgentRequest, TaskExtractionRequest, RoutePlaceSearchRequest, ApproveRequest, RejectRequest, PreferenceIn, PreferenceUpdate, RoutineCreate, RoutineUpdate, SignUpRequest, ConfirmSignUpRequest, EmailRequest, LoginRequest, RefreshTokenRequest
from app.service import create_schedule, preview_schedule, get_schedule, get_schedule_timeline, add_destination, replan, get_proposal, approve, reject, snapshot, row_stop, uid, user_travel_mode
from app.integrations import parse_intent, parse_replan_request, search_places, search_places_on_route, extract_tasks
from app.auth import authenticated_user, resolve_user_id
from app import cognito
from app.strands_agent import interpret_with_strands
from app.workflows import start_planning_execution, get_planning_execution

@asynccontextmanager
async def lifespan(app):
    if settings.auto_migrate:
        from alembic import command
        from alembic.config import Config
        migration_config=Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        migration_config.set_main_option("sqlalchemy.url",settings.database_url.replace("%","%%"))
        command.upgrade(migration_config,"head")
    yield

app=FastAPI(title="EcoRoute API",version="0.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=False,allow_methods=["*"],allow_headers=["*"])

@app.post("/v1/auth/signup")
def auth_sign_up(req:SignUpRequest):
    return cognito.sign_up(req.email,req.password)

@app.post("/v1/auth/confirm")
def auth_confirm(req:ConfirmSignUpRequest):
    return cognito.confirm_sign_up(req.email,req.code)

@app.post("/v1/auth/resend-confirmation")
def auth_resend_confirmation(req:EmailRequest):
    return cognito.resend_confirmation(req.email)

@app.post("/v1/auth/login")
def auth_login(req:LoginRequest):
    return cognito.log_in(req.email,req.password)

@app.post("/v1/auth/refresh")
def auth_refresh(req:RefreshTokenRequest):
    return cognito.refresh(req.refresh_token)

@app.get("/v1/auth/me")
def auth_me(principal:str|None=Depends(authenticated_user)):
    if not principal:
        raise HTTPException(401,"Sign in to get the current user")
    return {"user_id":principal}

def proposal_json(p):
    return {"id":p.id,"schedule_id":p.schedule_id,"status":p.status,"feasible":p.status in ("pending","approved"),"base_revision":p.base_revision,"proposed_stops":p.proposed_stops,"metrics":p.metrics,"conflicts":p.conflicts,"explanation_facts":p.explanation_facts,"expires_at":p.expires_at.isoformat()}

def owner(user_id, principal):
    return resolve_user_id(user_id, principal)

@app.get("/")
def root(): return {"name":"EcoRoute API","docs":"/docs"}

@app.get("/app",include_in_schema=False)
def web_app(): return FileResponse(Path(__file__).resolve().parent.parent / "web" / "index.html")

@app.get("/app/{asset}",include_in_schema=False)
def web_asset(asset:str):
    if asset not in {"app.js","style.css"}:
        raise HTTPException(404,"Asset not found")
    return FileResponse(Path(__file__).resolve().parent.parent / "web" / asset)
@app.get("/health")
def health(): return {"status":"ok"}

@app.get("/ready")
def ready(db:Session=Depends(get_db)):
    try:
        db.execute(select(1))
    except Exception as exc:
        raise HTTPException(503,"Database is unavailable") from exc
    return {"status":"ready"}

@app.post("/v1/schedules")
def create(req:ScheduleCreate,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    s=create_schedule(db,req)
    return {"id":s.id,"user_id":s.user_id,"date":s.schedule_date.isoformat(),"current_revision":s.current_revision,"status":s.status,"metrics":s.planning_metrics,"timeline":s.planning_timeline,"travel_estimate_source":s.planning_source}

@app.post("/v1/schedules/preview")
def preview(req:SchedulePreview,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    return preview_schedule(db,req,req.max_candidate_evaluations)

@app.post("/v1/agent/extract-tasks")
def extract_plan_tasks(req:TaskExtractionRequest,principal:str|None=Depends(authenticated_user)):
    return extract_tasks(req.text,req.date,req.timezone)

@app.get("/v1/places/search")
def place_search(query:str,latitude:float|None=None,longitude:float|None=None,principal:str|None=Depends(authenticated_user)):
    if not query.strip():
        raise HTTPException(422,"query must not be empty")
    bias=[longitude,latitude] if latitude is not None and longitude is not None else None
    if (latitude is None) != (longitude is None):
        raise HTTPException(422,"latitude and longitude must be supplied together")
    if latitude is not None and not -90 <= latitude <= 90:
        raise HTTPException(422,"latitude must be between -90 and 90")
    if longitude is not None and not -180 <= longitude <= 180:
        raise HTTPException(422,"longitude must be between -180 and 180")
    return {"places":search_places(query,bias,10)}

@app.post("/v1/places/route-search")
def route_place_search(req:RoutePlaceSearchRequest,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    mode=user_travel_mode(db,principal) if principal else "Walking"
    return {"places":search_places_on_route(
        req.query,
        req.start_location.model_dump(mode="json"),
        req.end_location.model_dump(mode="json"),
        mode,
        req.max_results,
    )}

@app.get("/v1/schedules/{sid}")
def read_schedule(sid:str,user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    s=get_schedule(db,sid,user_id)
    rows=db.scalars(select(models.Stop).where(models.Stop.schedule_id==sid).order_by(models.Stop.order_index)).all()
    cs=db.scalars(select(models.ScheduleConstraint).where(models.ScheduleConstraint.schedule_id==sid)).all()
    return {"id":s.id,"user_id":s.user_id,"date":s.schedule_date.isoformat(),"timezone":s.timezone,"start_at":s.start_at.isoformat(),"end_at":s.end_at.isoformat(),"start_location":s.start_location,"end_location":s.end_location,"status":s.status,"current_revision":s.current_revision,"stops":[row_stop(x) for x in rows],"constraints":[{"type":c.type,"hardness":c.hardness,"weight":c.weight,"parameters":c.parameters} for c in cs]}

@app.get("/v1/schedules/{sid}/timeline")
def timeline(sid:str,user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    return get_schedule_timeline(db,sid,user_id)

@app.post("/v1/schedules/{sid}/stops")
def add_stop(sid:str,req:AddStopRequest,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    return proposal_json(add_destination(db,sid,req))

@app.post("/v1/schedules/{sid}/replan")
def replan_route(sid:str,req:ReplanRequest,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    return proposal_json(replan(db,sid,req))

@app.post("/v1/agent/requests")
def agent(req:AgentRequest,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    if settings.step_functions_enabled:
        return start_planning_execution(user_id=req.user_id,text=req.text,schedule_id=req.schedule_id,timezone=req.timezone)
    schedule_context=None
    bias=None
    if req.schedule_id:
        schedule=get_schedule(db,req.schedule_id,req.user_id)
        rows=db.scalars(select(models.Stop).where(models.Stop.schedule_id==schedule.id).order_by(models.Stop.order_index)).all()
        schedule_context={
            "date":schedule.schedule_date.isoformat(),
            "start_location":schedule.start_location.get("label"),
            "end_location":schedule.end_location.get("label"),
            "stops":[{"id":row.id,"title":row.title,"type":row.type,"location":row.location} for row in rows],
        }
        bias=[schedule.start_location["longitude"],schedule.start_location["latitude"]]
    if settings.strands_agent_enabled:
        intent=interpret_with_strands(req.text,req.timezone,bias,schedule_context)
    else:
        intent=parse_intent(req.text,req.timezone,schedule_context)
    if intent.get("clarification_needed"):
        return {"status":"clarification_required","question":intent.get("clarification_question"),"intent":intent}
    op=intent.get("operation","clarify")
    if op=="add_destination":
        if not req.schedule_id: raise HTTPException(422,"schedule_id is required")
        s=get_schedule(db,req.schedule_id,req.user_id)
        query=intent.get("destination_query") or req.text
        places=search_places(query,[s.start_location["longitude"],s.start_location["latitude"]],10)
        message="Choose a place, verify any product details, then submit it to the stops endpoint."
        if intent.get("intent_source")=="local_fallback":
            message="The language model was unavailable; this request was interpreted with simple rules. Review the place suggestions carefully. " + message
        return {"status":"destination_candidates" if places else "needs_destination_selection","intent":intent,"candidates":places,"message":message}
    if op=="replan":
        if not req.schedule_id: raise HTTPException(422,"schedule_id is required")
        schedule=get_schedule(db,req.schedule_id,req.user_id)
        rows=db.scalars(select(models.Stop).where(models.Stop.schedule_id==schedule.id).order_by(models.Stop.order_index)).all()
        stops=[row_stop(row) for row in rows]
        parsed_change=parse_replan_request(req.text,stops,schedule.timezone or req.timezone,{
            "date":schedule.schedule_date.isoformat(),
            "start_at":schedule.start_at.isoformat(),
            "end_at":schedule.end_at.isoformat(),
            "start_location":(schedule.start_location or {}).get("label"),
            "end_location":(schedule.end_location or {}).get("label"),
        })
        if parsed_change["clarification_question"]:
            return {"status":"clarification_required","question":parsed_change["clarification_question"],"intent":intent}
        if not parsed_change["updates"] and parsed_change.get("stop_order") is None and not parsed_change.get("optimize_route"):
            return {"status":"clarification_required","question":"What should change? You can adjust a stop's time or duration, choose a stop order, or ask me to optimize the route.","intent":intent}
        change=ReplanRequest(user_id=req.user_id,updates=parsed_change["updates"],stop_order=parsed_change.get("stop_order"),reason=req.text)
        result=proposal_json(replan(db,req.schedule_id,change))
        if parsed_change["source"]=="local_fallback":
            result["explanation_facts"].append("Mantle was unavailable; this change was interpreted with simple rules. Review the proposed timing and stop order carefully.")
        return result
    return {"status":"clarification_required","question":"Create a schedule first, then provide its schedule_id to add destinations or replan.","intent":intent}

@app.get("/v1/proposals/{pid}")
def read_proposal(pid:str,user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    return proposal_json(get_proposal(db,pid,user_id))

@app.post("/v1/proposals/{pid}/approve")
def approve_route(pid:str,req:ApproveRequest,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    p=get_proposal(db,pid,req.user_id)
    return approve(db,p,req)

@app.post("/v1/proposals/{pid}/reject")
def reject_route(pid:str,req:RejectRequest,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    p=get_proposal(db,pid,req.user_id)
    return reject(db,p,req.reason)

@app.get("/v1/schedules/{sid}/revisions")
def revisions(sid:str,user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    s=get_schedule(db,sid,user_id)
    rows=db.scalars(select(models.PlanRevision).where(models.PlanRevision.schedule_id==sid).order_by(models.PlanRevision.revision_number.desc())).all()
    return [{"id":r.id,"revision_number":r.revision_number,"snapshot":r.snapshot,"reason":r.reason,"created_at":r.created_at.isoformat()} for r in rows]

@app.get("/v1/preferences")
def preferences(user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    rows=db.scalars(select(models.Preference).where(models.Preference.user_id==user_id)).all()
    return [{"id":r.id,"key":r.key,"value":r.value,"confidence":r.confidence,"source":r.source,"updated_at":r.updated_at.isoformat()} for r in rows]

@app.post("/v1/preferences")
def set_preference(req:PreferenceIn,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    row=db.scalar(select(models.Preference).where(models.Preference.user_id==req.user_id,models.Preference.key==req.key))
    if row:
        row.value=req.value; row.confidence=req.confidence; row.source=req.source
    else:
        row=models.Preference(id=uid(),user_id=req.user_id,key=req.key,value=req.value,confidence=req.confidence,source=req.source); db.add(row)
    db.commit()
    return {"id":row.id,"user_id":row.user_id,"key":row.key,"value":row.value,"confidence":row.confidence,"source":row.source}

@app.put("/v1/preferences/{key}")
def update_preference(key:str,req:PreferenceUpdate,user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    row=db.scalar(select(models.Preference).where(models.Preference.user_id==user_id,models.Preference.key==key))
    if not row:
        raise HTTPException(404,"Preference not found")
    row.value=req.value; row.confidence=req.confidence; row.source=req.source
    db.commit()
    return {"id":row.id,"key":row.key,"value":row.value,"confidence":row.confidence,"source":row.source,"updated_at":row.updated_at.isoformat()}

@app.delete("/v1/preferences/{key}",status_code=204)
def delete_preference(key:str,user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    row=db.scalar(select(models.Preference).where(models.Preference.user_id==user_id,models.Preference.key==key))
    if not row:
        raise HTTPException(404,"Preference not found")
    db.delete(row); db.commit()

@app.get("/v1/routines")
def routines(user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    rows=db.scalars(select(models.Routine).where(models.Routine.user_id==user_id).order_by(models.Routine.weekday,models.Routine.name)).all()
    return [{"id":r.id,"name":r.name,"weekday":r.weekday,"stop":r.stop,"active":r.active,"created_at":r.created_at.isoformat()} for r in rows]

@app.post("/v1/routines",status_code=201)
def create_routine(req:RoutineCreate,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    r=req.routine
    row=models.Routine(id=uid(),user_id=req.user_id,name=r.name,weekday=r.weekday,stop=r.stop.model_dump(mode="json",exclude={"id"}),active=r.active)
    db.add(row); db.commit(); db.refresh(row)
    return {"id":row.id,"name":row.name,"weekday":row.weekday,"stop":row.stop,"active":row.active}

@app.put("/v1/routines/{routine_id}")
def update_routine(routine_id:str,req:RoutineUpdate,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    req=req.model_copy(update={"user_id":owner(req.user_id,principal)})
    row=db.scalar(select(models.Routine).where(models.Routine.id==routine_id,models.Routine.user_id==req.user_id))
    if not row:
        raise HTTPException(404,"Routine not found")
    row.name=req.routine.name; row.weekday=req.routine.weekday; row.stop=req.routine.stop.model_dump(mode="json",exclude={"id"}); row.active=req.routine.active
    db.commit()
    return {"id":row.id,"name":row.name,"weekday":row.weekday,"stop":row.stop,"active":row.active}

@app.delete("/v1/routines/{routine_id}",status_code=204)
def delete_routine(routine_id:str,user_id:str|None=None,db:Session=Depends(get_db),principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    row=db.scalar(select(models.Routine).where(models.Routine.id==routine_id,models.Routine.user_id==user_id))
    if not row:
        raise HTTPException(404,"Routine not found")
    db.delete(row); db.commit()

@app.get("/v1/workflows/status")
def workflow_status(execution_arn:str,user_id:str|None=None,principal:str|None=Depends(authenticated_user)):
    user_id=owner(user_id,principal)
    return get_planning_execution(execution_arn,user_id)
