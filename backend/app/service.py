from datetime import datetime, timezone, timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app import models
from app.schemas import ScheduleCreate, StopIn, ConstraintIn, AddStopRequest, ReplanRequest
from app.planner import plan
from app.integrations import TravelProvider
from app.config import settings

def uid(): return str(uuid4())

def stop_dict(s, index):
    return {"id":s["id"],"title":s["title"],"type":s.get("type","errand"),"location":s["location"],"duration_minutes":s["duration_minutes"],"earliest_start":s.get("earliest_start"),"latest_start":s.get("latest_start"),"latest_end":s.get("latest_end"),"fixed_start":s.get("fixed_start"),"opening_hours":s.get("opening_hours"),"priority":s.get("priority",3),"mandatory":s.get("mandatory",False),"status":s.get("status","planned"),"source":s.get("source","user"),"attributes":s.get("attributes",{}),"order_index":index}

def row_stop(row):
    return {"id":row.id,"title":row.title,"type":row.type,"location":row.location,"duration_minutes":row.duration_minutes,"earliest_start":row.earliest_start.isoformat() if row.earliest_start else None,"latest_start":row.latest_start.isoformat() if row.latest_start else None,"latest_end":row.latest_end.isoformat() if row.latest_end else None,"fixed_start":row.fixed_start.isoformat() if row.fixed_start else None,"opening_hours":row.opening_hours,"priority":row.priority,"mandatory":row.mandatory,"status":row.status,"source":row.source,"attributes":row.attributes or {}}

def input_stop(s: StopIn):
    d=s.model_dump(mode="json")
    d["id"]=d["id"] or uid()
    return d

def snapshot(db,schedule):
    rows=db.scalars(select(models.Stop).where(models.Stop.schedule_id==schedule.id).order_by(models.Stop.order_index)).all()
    return {"schedule_id":schedule.id,"revision":schedule.current_revision,"date":schedule.schedule_date.isoformat(),"timezone":schedule.timezone,"start_at":schedule.start_at.isoformat(),"end_at":schedule.end_at.isoformat(),"start_location":schedule.start_location,"end_location":schedule.end_location,"stops":[row_stop(x) for x in rows]}

def create_schedule(db,req:ScheduleCreate):
    if req.end_at<=req.start_at: raise HTTPException(422,"end_at must be after start_at")
    if req.start_at.tzinfo is None or req.end_at.tzinfo is None: raise HTTPException(422,"Schedule timestamps must include a timezone")
    for stop in req.stops:
        for name in ("earliest_start","latest_start","latest_end","fixed_start"):
            value=getattr(stop,name)
            if value is not None and value.tzinfo is None: raise HTTPException(422,f"{name} must include a timezone")
        if stop.earliest_start and stop.latest_start and stop.earliest_start>stop.latest_start:
            raise HTTPException(422,"earliest_start must not be after latest_start")
    sid=uid()
    s=models.Schedule(id=sid,user_id=req.user_id,schedule_date=req.date,timezone=req.timezone,start_at=req.start_at,end_at=req.end_at,start_location=req.start_location.model_dump(mode="json"),end_location=req.end_location.model_dump(mode="json"),current_revision=1,status="active")
    db.add(s); db.flush()
    for i,st in enumerate(req.stops):
        d=input_stop(st)
        db.add(models.Stop(id=d["id"],schedule_id=sid,order_index=i,title=d["title"],type=d["type"],location=d["location"],duration_minutes=d["duration_minutes"],earliest_start=st.earliest_start,latest_start=st.latest_start,latest_end=st.latest_end,fixed_start=st.fixed_start,opening_hours=d["opening_hours"],priority=d["priority"],mandatory=d["mandatory"],status=d["status"],source=d["source"],attributes=d["attributes"]))
    for c in req.constraints:
        db.add(models.ScheduleConstraint(id=uid(),schedule_id=sid,type=c.type,hardness=c.hardness,weight=c.weight,parameters=c.parameters))
    db.flush()
    db.add(models.PlanRevision(id=uid(),schedule_id=sid,revision_number=1,snapshot=snapshot(db,s),reason="Initial schedule"))
    db.commit(); db.refresh(s)
    return s

