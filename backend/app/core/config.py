# /backend/app/core/config.py
import os
import json
from typing import Dict, Any, Literal, List, Union
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "LazyProf Backend"
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    MAX_CONCURRENT_PDF_PARSES: int = 4
    ENABLE_DEBUG_DUMP: bool = os.getenv("ENABLE_DEBUG_DUMP", "False").lower() in ("true", "1", "yes")
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://lazy-prof.vercel.app"
    ]
    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            # Jeśli podano tablicę JSON: ["http://..."]
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            # Jeśli podano listę rozdzieloną przecinkami: url1,url2
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    # Modele Google Gemini
    MAP_MODEL: str = "gemini-3.1-flash-lite"  # Szybki i ultrawydajny model do etapu MAP
    REDUCE_MODEL: str = "gemini-3.5-flash"  # Zaawansowany model do głębokiej syntezy w REDUCE

    # Wybór backendu dla limitów: "in_memory" (lokalnie) lub "redis" (chmura)
    QUOTA_BACKEND: Literal["in_memory", "redis"] = "in_memory"
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- DEFINICJA LIMITÓW API (RPM, TPM, RPD) ---
    # Limity bezterminowe/darmowe pobrane z Google AI Studio
    MODEL_LIMITS: Dict[str, Dict[str, int]] = {
        "gemini-3.1-flash-lite": {
            "rpm": 15,          # Requests Per Minute
            "tpm": 250_000,     # Tokens Per Minute
            "rpd": 500,         # Requests Per Day
        },
        "gemini-2.5-flash": {
            "rpm": 5,
            "tpm": 250_000,
            "rpd": 20,
        },
        "gemini-3.5-flash": {
            "rpm": 5,
            "tpm": 250_000,
            "rpd": 20,
        }
    }

    # Configuration for Speed Modes (Fast, Medium, High)
    SPEED_MODES: Dict[str, Dict[str, Any]] = {
        "fast": {
            "model_name": "gemini-3.1-flash-lite",  # Zmień na gemini-3.1-flash-lite gdy będzie dostępny
            "context_mode": "smart_chunks",     # Wyciąganie dedykowanych fragmentów
            "thinking_level": "low",
            "service_tier": "flex",
        },
        "medium": {
            "model_name": "gemini-3.1-flash-lite",  # Zmień na gemini-3.1-flash-lite gdy będzie dostępny
            "context_mode": "smart_chunks",     # Wyciąganie dedykowanych fragmentów
            "thinking_level": "medium",
            "service_tier": "flex",
        },
        "high": {
            "model_name": "gemini-3.5-flash",  # Zmień na gemini-3.5-flash gdy będzie dostępny
            "context_mode": "full_paper",       # Pełny tekst artykułów
            "thinking_level": "high",
            "service_tier": "flex",
        }
    }

    # --- KONFIGURACJA LIMITÓW DLA ARXIV ---
    ARXIV_REQUEST_INTERVAL_SECONDS: float = 3.0  # Wymóg arXiv: 1 request / 3 sekundy
    ARXIV_USER_AGENT: str = "LazyProf/1.0 (Academic Research Assistant; contact@lazyprof.app)"
    ARXIV_TIMEOUT_SECONDS: float = 15.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
        
settings = Settings()