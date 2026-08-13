import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "LazyProf Backend"
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    
    # Modele Google Gemini
    MAP_MODEL: str = "gemini-3.1-flash-lite"  # Szybki i ultrawydajny model do etapu MAP
    REDUCE_MODEL: str = "gemini-3.5-flash"  # Zaawansowany model do głębokiej syntezy w REDUCE

    class Config:
        env_file = ".env"

settings = Settings()