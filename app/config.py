import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


class Settings:
    DATABASE_URL: str = os.environ["DATABASE_URL"]
    APP_TITLE: str = "Wallet & Ledger Service"
    APP_VERSION: str = "1.0.0"


settings = Settings()