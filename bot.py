import asyncio
import logging
import sys
from collections import OrderedDict
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import load_settings
from indexer import sync_knowledge_base
from rag import generate_rag_answer, load_knowledge_collection
from utils import normalize_query, split_message

logger = logging.getLogger("discord-rag-bot")

# Límite duro impuesto por Discord para mensajes de texto en un canal.
DISCORD_MESSAGE_LIMIT = 2000

# Tope de la caché de respuestas. Evita crecimiento ilimitado de memoria
# en sesiones largas. Cuando se llena, se expulsa la entrada más antigua.
RESPONSE_CACHE_MAX_SIZE = 200


try:
    settings = load_settings()
    knowledge_collection = load_knowledge_collection(settings)
except Exception as error:
    print(f"❌ Error fatal durante la carga inicial: {error}", file=sys.stderr)
    sys.exit(1)


class BoundedLRUCache:
    """Caché LRU sencilla con tamaño máximo.

    Evita que la caché de respuestas crezca sin límite a lo largo del tiempo.
    Cuando se alcanza ``max_size`` se descarta la entrada accedida menos
    recientemente.
    """

    def __init__(self, max_size: int) -> None:
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Optional[str]:
        value = self._cache.get(key)
        if value is not None:
            self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: str) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        elif len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = value

    def clear(self) -> None:
        self._cache.clear()


response_cache = BoundedLRUCache(max_size=RESPONSE_CACHE_MAX_SIZE)

# Lock global: solo se procesa una generación a la vez. La inferencia en CPU
# es pesada y procesar varias en paralelo degrada mucho la respuesta.
processing_lock = asyncio.Lock()
waiting_requests = 0


def build_final_message(question: str, answer: str) -> str:
    return f"**Pregunta:** {question}\n\n{answer}"


async def send_split_response(
    interaction: discord.Interaction,
    content: str,
    continue_note: str = "\n\n*(Sigue abajo...)*",
) -> None:
    """Envía una respuesta dividiéndola si supera el límite de Discord.

    Si la interacción ya respondió previamente edita el mensaje original y
    encadena los siguientes trozos como ``followup``.
    """
    message_limit = min(settings["bot"]["split_message_limit"], DISCORD_MESSAGE_LIMIT)
    split_limit = max(1, message_limit - len(continue_note))

    parts = split_message(text=content, limit=split_limit)

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
    def __init__(self) -> None:
        # Solo se usan slash commands. message_content no es necesario y al
        # estar desactivado evita pedir el privileged intent en el portal.
        intents = discord.Intents.default()
        intents.message_content = False

        activity = discord.Game(name=settings["bot"]["activity_message"])

        super().__init__(
            command_prefix="!",  # Sin uso real, requerido por commands.Bot.
            intents=intents,
            activity=activity,
        )

    async def setup_hook(self) -> None:
        # Sincroniza el árbol de slash commands con Discord en cada arranque.
        # Es la práctica recomendada por discord.py: garantiza que los
        # comandos del código y los registrados en Discord están alineados.
        # La sincronización global puede tardar hasta una hora en propagarse
        # a todos los servidores la primera vez.
        await self.tree.sync()
        logger.info("Slash commands sincronizados con Discord.")


bot = AIBot()


@bot.event
async def on_ready() -> None:
    chat_model = settings["ollama"]["chat_model"]
    embedding_model = settings["ollama"]["embedding_model"]
    num_thread = settings["ollama"]["num_thread"]

    logger.info("Bot online como %s", bot.user)
    logger.info(
        "Configuración activa | chat_model=%s | embedding_model=%s | threads=%s",
        chat_model,
        embedding_model,
        num_thread,
    )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    """Manejador global para errores no controlados en slash commands.

    Cualquier excepción en una corutina decorada con ``@bot.tree.command``
    que no se capture llega aquí. Sin este handler, el usuario recibe el
    mensaje genérico de Discord ("The application did not respond") y la
    excepción se pierde en logs internos de la librería.
    """
    logger.error("Error no controlado en slash command", exc_info=error)

    error_message = (
        "❌ Ha ocurrido un error inesperado al procesar tu petición. "
        "Si el problema persiste, contacta con el administrador."
    )

    try:
        # ephemeral=True hace que solo lo vea quien ejecutó el comando, así no
        # ensuciamos el canal con errores visibles para todos.
        if interaction.response.is_done():
            await interaction.followup.send(content=error_message, ephemeral=True)
        else:
            await interaction.response.send_message(
                content=error_message,
                ephemeral=True,
            )
    except discord.HTTPException:
        logger.exception("No se pudo notificar al usuario del error.")


