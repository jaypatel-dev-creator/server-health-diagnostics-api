# Design Notes

Short notes on how the API is built, why, and what was checked.

## Scope

The task: one endpoint that reads CPU, memory and disk usage, classifies the status, and adds a short Gemini diagnosis, without crashing when the LLM fails.

Left out on purpose, as the task says: Docker, Redis, databases and a frontend. There is also no authentication and no automated test suite (see "How it was checked").

## How a request flows

1. `GET /api/healthreport` reaches the route in `api/routes/health_report.py`.
2. `metrics_service.collect_metrics()` reads CPU, memory and disk.
3. `metrics_service.classify_status()` turns the readings into `HEALTHY`, `WARNING` or `CRITICAL`.
4. `ai_service.get_ai_analysis()` asks Gemini for a summary and a recommendation, or returns a fallback.
5. The route builds a `HealthReport` and FastAPI returns it as JSON.

The route only coordinates. All logic lives in the two services. The settings, logging and exception code is in `core/`, and the response models are in `schemas/`.

## Decisions and why

**Async endpoint, blocking work in a thread.** The Gemini call is async, so the endpoint is `async def`. `psutil` calls block, so they run through `asyncio.to_thread`. Otherwise the CPU sampling would freeze the event loop for every other request.

**The highest metric decides the status.** If CPU, memory or disk is high, the system is under stress, even when the other two are fine. A value has to be above the limit to count: exactly 85% is still `WARNING`, and exactly 70% is still `HEALTHY`. This follows the task's ">85" and ">70".

**Thresholds are settings, and bad values stop startup.** A validator in `config.py` rejects a warning threshold that is not lower than the critical one. A wrong `.env` fails at startup instead of silently giving wrong statuses.

**Settings use pydantic-settings, not `os.getenv`.** `os.getenv` returns plain text, or `None` if the name is missing or misspelled. `pydantic-settings` keeps all settings in one `Settings` class. It turns each value into the right type (for example a number for the timeout), checks the limits, keeps every default in one place, and reads `.env` while real environment variables take priority. A bad value stops the app at startup with a clear message, instead of failing later inside a request.


**Structured output from Gemini.** The `AIAnalysis` model (summary and recommendation) is passed to Gemini as the response schema, with the JSON mime type. The reply arrives already shaped, with no text parsing. The same model validates the result, so a missing field is caught.

**Prompt design.** A short system instruction sets the role. The prompt then lists the three metrics, the status and the thresholds, names the highest metric (the one that decided the status), and asks for exactly two things: a 1 to 2 sentence summary and one recommendation. It says the status is correct, so the model explains it instead of questioning it. For `HEALTHY` it must say no action is needed.


**The API key is optional.** The app starts without a key and uses the fallback, as the task requires. The key lives only in `.env`, which is ignored by Git. `.env.example` shows the variables with no real values.

**Secrets stay out of errors.** `hide_input_in_errors=True` stops Pydantic from printing setting values, such as part of the API key, in a validation error.

**Two layers of error handling.** Our own exceptions have a base class with a status code. A catch-all handler covers anything unexpected. For 5xx errors the real reason goes to the log and the client gets a generic message.

**Logging is set up once, from the environment.** `core/logging.py` uses DEBUG level in development and INFO in production, with one format (time, level, module, message). Noisy libraries (`httpx`, `httpcore`, `google_genai`) are limited to warnings, so our own messages stay readable. Fallbacks and 5xx errors are logged with the real reason, while the client sees only a generic message.

**Startup and shutdown use FastAPI's lifespan.** On startup the app logs its environment and warns if `LLM_API_KEY` is missing, so a missing key is visible immediately instead of only showing up as fallback responses. On shutdown it logs a stop message. The app is built in a `create_app()` factory, which keeps the setup in one place.

**One endpoint only.** There is no `/health` or `/` route, because the task asks for a single endpoint. The interactive docs are shown only in development.

**Python 3.10 or newer, not 3.9.** The task says Python 3.9+. This project needs 3.10+ because the pinned FastAPI version requires it, and Python 3.9 reached end-of-life in October 2025. The code itself uses no 3.10-only syntax (such as `X | None`), so only the dependencies set the minimum.

## How it was checked

There is no automated test suite. The checks were run by hand against the running server on Windows:

| Check | Result |
|---|---|
| Real Gemini call with a valid key | AI-written summary returned |
| Wrong API key | Status 200, raw metrics, fallback text, warning in the log |
| Empty API key | Server starts with a warning, fallback returned, no API call made |
| Thresholds set to 1 and 2 | Status `CRITICAL`, recommendation about the busiest metric |
| Thresholds set to 1 and 99 | Status `WARNING` |
| Warning threshold higher than critical | Server refuses to start with a clear message |
| Default model `gemini-3.1-flash-lite` | Worked with a valid key on 21 and 22 Nov 2026 |
| Fresh clone from GitHub, install from `requirements.txt`, add key to `.env`, start the server | Real AI summary returned on 22 Nov 2026 |

Not checked: a real network outage, and any Python version other than the one used for development.

## Problem found while testing

- A config validation error printed the first characters of the API key. Fixed with `hide_input_in_errors=True`.

## Known limitations and next steps

- Every request calls Gemini. A short cache (for example 30 seconds) would cut cost and latency.
- It reports only the machine it runs on.
- No authentication or rate limiting.
- Each request takes at least 0.5 seconds because of CPU sampling.
- The default model name worked on 22 Nov 2026 but may be retired later. It can be changed with `LLM_MODEL`.
- Automated tests for the status rules and each fallback case would be the first thing to add.