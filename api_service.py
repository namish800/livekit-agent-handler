from __future__ import annotations

"""FastAPI service exposing an HTTP API to launch outbound LiveKit calls.

Usage:
    uvicorn api_service:app --host 0.0.0.0 --port 8000

Following best-practices:
*  Environment config via Pydantic BaseSettings
*  Typed request/response models
*  Background tasks optional (currently awaiting call setup)
*  Docs hidden by default except on selected envs
"""

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, constr
from pydantic_settings import BaseSettings
from starlette.responses import JSONResponse
from contextlib import asynccontextmanager

from manager import OutboundCallManager, PHONE_RE

logger = logging.getLogger("api")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Application and environment configuration."""

    environment: str = Field("local", alias="ENVIRONMENT")
    sip_trunk_id: Optional[str] = Field(default=None, alias="SIP_TRUNK_ID")
    krisp_enabled: bool = Field(True, alias="KRISP_ENABLED")

    livekit_url: str = Field(None, alias="LIVEKIT_URL")
    livekit_api_key: str = Field(None, alias="LIVEKIT_API_KEY")
    livekit_api_secret: str = Field(None, alias="LIVEKIT_API_SECRET")

    show_docs_environments: set[str] = {"local", "staging"}

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False


settings = Settings()  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# Application instance
# ---------------------------------------------------------------------------

app_configs: dict[str, Any] = {
    "title": "Outbound Calls API",
    "version": "1.0.0",
}

if settings.environment not in settings.show_docs_environments:
    # Hide swagger/redoc outside allowed envs
    app_configs["openapi_url"] = None

# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Graceful startup / shutdown for FastAPI app."""
    yield  # nothing required on startup
    manager = get_call_manager()
    await manager.close()


app = FastAPI(**app_configs, lifespan=lifespan)

# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class OutboundCallRequest(BaseModel):
    phone_number: constr(pattern=PHONE_RE.pattern) = Field(  # type: ignore[valid-type]
        ...,
        description="Destination phone number in E.164 format (e.g. +15551234567)",
    )
    caller_name: str = Field(..., description="Display name for the caller in LiveKit room")
    agent_name: str = Field(..., description="Name of the LiveKit Agent to dispatch")
    agent_metadata: Optional[Dict[str, Any]] = Field(
        None, description="Arbitrary metadata JSON forwarded to the Agent dispatch"
    )


class OutboundCallResponse(BaseModel):
    room_name: str
    participant_sid: str


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


def get_call_manager() -> OutboundCallManager:
    """Singleton OutboundCallManager instance."""

    # We rely on the class-level singleton behaviour inside OutboundCallManager,
    # so instantiating on every call is cheap.
    return OutboundCallManager(
        sip_trunk_id=settings.sip_trunk_id,
        krisp_enabled=settings.krisp_enabled,
        livekit_url=settings.livekit_url,
        livekit_api_key=settings.livekit_api_key,
        livekit_api_secret=settings.livekit_api_secret,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
async def health_check():
    """Container / LB health-probe endpoint."""
    return {"status": "ok"}


@app.post(
    "/calls/outbound",
    response_model=OutboundCallResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Calls"],
    summary="Launch an outbound voice call",
    description=(
        "Creates a new LiveKit room, dispatches the specified Agent, then dials "
        "the provided phone number via SIP and bridges the call into the room. "
        "Returns when the callee answers."
    ),
)
async def launch_outbound_call(
    payload: OutboundCallRequest,
):
    """Main endpoint used by external workflow engines (e.g. n8n)."""

    manager = get_call_manager()

    try:
        participant, room_name = await manager.create_outbound_call(
            phone_number=payload.phone_number,
            caller_name=payload.caller_name,
            agent_name=payload.agent_name,
            agent_metadata=payload.agent_metadata,
        )
    except ValueError as exc:
        # Phone number validation failed or other local validation error
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to launch outbound call")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error") from exc

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=OutboundCallResponse(room_name=room_name, participant_sid=participant.participant_id).dict(),
    )


# ---------------------------------------------------------------------------
# Entry-point helper (optional)
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("api_service:app", host="0.0.0.0", port=8000, reload=True) 