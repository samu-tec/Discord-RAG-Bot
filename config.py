import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Todas las rutas se resuelven respecto a la carpeta del proyecto, no al cwd
# desde donde se lance python. Así el bot funciona igual al ejecutarlo desde
# systemd, desde un IDE o desde la terminal.
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
CONFIG_FILE = BASE_DIR / "config.json"

# Estructura mínima que debe tener config.json. Si falta cualquier clave de
# este mapa, load_settings() falla en arranque con un mensaje claro indicando
# qué falta exactamente.
REQUIRED_KEYS = {
    "bot": ("activity_message", "split_message_limit"),
    "knowledge_base": ("knowledge_dir", "db_dir", "collection_name"),
    "retrieval": ("top_k",),
    "indexing": ("chunk_size", "chunk_overlap"),
    "ollama": (
        "base_url",
        "chat_model",
        "embedding_model",
        "temperature",
        "num_thread",
        "num_predict",
    ),
    "prompts": ("system_prompt",),
}


def validate_required_keys(config: dict[str, Any]) -> None:
    missing = []

    for section, keys in REQUIRED_KEYS.items():
        if section not in config or not isinstance(config[section], dict):
            missing.append(section)
            continue

        for key in keys:
            if key not in config[section]:
                missing.append(f"{section}.{key}")

    if missing:
        missing_keys = ", ".join(missing)
        raise ValueError(f"Faltan claves obligatorias en config.json: {missing_keys}")


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_config_values(config: dict[str, Any]) -> None:
    split_limit = config["bot"]["split_message_limit"]
    top_k = config["retrieval"]["top_k"]
    chunk_size = config["indexing"]["chunk_size"]
    chunk_overlap = config["indexing"]["chunk_overlap"]
    num_thread = config["ollama"]["num_thread"]
    num_predict = config["ollama"]["num_predict"]
    temperature = config["ollama"]["temperature"]

    required_text_values = (
        ("bot.activity_message", config["bot"]["activity_message"]),
        ("knowledge_base.collection_name", config["knowledge_base"]["collection_name"]),
        ("ollama.base_url", config["ollama"]["base_url"]),
        ("ollama.chat_model", config["ollama"]["chat_model"]),
        ("ollama.embedding_model", config["ollama"]["embedding_model"]),
        ("prompts.system_prompt", config["prompts"]["system_prompt"]),
    )

    for field_name, value in required_text_values:
        if not is_non_empty_string(value):
            raise ValueError(f"{field_name} debe ser un texto no vacío.")

    if not is_integer(split_limit) or not 1 <= split_limit <= 2000:
        raise ValueError("bot.split_message_limit debe ser un entero entre 1 y 2000.")

    if not is_integer(top_k) or top_k < 1:
        raise ValueError("retrieval.top_k debe ser un entero mayor o igual que 1.")

    if not is_integer(chunk_size) or chunk_size < 100:
        raise ValueError("indexing.chunk_size debe ser un entero mayor o igual que 100.")

    if not is_integer(chunk_overlap) or chunk_overlap < 0:
        raise ValueError("indexing.chunk_overlap debe ser un entero mayor o igual que 0.")

    if chunk_overlap >= chunk_size:
        raise ValueError("indexing.chunk_overlap debe ser menor que indexing.chunk_size.")

    if not is_integer(num_thread) or num_thread < 1:
        raise ValueError("ollama.num_thread debe ser un entero mayor o igual que 1.")

    if not is_integer(num_predict) or num_predict < 1:
        raise ValueError("ollama.num_predict debe ser un entero mayor o igual que 1.")

    if not is_number(temperature) or temperature < 0:
        raise ValueError("ollama.temperature debe ser un número mayor o igual que 0.")


def resolve_project_path(raw_path: str, field_name: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{field_name} debe ser una ruta relativa no vacía.")

    path = Path(raw_path)

    if path.is_absolute():
        raise ValueError(f"{field_name} debe ser una ruta relativa al proyecto.")

    return (BASE_DIR / path).resolve()


def load_settings():
    """Carga y valida la configuración del bot.

    Lee el token desde .env, el resto de opciones desde config.json, valida
    que toda la estructura esté correcta y resuelve las rutas relativas a
    rutas absolutas. Lanza una excepción con mensaje legible si algo falla,
    para que el error en arranque sea fácil de diagnosticar.
    """
    load_dotenv(ENV_FILE)

    discord_token = os.getenv("DISCORD_TOKEN")
    if not discord_token:
        raise ValueError("No se ha encontrado DISCORD_TOKEN en el archivo .env")

    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            "No se ha encontrado config.json. Copia config.example.json a config.json."
        )

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"config.json no contiene JSON válido: {error}") from error

    validate_required_keys(config)
    validate_config_values(config)

    knowledge_dir = resolve_project_path(
        config["knowledge_base"]["knowledge_dir"],
        "knowledge_base.knowledge_dir",
    )
    db_dir = resolve_project_path(
        config["knowledge_base"]["db_dir"],
        "knowledge_base.db_dir",
    )

    knowledge_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    config["discord_token"] = discord_token
    config["paths"] = {
        "base_dir": BASE_DIR,
        "knowledge_dir": knowledge_dir,
        "db_dir": db_dir,
    }

    return config