def get_schedule(db,sid,user_id):
    s=db.get(models.Schedule,sid)
    if not s or s.user_id!=user_id: raise HTTPException(404,"Schedule not found")
    return s

def make_plan_request(db,s,existing,candidates,constraints,allow_reorder,max_reorder):
    stored=db.scalars(select(models.ScheduleConstraint).where(models.ScheduleConstraint.schedule_id==s.id)).all()
    cs=[{"type":c.type,"hardness":c.hardness,"weight":c.weight,"parameters":c.parameters or {}} for c in stored]
    cs += [c.model_dump() for c in constraints]
    return {"start_at":s.start_at,"end_at":s.end_at,"start_location":s.start_location,"end_location":s.end_location,"existing_stops":existing,"candidate_stops":candidates,"constraints":cs,"allow_reordering_flexible_stops":allow_reorder,"max_reordered_stops":max_reorder,"max_candidate_evaluations":500,"weights":{"travel_time":5,"distance":1,"disruption":4}}

def save_proposal(db,s,user_id,operation,result):
    p=models.Proposal(id=uid(),schedule_id=s.id,user_id=user_id,base_revision=s.current_revision,status="pending" if result["feasible"] else "infeasible",operation=operation,proposed_stops=[stop_dict(x,i) for i,x in enumerate(result["stops"])],metrics=result["metrics"],conflicts=result["conflicts"],explanation_facts=result["explanation_facts"],created_at=datetime.now(timezone.utc),expires_at=datetime.now(timezone.utc)+timedelta(minutes=settings.proposal_ttl_minutes))
    db.add(p); db.commit(); db.refresh(p); return p

def add_destination(db,sid,req:AddStopRequest):
    s=get_schedule(db,sid,req.user_id)
    rows=db.scalars(select(models.Stop).where(models.Stop.schedule_id==sid).order_by(models.Stop.order_index)).all()
    existing=[row_stop(x) for x in rows]
    dest=input_stop(req.destination)
    r=make_plan_request(db,s,existing,[dest],req.constraints,req.allow_reordering_flexible_stops,req.max_reordered_stops)
    try:
        result=plan(r,TravelProvider())
    except Exception as exc:
        raise HTTPException(502,"Travel provider failed to calculate a route") from exc
    return save_proposal(db,s,req.user_id,"add_destination",result)

def replan(db,sid,req:ReplanRequest):
    s=get_schedule(db,sid,req.user_id)
    rows=db.scalars(select(models.Stop).where(models.Stop.schedule_id==sid).order_by(models.Stop.order_index)).all()
    existing=[row_stop(x) for x in rows]
    for sid2,updates in req.updates.items():
        found=next((x for x in existing if x["id"]==sid2),None)
        if not found: raise HTTPException(422,f"Unknown stop id: {sid2}")
        allowed={"duration_minutes","earliest_start","latest_start","latest_end","fixed_start","priority","mandatory"}
        for k,v in updates.items():
            if k not in allowed: raise HTTPException(422,f"Unsupported update field: {k}")
            found[k]=v.isoformat() if isinstance(v,datetime) else v
    r=make_plan_request(db,s,existing,[],req.constraints,req.allow_reordering_flexible_stops,req.max_reordered_stops)
    try:
        result=plan(r,TravelProvider())
    except Exception as exc:
        raise HTTPException(502,"Travel provider failed to calculate a route") from exc
    return save_proposal(db,s,req.user_id,"replan",result)

def get_proposal(db,pid,user_id):
    p=db.get(models.Proposal,pid)
    if not p or p.user_id!=user_id: raise HTTPException(404,"Proposal not found")
    return p

