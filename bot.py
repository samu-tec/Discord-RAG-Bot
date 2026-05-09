import asyncio
import sys

import discord
from discord import app_commands
from discord.ext import commands

from config import load_settings
from indexer import sync_knowledge_base
from rag import generate_rag_answer, load_knowledge_collection
from utils import normalize_query, split_message

try:
    settings = load_settings()
    knowledge_collection = load_knowledge_collection(settings)
except Exception as error:
    print(f"❌ Error fatal durante la carga inicial: {error}")
    sys.exit(1)

response_cache = {}
processing_lock = asyncio.Lock()
waiting_requests = 0
DISCORD_MESSAGE_LIMIT = 2000


def build_final_message(question: str, answer: str) -> str:
    return f"**Pregunta:** {question}\n\n{answer}"


async def send_split_response(
    interaction: discord.Interaction,
    content: str,
    continue_note: str = "\n\n*(Sigue abajo...)*",
) -> None:
    message_limit = min(settings["bot"]["split_message_limit"], DISCORD_MESSAGE_LIMIT)
    split_limit = max(1, message_limit - len(continue_note))

    parts = split_message(
        text=content,
        limit=split_limit,
    )

    if not parts:
        parts = ["No hay contenido para mostrar."]

    first_part = parts[0]

    if len(parts) > 1:
        first_part = f"{first_part}{continue_note}"

    if interaction.response.is_done():
        await interaction.edit_original_response(content=first_part)
    else:
        await interaction.response.send_message(content=first_part)

    for part in parts[1:]:
        await interaction.followup.send(content=part)


class AIBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False

        activity = discord.Game(name=settings["bot"]["activity_message"])

        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=activity,
        )

    async def setup_hook(self):
        await self.tree.sync()


bot = AIBot()


@bot.event
async def on_ready():
    chat_model = settings["ollama"]["chat_model"]
    embedding_model = settings["ollama"]["embedding_model"]
    num_thread = settings["ollama"]["num_thread"]

    print(f"🚀 Bot online como {bot.user}")
    print(
        f"⚙️ Configuración activa | chat_model={chat_model} | "
        f"embedding_model={embedding_model} | threads={num_thread}"
    )


@bot.tree.command(name="ai", description="Haz una pregunta a la base de conocimiento.")
@app_commands.describe(pregunta="Escribe tu pregunta")
async def ai_command(interaction: discord.Interaction, pregunta: str):
    global waiting_requests

    print(f"📥 Petición de {interaction.user}: {pregunta}")

    cache_id = normalize_query(pregunta)
    cached_answer = response_cache.get(cache_id)

    if cached_answer:
        print("⚡ Respuesta servida desde caché.")
        final_message = build_final_message(pregunta, cached_answer)
        await send_split_response(interaction, final_message)
        return

    system_busy = processing_lock.locked()
    queue_position = None

    if system_busy:
        waiting_requests += 1
        queue_position = waiting_requests
        await interaction.response.send_message(
            f"⏳ **En cola...** (Posición #{queue_position})\n"
            f"*Tu pregunta:* {pregunta}"
        )
    else:
        await interaction.response.send_message(
            f"🔍 **Buscando en la base de conocimiento para:** *{pregunta}*"
        )

    async with processing_lock:
        if queue_position is not None:
            waiting_requests -= 1

        await interaction.edit_original_response(
            content=f"⚙️ **Procesando:** *{pregunta}*"
        )

        try:
            print("🧠 Generando respuesta...")
            loop = asyncio.get_running_loop()

            result = await loop.run_in_executor(
                None,
                generate_rag_answer,
                pregunta,
                settings,
                knowledge_collection,
            )

            if not result["has_context"]:
                if result.get("needs_sync"):
                    message = (
                        f"**Pregunta:** {pregunta}\n\n"
                        "La base de conocimiento todavía no tiene documentos "
                        "indexados. Añade archivos `.md` o `.txt` y ejecuta "
                        "`/sync_knowledge` antes de preguntar."
                    )
                else:
                    message = (
                        f"**Pregunta:** {pregunta}\n\n"
                        "No he encontrado información relevante en la base de "
                        "conocimiento."
                    )

                await interaction.edit_original_response(
                    content=message
                )
                return

            answer = result["answer"].strip()

            if not answer:
                await interaction.edit_original_response(
                    content=(
                        f"**Pregunta:** {pregunta}\n\n"
                        "No se ha podido generar una respuesta válida."
                    )
                )
                return

            response_cache[cache_id] = answer

            final_message = build_final_message(pregunta, answer)
            await send_split_response(interaction, final_message)

            print("✅ Respuesta entregada correctamente.")

        except Exception as error:
            print(f"❌ Error durante la generación: {error}")
            await interaction.edit_original_response(
                content=(
                    f"**Pregunta:** {pregunta}\n\n"
                    "❌ Ha ocurrido un error técnico al generar la respuesta. "
                    "Revisa que Ollama esté iniciado, que los modelos estén "
                    "descargados y que la base de conocimiento esté sincronizada."
                )
            )


@bot.tree.command(
    name="sync_knowledge",
    description="Reindexa manualmente la base de conocimiento."
)
@app_commands.default_permissions(administrator=True)
async def sync_knowledge_command(interaction: discord.Interaction):
    global knowledge_collection, response_cache

    locked_before = processing_lock.locked()

    if locked_before:
        await interaction.response.send_message(
            "⏳ **Sistema ocupado.** Esperando para sincronizar la base de conocimiento..."
        )
    else:
        await interaction.response.send_message(
            "🔄 **Sincronizando base de conocimiento...**"
        )

    async with processing_lock:
        if locked_before:
            await interaction.edit_original_response(
                content="🔄 **Iniciando sincronización...**"
            )

        try:
            print("🔄 Sincronizando base de conocimiento manualmente...")
            loop = asyncio.get_running_loop()

            result = await loop.run_in_executor(
                None,
                sync_knowledge_base,
                settings,
            )

            knowledge_collection = result["collection"]
            response_cache.clear()

            files_indexed = result["files_indexed"]
            chunks_indexed = result["chunks_indexed"]

            if files_indexed == 0:
                message = (
                    "⚠️ **Sincronización completada sin documentos**\n"
                    "No se encontraron archivos `.md` o `.txt` en la carpeta "
                    "de conocimiento."
                )
            else:
                message = (
                    "✅ **Sincronización completada**\n"
                    f"Archivos indexados: **{files_indexed}**\n"
                    f"Fragmentos indexados: **{chunks_indexed}**"
                )

            await interaction.edit_original_response(content=message)

            print(
                f"✅ Sincronización completada: "
                f"{files_indexed} archivos, {chunks_indexed} fragmentos."
            )

        except Exception as error:
            print(f"❌ Error durante la sincronización: {error}")
            await interaction.edit_original_response(
                content=(
                    "❌ Error durante la sincronización. Revisa que Ollama esté "
                    "iniciado y que el modelo de embeddings esté descargado.\n\n"
                    f"Detalle: {error}"
                )
            )


if __name__ == "__main__":
    try:
        bot.run(settings["discord_token"])
    except Exception as error:
        print(f"❌ Error fatal al arrancar el bot: {error}")
        sys.exit(1)
