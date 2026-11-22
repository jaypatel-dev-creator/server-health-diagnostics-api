# Server Health Diagnostics API

A small FastAPI service that reads the CPU, memory and disk usage of the machine it runs on, classifies the overall health, and uses Gemini to write a short diagnosis with one recommendation. If the LLM is unavailable, the API still returns the raw metrics with a fallback message.

## Features

- Live CPU, memory and disk usage, read with `psutil`
- Overall status: `HEALTHY`, `WARNING` or `CRITICAL`, based on configurable thresholds
- A plain-English summary and one recommendation from Gemini, returned as structured JSON
- Fallback response when the API key is missing, the call times out, or the LLM fails
- One endpoint: `GET /api/healthreport`

## Tech stack

Python 3.10+, FastAPI, Uvicorn, psutil, google-genai (Gemini), pydantic-settings

## Project structure

```
server-health-diagnostics-api/
├── app/
│   ├── main.py                  # app factory, lifespan, exception handlers
│   ├── api/routes/
│   │   └── health_report.py     # GET /api/healthreport
│   ├── core/
│   │   ├── config.py            # settings loaded from .env
│   │   ├── exceptions.py        # custom exceptions and handlers
│   │   └── logging.py           # logging setup
│   ├── schemas/
│   │   └── health_report.py     # response and LLM output models
│   └── services/
│       ├── metrics_service.py   # psutil readings and status rules
│       └── ai_service.py        # Gemini call and fallback
├── .env.example
├── .gitignore
├── requirements.txt
├── DESIGN_NOTES.md
└── README.md
```

## Getting started

### Prerequisites

- Python 3.10 or newer
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

### 1. Clone and create a virtual environment

```
git clone https://github.com/jaypatel-dev-creator/server-health-diagnostics-api.git
cd server-health-diagnostics-api
python -m venv venv
```

Activate it:

- Windows (CMD): `venv\Scripts\activate`
- macOS / Linux: `source venv/bin/activate`

### 2. Install dependencies

```
pip install -r requirements.txt
```

### 3. Set the API key

Copy the example file and put your key in it:

- Windows (CMD): `copy .env.example .env`
- macOS / Linux: `cp .env.example .env`

Then open `.env` and set `LLM_API_KEY`. The `.env` file is ignored by Git, so your key is never committed.

### 4. Start the server

```
uvicorn app.main:app --reload
```

Restart the server after you change `.env`. Settings are read once at startup.

### 5. Test the endpoint

Open this URL in a browser, or use curl:

```
curl http://127.0.0.1:8000/api/healthreport
```

Interactive docs are at `http://127.0.0.1:8000/docs` (shown only when `APP_ENV=development`).

## Sample output

With Gemini available:

```json
{
  "timestamp": "2026-11-21T17:12:52Z",
  "status": "HEALTHY",
  "metrics": {
    "cpu_percent": 8.3,
    "memory_percent": 59.7,
    "disk_percent": 26.0
  },
  "ai_analysis": {
    "summary": "The system is currently in a healthy state with low CPU and disk usage, while memory utilization is at 59.7%.",
    "recommendation": "No action is needed."
  }
}
```

With the LLM unavailable (wrong or missing key, timeout, API error). The response keeps the same shape and the HTTP status stays 200:

```json
{
  "timestamp": "2026-11-21T17:17:34Z",
  "status": "HEALTHY",
  "metrics": {
    "cpu_percent": 12.4,
    "memory_percent": 59.2,
    "disk_percent": 26.0
  },
  "ai_analysis": {
    "summary": "AI analysis is currently unavailable. The system status is HEALTHY, based on the raw metrics.",
    "recommendation": "No action is needed."
  }
}
```

## Status rules

The overall status comes from the highest of the three metrics:

| Highest metric | Status |
|---|---|
| above 85% | `CRITICAL` |
| above 70% | `WARNING` |
| otherwise | `HEALTHY` |

The timestamp is in UTC. Disk usage is read from the drive that holds the user's home folder (`C:\` on most Windows machines, `/` on Linux and macOS).

## Configuration

All settings are environment variables, read from `.env`.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_API_KEY` | empty | Gemini API key. If empty, the fallback message is returned. |
| `LLM_MODEL` | `gemini-3.1-flash-lite` | Gemini model name |
| `LLM_TIMEOUT_SECONDS` | `10` | Time limit for one LLM request |
| `LLM_MAX_ATTEMPTS` | `2` | Tries before giving up and using the fallback |
| `WARNING_THRESHOLD` | `70` | Percent above which the status is `WARNING` |
| `CRITICAL_THRESHOLD` | `85` | Percent above which the status is `CRITICAL` |
| `APP_ENV` | `development` | `development` shows `/docs` and debug logs |

The server refuses to start if `WARNING_THRESHOLD` is not lower than `CRITICAL_THRESHOLD`.

## How the fallback works

The API never fails because of the LLM. If the key is missing, the request times out, Gemini returns an error, or the reply is empty or unusable, the API logs a warning and returns the raw metrics with a short message and a generic recommendation for the current status. In the worst case, a slow LLM can delay the response by about 25 seconds before the fallback is returned.

If reading the metrics themselves fails, the API returns a clean `500`:

```json
{
  "error": "InternalServerError",
  "message": "An unexpected error occurred."
}
```

Details are written to the server log, not sent to the client.

## More detail

See [DESIGN_NOTES.md](DESIGN_NOTES.md) for the design decisions, how the API was checked, and known limitations.