@bot.tree.command(name="ai", description="Haz una pregunta a la base de conocimiento.")
@app_commands.describe(pregunta="Escribe tu pregunta")
async def ai_command(interaction: discord.Interaction, pregunta: str) -> None:
    global waiting_requests

    logger.info("Petición de %s: %s", interaction.user, pregunta)

    cache_id = normalize_query(pregunta)
    cached_answer = response_cache.get(cache_id)

    if cached_answer:
        logger.info("Respuesta servida desde caché.")
        final_message = build_final_message(pregunta, cached_answer)
        await send_split_response(interaction, final_message)
        return

    # Respuesta inicial: debe enviarse en menos de 3 segundos o el token de
    # interacción se invalida (límite de Discord). Si hay otra generación en
    # curso mostramos la posición en la cola; si no, vamos directos al estado
    # de "Procesando..." para que el usuario no vea un mensaje fugaz.
    queue_position: Optional[int] = None

    if processing_lock.locked():
        waiting_requests += 1
        queue_position = waiting_requests
        await interaction.response.send_message(
            f"⏳ **En cola** (posición #{queue_position})\n"
            f"*Tu pregunta:* {pregunta}"
        )
    else:
        await interaction.response.send_message(
            f"⚙️ **Procesando:** *{pregunta}*"
        )

    async with processing_lock:
        # Si veníamos de la cola, actualizamos el mensaje para reflejar que
        # ya estamos procesando (la transición "En cola" → "Procesando" es
        # informativa porque entre ambos estados pasa tiempo real).
        if queue_position is not None:
            waiting_requests -= 1
            await interaction.edit_original_response(
                content=f"⚙️ **Procesando:** *{pregunta}*"
            )

        try:
            logger.info("Generando respuesta...")
            loop = asyncio.get_running_loop()

            # generate_rag_answer es síncrono y hace inferencia pesada en CPU.
            # Lo lanzamos en un executor para no bloquear el loop de asyncio
            # y permitir que el bot siga atendiendo otros eventos de Discord.
            result = await loop.run_in_executor(
                None,
                generate_rag_answer,
                pregunta,
                settings,
                knowledge_collection,
            )

            if not result["has_context"]:
                if result.get("needs_sync"):
                    error_text = (
                        "La base de conocimiento todavía no tiene documentos "
                        "indexados. Añade archivos `.md` o `.txt` y ejecuta "
                        "`/sync_knowledge` antes de preguntar."
                    )
                else:
                    error_text = (
                        "No he encontrado información relevante en la base de "
                        "conocimiento."
                    )

                await interaction.edit_original_response(
                    content=build_final_message(pregunta, error_text)
                )
                return

            answer = result["answer"].strip()

            if not answer:
                await interaction.edit_original_response(
                    content=build_final_message(
                        pregunta,
                        "No se ha podido generar una respuesta válida.",
                    )
                )
                return

            response_cache.set(cache_id, answer)
            await send_split_response(
                interaction,
                build_final_message(pregunta, answer),
            )

            logger.info("Respuesta entregada correctamente.")

        except Exception:
            # Detalles técnicos al log para que el admin pueda diagnosticar.
            # Al usuario le mostramos un mensaje genérico y amable.
            logger.exception("Error durante la generación de respuesta")
            await interaction.edit_original_response(
                content=build_final_message(
                    pregunta,
                    "⚠️ El servicio no está disponible en este momento. "
                    "Inténtalo de nuevo en unos minutos.",
                )
            )


@bot.tree.command(
    name="sync_knowledge",
    description="Reindexa manualmente la base de conocimiento."
)
@app_commands.default_permissions(administrator=True)
async def sync_knowledge_command(interaction: discord.Interaction) -> None:
    global knowledge_collection

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
            logger.info("Sincronizando base de conocimiento manualmente...")
            loop = asyncio.get_running_loop()

            result = await loop.run_in_executor(None, sync_knowledge_base, settings)

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

            logger.info(
                "Sincronización completada: %s archivos, %s fragmentos.",
                files_indexed,
                chunks_indexed,
            )

        except Exception as error:
            # Aquí sí queremos detalles técnicos en el mensaje porque solo
            # los admins pueden ejecutar /sync_knowledge.
            logger.exception("Error durante la sincronización")
            await interaction.edit_original_response(
                content=(
                    "❌ **Error durante la sincronización.**\n"
                    "Comprueba los logs del servidor para más detalles.\n\n"
                    f"`{error}`"
                )
            )


if __name__ == "__main__":
    # bot.run() configura el sistema de logging de discord.py automáticamente.
    # Pasando log_level=INFO también capturamos nuestros logs propios y los
    # de la librería en journalctl al correr como servicio systemd.
    try:
        bot.run(settings["discord_token"], log_level=logging.INFO)
    except Exception:
        logger.exception("Error fatal al arrancar el bot")
        sys.exit(1)
