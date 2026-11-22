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

**CPU is sampled over 0.5 seconds.** `psutil.cpu_percent()` without an interval returns `0.0` on the first call. The half-second sample gives a real number, at the cost of that much latency per request.

**Status comes from the worst metric.** One overloaded resource is enough to call the system stressed. The comparison is strictly greater than, so exactly 85% is `WARNING` and exactly 70% is `HEALTHY`, matching the task's ">85" and ">70".

**Thresholds are settings, and bad values stop startup.** A validator in `config.py` rejects a warning threshold that is not lower than the critical one. A wrong `.env` fails at startup instead of silently giving wrong statuses.

**Disk is read from the home folder's drive.** This avoids hard-coding `C:\` or `/`, and works on both Windows and Linux.

**Structured output from Gemini.** The `AIAnalysis` model (summary and recommendation) is passed to Gemini as the response schema, with the JSON mime type. The reply arrives already shaped, with no text parsing. The same model validates the result, so a missing field is caught.

**Prompt design.** A short system instruction sets the role. The prompt then lists the three metrics, the status and the thresholds, names the highest metric (the one that decided the status), and asks for exactly two things: a 1 to 2 sentence summary and one recommendation. It says the status is correct, so the model explains it instead of questioning it. For `HEALTHY` it must say no action is needed.

**Fallback never raises.** `get_ai_analysis()` catches every failure and returns a fallback with the same JSON shape. The cases are: missing key, timeout, API error, `parsed` being `None` (for example when output is cut off), and empty fields. The fallback text says the AI is unavailable and gives generic advice for the current status. `CancelledError` is not caught, so a cancelled request still stops normally.

**Three limits on the LLM call.** The SDK timeout (10 s per request), the retry count (2 attempts), and a hard `asyncio.wait_for` limit as a backstop. The SDK retries failed calls on its own by default, so the limits are set explicitly.

**The API key is optional.** The app starts without a key and uses the fallback, as the task requires. The key lives only in `.env`, which is ignored by Git. `.env.example` shows the variables with no real values.

**Secrets stay out of errors.** `hide_input_in_errors=True` stops Pydantic from printing setting values, such as part of the API key, in a validation error.

**Two layers of error handling.** Our own exceptions have a base class with a status code. A catch-all handler covers anything unexpected. For 5xx errors the real reason goes to the log and the client gets a generic message.

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

## Problems found while testing

- With artificial thresholds, Gemini called the `CRITICAL` status "inconsistent" with the metrics. The prompt now states that the status is correct and names the metric that caused it.
- A config validation error printed the first characters of the API key. Fixed with `hide_input_in_errors=True`.

## Known limitations and next steps

- Every request calls Gemini. A short cache (for example 30 seconds) would cut cost and latency.
- It reports only the machine it runs on.
- No authentication or rate limiting.
- Each request takes at least 0.5 seconds because of CPU sampling.
- The default model name worked on 22 Nov 2026 but may be retired later. It can be changed with `LLM_MODEL`.
- Automated tests for the status rules and each fallback case would be the first thing to add.