import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
CONFIG_FILE = BASE_DIR / "config.json"


def load_settings():
    load_dotenv(ENV_FILE)

    discord_token = os.getenv("DISCORD_TOKEN")
    if not discord_token:
        raise ValueError("No se ha encontrado DISCORD_TOKEN en el archivo .env")

    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            "No se ha encontrado config.json. Copia config.example.json a config.json."
        )

    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        config = json.load(file)

    knowledge_dir = BASE_DIR / config["knowledge_base"]["knowledge_dir"]
    db_dir = BASE_DIR / config["knowledge_base"]["db_dir"]

    knowledge_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    config["discord_token"] = discord_token
    config["paths"] = {
        "base_dir": BASE_DIR,
        "knowledge_dir": knowledge_dir,
        "db_dir": db_dir,
    }

    return config