"""
OutboundCallManager – production-ready wrapper around LiveKit AgentDispatch + SIP
Author: Namish / ChatGPT
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from livekit import api
from livekit.protocol.sip import SIPParticipantInfo
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()  # load env in local/dev

_log = logging.getLogger("outbound")

# -- helpers ------------------------------------------------------------------


def _e(var: str) -> str:
    val = os.getenv(var)
    if not val:
        raise EnvironmentError(f"{var} env var is required")
    return val


PHONE_RE = re.compile(r"^\+\d{7,15}$")  # E.164


# -- manager -------------------------------------------------------------------


class OutboundCallManager:
    """Singleton managing LiveKit outbound survey & simple calls."""

    _lk_api: Optional[api.LiveKitAPI] = None

    def __init__(
        self,
        *,
        sip_trunk_id: str | None = None,
        krisp_enabled: bool | None = None,
        livekit_url: str | None = None,
        livekit_api_key: str | None = None,
        livekit_api_secret: str | None = None,
    ) -> None:
        # env fall-backs
        self.sip_trunk_id = sip_trunk_id or _e("SIP_TRUNK_ID")
        self.krisp_enabled = (
            krisp_enabled
            if krisp_enabled is not None
            else os.getenv("KRISP_ENABLED", "true").lower() == "true"
        )

        # singleton API client
        if OutboundCallManager._lk_api is None:
            OutboundCallManager._lk_api = api.LiveKitAPI(
                url=livekit_url,
                api_key=livekit_api_key,
                api_secret=livekit_api_secret,
            )
        self.livekit_api: api.LiveKitAPI = OutboundCallManager._lk_api

    # --------------------------------------------------------------------- utils
    async def _wait_for_agent(
        self, room: str, agent_name: str, timeout: float = 3.0
    ) -> None:  # noqa: D401
        """Wait until the agent joins the room or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            participants = await self.livekit_api.room.list_participants(room)
            if any(p.identity == agent_name for p in participants.items):
                return
            await asyncio.sleep(0.1)
        _log.warning("agent %s not detected in room %s after %.1fs", agent_name, room, timeout)

    # ---------------------------------------------------------- public API -----

    @retry(wait=wait_exponential(multiplier=0.5, min=0.5, max=4), stop=stop_after_attempt(3))
    async def _dial(
        self,
        phone_number: str,
        room_name: str,
        participant_identity: str,
        participant_name: str,
    ) -> SIPParticipantInfo:
        """Internal helper with automatic retry/back-off for SIP dial."""
        req = api.CreateSIPParticipantRequest(
            sip_trunk_id=self.sip_trunk_id,
            sip_call_to=phone_number,
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name=participant_name,
            krisp_enabled=self.krisp_enabled,
            wait_until_answered=True,
        )
        return await self.livekit_api.sip.create_sip_participant(req)

    # --------------------------------------------------------------------------

    async def create_outbound_call(
        self,
        *,
        phone_number: str,
        caller_name: str,
        agent_name: str,
        agent_metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[SIPParticipantInfo, str]:
        """Launch a outbound telephony call (Agent + customer)."""
        self._validate_phone(phone_number)

        room_name = f"outbound-{uuid.uuid4().hex}"
        timestamp = int(time.time())


        # 1) dispatch agent
        _log.info("dispatching agent=%s room=%s", agent_name, room_name)
        await self.livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata=json.dumps(agent_metadata),
            )
        )

        # await self._wait_for_agent(room_name, agent_name)

        # 2) dial customer
        participant = await self._dial(
            phone_number=phone_number,
            room_name=room_name,
            participant_identity=f"{caller_name}-caller-{timestamp}",
            participant_name=caller_name or "Caller",
        )

        _log.info("outbound call connected room=%s participant_sid=%s", room_name, participant.participant_id)
        return participant, room_name

    # --------------------------------------------------------------------------

    @staticmethod
    def _validate_phone(number: str) -> None:
        if not PHONE_RE.match(number):
            raise ValueError("phone number must be E.164 (start with '+' and digits)")

    async def close(self) -> None:
        """Close LiveKit API connection (call once on shutdown)."""
        if self.livekit_api:
            await self.livekit_api.aclose()
