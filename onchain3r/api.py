"""FastAPI server."""

from __future__ import annotations

import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Onchain3r", version="0.1.0")

# In-memory report store
_reports: dict[str, dict] = {}


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


class AnalyzeRequest(BaseModel):
    address: str
    chain: str = "base"


class AnalyzeResponse(BaseModel):
    report_id: str
    status: str


async def _run_analysis(report_id: str, address: str, chain: str) -> None:
    from onchain3r.core.engine import Engine

    config = _load_config()
    engine = Engine(config)
    try:
        report = await engine.analyze(address, chain)
        _reports[report_id] = {
            "status": "completed",
            "report": report.model_dump(mode="json", exclude={"raw_data"}),
        }
    except Exception as e:
        _reports[report_id] = {"status": "failed", "error": str(e)}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, bg: BackgroundTasks) -> AnalyzeResponse:
    report_id = str(uuid.uuid4())
    _reports[report_id] = {"status": "pending"}
    bg.add_task(_run_analysis, report_id, req.address, req.chain)
    return AnalyzeResponse(report_id=report_id, status="pending")


@app.get("/report/{report_id}")
async def get_report(report_id: str) -> dict:
    if report_id not in _reports:
        raise HTTPException(404, "Report not found")
    return _reports[report_id]


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
