from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    
    llm_api_key: str = "" #api key defaults to empty so the app still starts without it; the AI service then returns the fallback message instead of crashing.
    llm_model: str = "gemini-3.1-flash-lite"
    llm_timeout_seconds: int = Field(default=10, gt=0)  # max seconds for one LLM call
    llm_max_attempts: int = Field(default=2, ge=1)      # total tries before the fallback

    # Status thresholds, in percent
    warning_threshold: float = Field(default=70, ge=0, le=100)
    critical_threshold: float = Field(default=85, ge=0, le=100)

    # App
    app_env: str = "development"  # "development" shows /docs and debug logs

    model_config = SettingsConfigDict(
        env_file=".env",            # read values from the .env file
        env_file_encoding="utf-8",
        case_sensitive=False,       # LLM_API_KEY and llm_api_key both work
        extra="ignore",             # ignore unknown variables in .env
        hide_input_in_errors=True,  # do not print setting values (like the API key) in errors
    )

    # mode=after ==>  Runs after every field is read and range-checked, because it compares two fields.
    # If warning is not lower than critical, startup fails with a clear message instead of classify_status silently returning wrong statuses.
    @model_validator(mode="after")
    def check_thresholds(self) -> "Settings":
        if self.warning_threshold >= self.critical_threshold:
            raise ValueError("WARNING_THRESHOLD must be lower than CRITICAL_THRESHOLD")
        return self


@lru_cache()
def get_settings() -> Settings:
    # The first call builds Settings; later calls reuse the cached object.
    return Settings()