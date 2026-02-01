"""FastAPI server with WebSocket analysis."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

load_dotenv()

app = FastAPI(title="Onchain3r", version="0.1.0")


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.yaml"
    if config_path.exists():
        return yaml.safe_load(config_path.read_text())
    return {}


@app.websocket("/ws/analyze")
async def ws_analyze(ws: WebSocket) -> None:
    await ws.accept()
    try:
        msg = json.loads(await ws.receive_text())
        address = msg.get("address", "")
        chain = msg.get("chain", "base")

        if not address:
            await ws.send_json({"type": "error", "message": "Missing address"})
            await ws.close()
            return

        from onchain3r.core.engine import Engine

        config = _load_config()
        engine = Engine(config)

        async def send_progress(text: str) -> None:
            await ws.send_json({"type": "progress", "message": text})

        engine.on_progress(send_progress)

        try:
            report = await engine.analyze(address, chain)
            await ws.send_json({
                "type": "result",
                "report": report.model_dump(mode="json"),
            })
        except Exception as e:
            await ws.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Serve frontend
_frontend_dir = Path(__file__).parent.parent / "frontend"
if _frontend_dir.exists():
    @app.get("/")
    async def index():
        return FileResponse(_frontend_dir / "index.html")
