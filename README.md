# LiveKit Outbound Call API

A lightweight micro-service that launches outbound voice calls via **LiveKit**. It:

1. Creates a new LiveKit room.
2. Dispatches a specified LiveKit **Agent** into that room.
3. Places an outbound SIP call through your LiveKit SIP trunk.
4. Bridges the callee into the room and waits until they answer.

Built with **FastAPI**, fully containerised.

---

## Quick start (Docker Compose)

```bash
# build & run in the background
docker compose up -d

# follow logs
docker compose logs -f outbound-api
```

The service will be available at <http://localhost:8000>.

Docs (Swagger UI) are served at `/docs` only when `ENVIRONMENT=local` or `staging` (default is `production`).

---

## Environment variables

Place these in a local `.env` file or pass individually with `-e` flags.

| Variable              | Required | Description                                  |
| --------------------- | -------- | -------------------------------------------- |
| `SIP_TRUNK_ID`        | ✅       | LiveKit SIP trunk ID to dial out on          |
| `LIVEKIT_URL`         | ✅       | LiveKit server URL (e.g. `https://lk.example`) |
| `LIVEKIT_API_KEY`     | ✅       | API key with permissions to create rooms, etc. |
| `LIVEKIT_API_SECRET`  | ✅       | API secret                                   |
| `KRISP_ENABLED`       | optional | `true/false` – enable Krisp noise suppression (default `true`) |
| `ENVIRONMENT`         | optional | `local`, `staging`, `production` (default)   |

---

## REST API

### `POST /calls/outbound`

Launch an outbound call.

Request body (JSON):
```json
{
  "phone_number": "+15551234567",
  "caller_name": "Support Bot",
  "agent_name": "SurveyAgent",
  "agent_metadata": {
    "campaign_id": 42,
    "lang": "en-US"
  }
}
```

Response `201 Created`:
```json
{
  "room_name": "outbound-4f2a3c…",
  "participant_sid": "PA_b8e1…"
}
```

### `GET /health`
Simple liveness probe → `{ "status": "ok" }`.

---

## Local development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ENVIRONMENT=local  # enables swagger docs
uvicorn api_service:app --reload
```

---

## Building the image manually

```bash
docker build -t livekit-outbound .
```

Then run:
```bash
docker run -p 8000:8000 --env-file .env livekit-outbound
```

---

## License
MIT 