from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.config import settings
from app.db import Base, engine, get_db
from app import models
from app.schemas import ScheduleCreate, AddStopRequest, ReplanRequest, AgentRequest, ApproveRequest, RejectRequest, PreferenceIn
from app.service import create_schedule, get_schedule, add_destination, replan, get_proposal, approve, reject, snapshot, row_stop, uid
from app.integrations import parse_intent, search_places

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    yield

app=FastAPI(title="EcoRoute API",version="0.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=settings.origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

def proposal_json(p):
    return {"id":p.id,"schedule_id":p.schedule_id,"status":p.status,"feasible":p.status in ("pending","approved"),"base_revision":p.base_revision,"proposed_stops":p.proposed_stops,"metrics":p.metrics,"conflicts":p.conflicts,"explanation_facts":p.explanation_facts,"expires_at":p.expires_at.isoformat()}

@app.get("/")
def root(): return {"name":"EcoRoute API","docs":"/docs"}
@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/v1/schedules")
def create(req:ScheduleCreate,db:Session=Depends(get_db)):
    s=create_schedule(db,req)
    return {"id":s.id,"user_id":s.user_id,"date":s.schedule_date.isoformat(),"current_revision":s.current_revision,"status":s.status}

@app.get("/v1/schedules/{sid}")
def read_schedule(sid:str,user_id:str,db:Session=Depends(get_db)):
    s=get_schedule(db,sid,user_id)
    rows=db.scalars(select(models.Stop).where(models.Stop.schedule_id==sid).order_by(models.Stop.order_index)).all()
    cs=db.scalars(select(models.ScheduleConstraint).where(models.ScheduleConstraint.schedule_id==sid)).all()
    return {"id":s.id,"user_id":s.user_id,"date":s.schedule_date.isoformat(),"timezone":s.timezone,"start_at":s.start_at.isoformat(),"end_at":s.end_at.isoformat(),"start_location":s.start_location,"end_location":s.end_location,"status":s.status,"current_revision":s.current_revision,"stops":[row_stop(x) for x in rows],"constraints":[{"type":c.type,"hardness":c.hardness,"weight":c.weight,"parameters":c.parameters} for c in cs]}

@app.post("/v1/schedules/{sid}/stops")
def add_stop(sid:str,req:AddStopRequest,db:Session=Depends(get_db)):
    return proposal_json(add_destination(db,sid,req))

@app.post("/v1/schedules/{sid}/replan")
def replan_route(sid:str,req:ReplanRequest,db:Session=Depends(get_db)):
    return proposal_json(replan(db,sid,req))

@app.post("/v1/agent/requests")
def agent(req:AgentRequest,db:Session=Depends(get_db)):
    intent=parse_intent(req.text,req.timezone)
    if intent.get("clarification_needed"):
        return {"status":"clarification_required","question":intent.get("clarification_question"),"intent":intent}
    op=intent.get("operation","clarify")
    if op=="add_destination":
        if not req.schedule_id: raise HTTPException(422,"schedule_id is required")
        s=get_schedule(db,req.schedule_id,req.user_id)
        query=intent.get("destination_query") or req.text
        places=search_places(query,[s.start_location["longitude"],s.start_location["latitude"]],10)
        return {"status":"destination_candidates" if places else "needs_destination_selection","intent":intent,"candidates":places,"message":"Choose a place, verify any product details, then submit it to the stops endpoint."}
    if op=="replan":
        if not req.schedule_id: raise HTTPException(422,"schedule_id is required")
        return proposal_json(replan(db,req.schedule_id,ReplanRequest(user_id=req.user_id,reason=req.text)))
    return {"status":"clarification_required","question":"Create a schedule first, then provide its schedule_id to add destinations or replan.","intent":intent}

@app.get("/v1/proposals/{pid}")
def read_proposal(pid:str,user_id:str,db:Session=Depends(get_db)):
    return proposal_json(get_proposal(db,pid,user_id))

@app.post("/v1/proposals/{pid}/approve")
def approve_route(pid:str,req:ApproveRequest,db:Session=Depends(get_db)):
    p=get_proposal(db,pid,req.user_id)
    return approve(db,p,req)

@app.post("/v1/proposals/{pid}/reject")
def reject_route(pid:str,req:RejectRequest,db:Session=Depends(get_db)):
    p=get_proposal(db,pid,req.user_id)
    return reject(db,p,req.reason)

@app.get("/v1/schedules/{sid}/revisions")
def revisions(sid:str,user_id:str,db:Session=Depends(get_db)):
    s=get_schedule(db,sid,user_id)
    rows=db.scalars(select(models.PlanRevision).where(models.PlanRevision.schedule_id==sid).order_by(models.PlanRevision.revision_number.desc())).all()
    return [{"id":r.id,"revision_number":r.revision_number,"snapshot":r.snapshot,"reason":r.reason,"created_at":r.created_at.isoformat()} for r in rows]

@app.get("/v1/preferences")
def preferences(user_id:str,db:Session=Depends(get_db)):
    rows=db.scalars(select(models.Preference).where(models.Preference.user_id==user_id)).all()
    return [{"id":r.id,"key":r.key,"value":r.value,"confidence":r.confidence,"source":r.source,"updated_at":r.updated_at.isoformat()} for r in rows]

@app.post("/v1/preferences")
def set_preference(req:PreferenceIn,db:Session=Depends(get_db)):
    row=db.scalar(select(models.Preference).where(models.Preference.user_id==req.user_id,models.Preference.key==req.key))
    if row:
        row.value=req.value; row.confidence=req.confidence; row.source=req.source
    else:
        row=models.Preference(id=uid(),user_id=req.user_id,key=req.key,value=req.value,confidence=req.confidence,source=req.source); db.add(row)
    db.commit()
    return {"id":row.id,"user_id":row.user_id,"key":row.key,"value":row.value,"confidence":row.confidence,"source":row.source}
