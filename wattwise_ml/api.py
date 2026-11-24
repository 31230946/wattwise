"""
WattWise ML web service (FastAPI). A thin wrapper around engine.py.

Run:   python -m uvicorn api:app --port 8000
Docs:  http://localhost:8000/docs

Endpoints
  GET  /health             {"status": "ok"}
  GET  /meta               dropdown values (home types, appliances), tariff, carbon factor
  POST /bill               monthly bill units -> bill + carbon (no ML)
  POST /forecast/daily     7-28 daily kWh -> next day / 7 days / 30 days + bill + carbon + tip
  POST /homes-like-yours   monthly bills (+ AC yes/no) -> closest SIMULATED Pune homes
"""
import os
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import engine

app = FastAPI(title="WattWise ML Service", version="3.3",
              description="Household electricity forecast (ML), MSEDCL bill, carbon footprint and tips.")

# Only matters if a browser calls this service directly. The Node server proxies every call, so it doesn't.
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
                   allow_methods=["GET", "POST"], allow_headers=["*"])

@app.exception_handler(RequestValidationError)
async def readable_422(request: Request, exc: RequestValidationError):
    """Every 422 has a plain-English `detail` string the frontend can show as-is
    (the raw list is kept in `errors` for debugging)."""
    msgs = []
    for e in exc.errors():
        field = ".".join(str(p) for p in e["loc"] if p != "body")
        msgs.append(f"{field}: {e['msg']}" if field else e["msg"])
    return JSONResponse(status_code=422, content={"detail": "; ".join(msgs), "errors": exc.errors()})


HomeType = Literal["1bhk", "2bhk", "3bhk", "villa"]


class Appliance(BaseModel):
    type: str = Field(..., description="key from GET /meta -> appliance_types, e.g. 'ac_1_5_ton'")
    count: int = Field(1, ge=1, le=20)
    hours_per_day: Optional[float] = Field(None, ge=0, le=24, description="leave empty for all_day appliances")
    when: Literal["morning", "day", "evening", "night", "all_day"] = "evening"
    rated_watts: Optional[float] = Field(None, gt=0, le=10000, description="from the appliance label, if known")
    star_rating: Optional[int] = Field(None, ge=1, le=5, description="BEE star rating 1-5 (AC, fridge, ceiling fan; see /meta -> appliance_star_types)")
    label_kwh_per_year: Optional[float] = Field(None, gt=0, le=5000, description="'kWh per year' printed on the BEE star label (AC, fridge)")


class Common(BaseModel):
    home_type: Optional[HomeType] = None
    has_smart_meter: bool = False
    peer_mean_kwh: Optional[float] = Field(None, gt=0, description="avg daily kWh of similar homes; default from training data")
    evening_share: Optional[float] = Field(None, ge=0, le=1)
    baseload_kw: Optional[float] = Field(None, ge=0, le=10)
    appliances: Optional[List[Appliance]] = None


class BillRequest(BaseModel):
    monthly_units: List[float] = Field(..., min_length=1, max_length=12, description="units from recent bills, OLDEST first")
    has_smart_meter: bool = False


class LikeYoursRequest(BaseModel):
    monthly_units: List[float] = Field(..., min_length=1, max_length=12, description="units from recent bills, OLDEST first")
    last_bill_month: Optional[int] = Field(None, ge=1, le=12, description="calendar month (1-12) of the LAST bill; default last month")
    has_ac: Optional[bool] = Field(None, description="does the home have an AC? leave empty if unknown")
    has_smart_meter: bool = False


class DailyRequest(Common):
    daily_kwh: Optional[List[float]] = Field(None, min_length=7, max_length=28, description="kWh per day, OLDEST first, last = most recent day")
    daily_meter_readings: Optional[List[float]] = Field(None, min_length=8, max_length=29, description="OR cumulative meter readings, one per day")
    last_reading_date: Optional[str] = Field(None, description="YYYY-MM-DD of the last value; default yesterday")



def _run(fn, payload):
    try:
        return fn(payload)
    except engine.InputError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/meta")
def meta():
    return engine.meta()


@app.post("/bill")
def bill(req: BillRequest):
    return _run(engine.bill_screen, req.model_dump())


@app.post("/forecast/daily")
def forecast_daily(req: DailyRequest):
    return _run(engine.forecast_daily, req.model_dump())


@app.post("/homes-like-yours")
def homes_like_yours(req: LikeYoursRequest):
    """Monthly bills -> closest SIMULATED Pune homes -> typical day + 12-month outlook (bill, carbon).
    Show `data_label` on screen."""
    return _run(engine.homes_like_yours, req.model_dump())