def approve(db,p,req):
    prior=db.scalar(select(models.Proposal).where(models.Proposal.idempotency_key==req.idempotency_key))
    if prior:
        if prior.id!=p.id or prior.user_id!=req.user_id:
            raise HTTPException(409,"Idempotency key has already been used")
        if prior.status=="approved": return {"schedule_id":prior.schedule_id,"revision":prior.base_revision+1,"idempotent_replay":True}
    if p.status!="pending": raise HTTPException(409,f"Proposal is not pending: {p.status}")
    expires_at=p.expires_at if p.expires_at.tzinfo else p.expires_at.replace(tzinfo=timezone.utc)
    if expires_at<datetime.now(timezone.utc):
        p.status="expired"; db.commit(); raise HTTPException(410,"Proposal expired")
    s=db.scalar(select(models.Schedule).where(models.Schedule.id==p.schedule_id,models.Schedule.user_id==req.user_id).with_for_update())
    if not s: raise HTTPException(404,"Schedule not found")
    if s.current_revision!=p.base_revision:
        p.status="stale"; db.commit(); raise HTTPException(409,"Schedule changed; generate a new proposal")
    try:
        latest=db.scalar(select(models.Proposal).where(models.Proposal.id==p.id).with_for_update())
        if not latest or latest.status!="pending": raise HTTPException(409,"Proposal is no longer pending")
        from app.planner import plan, TravelProvider
        constraints=db.scalars(select(models.ScheduleConstraint).where(models.ScheduleConstraint.schedule_id==s.id)).all()
        current_rows=db.scalars(select(models.Stop).where(models.Stop.schedule_id==s.id).order_by(models.Stop.order_index)).all()
        existing=[row_stop(x) for x in current_rows]
        proposed=p.proposed_stops
        # Revalidate against current persisted constraints and travel estimates immediately before commit.
        validation=plan({"start_at":s.start_at,"end_at":s.end_at,"start_location":s.start_location,"end_location":s.end_location,"existing_stops":existing,"candidate_stops":[],"constraints":[{"type":c.type,"hardness":c.hardness,"parameters":c.parameters or {}} for c in constraints]},TravelProvider())
        if not validation["feasible"]: raise HTTPException(409,"Current schedule is no longer feasible")
        proposed_validation=plan({"start_at":s.start_at,"end_at":s.end_at,"start_location":s.start_location,"end_location":s.end_location,"existing_stops":proposed,"candidate_stops":[],"constraints":[{"type":c.type,"hardness":c.hardness,"parameters":c.parameters or {}} for c in constraints]},TravelProvider())
        if not proposed_validation["feasible"]: raise HTTPException(409,"Proposed schedule failed validation")
        p.idempotency_key=req.idempotency_key
        s.current_revision=p.base_revision+1
        changed=db.execute(update(models.Schedule).where(models.Schedule.id==s.id,models.Schedule.current_revision==p.base_revision).values(current_revision=p.base_revision+1))
        if changed.rowcount != 1:
            p.status="stale"
            raise HTTPException(409,"Schedule changed; generate a new proposal")
        db.query(models.Stop).filter(models.Stop.schedule_id==s.id).delete(synchronize_session=False)
        for i,x in enumerate(p.proposed_stops):
            db.add(models.Stop(id=x["id"],schedule_id=s.id,order_index=i,title=x["title"],type=x["type"],location=x["location"],duration_minutes=x["duration_minutes"],earliest_start=datetime.fromisoformat(x["earliest_start"]) if x.get("earliest_start") else None,latest_start=datetime.fromisoformat(x["latest_start"]) if x.get("latest_start") else None,latest_end=datetime.fromisoformat(x["latest_end"]) if x.get("latest_end") else None,fixed_start=datetime.fromisoformat(x["fixed_start"]) if x.get("fixed_start") else None,opening_hours=x.get("opening_hours"),priority=x.get("priority",3),mandatory=x.get("mandatory",False),status=x.get("status","planned"),source=x.get("source","user"),attributes=x.get("attributes",{})))
        db.flush()
        db.add(models.PlanRevision(id=uid(),schedule_id=s.id,revision_number=s.current_revision,snapshot=snapshot(db,s),reason=f"Approved proposal {p.id}"))
        p.status="approved"; db.commit()
        return {"schedule_id":s.id,"revision":s.current_revision,"idempotent_replay":False}
    except Exception:
        db.rollback(); raise

def reject(db,p,reason):
    if p.status!="pending": raise HTTPException(409,"Only pending proposals can be rejected")
    p.status="rejected"
    if reason: p.explanation_facts=(p.explanation_facts or [])+[f"Rejected: {reason}"]
    db.commit()
    return {"proposal_id":p.id,"status":p.status}
