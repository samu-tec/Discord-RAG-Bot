from pathlib import Path

import chromadb
from ollama import Client as OllamaClient

# Solo se indexan archivos de texto plano. Otros formatos (PDF, docx) no están
# soportados de momento.
SUPPORTED_EXTENSIONS = {".md", ".txt"}

# Valores por defecto si el config.json no los define. Los valores reales se
# leen de settings["indexing"] al sincronizar.
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150

# Timeout amplio para generar embeddings con Ollama. En máquinas básicas (mini
# PCs antiguos, equipos sin GPU) cada embedding puede tardar varios segundos.
# Mantenemos un margen generoso para que la indexación no aborte por timeout
# aunque el equipo esté cargado en ese momento.
OLLAMA_EMBED_TIMEOUT_SECONDS = 600

# Tamaño del lote al añadir chunks a ChromaDB. Lotes pequeños hacen que la
# transacción con la base sea ligera y permiten que un fallo a mitad no eche
# por tierra todo el trabajo previo.
INDEXING_BATCH_SIZE = 16


class OllamaEmbeddingFunction:
    """Función de embeddings que usa el cliente oficial de Ollama.

    Existe como reemplazo de la implementación incluida en ChromaDB porque la
    suya tiene un timeout corto que se queda corto en máquinas modestas y
    procesa los textos en paralelo, lo que satura una CPU sin GPU. Aquí
    procesamos los textos uno a uno con un timeout amplio y respetando el
    límite de hilos configurado.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        num_thread: int | None = None,
        timeout: int = OLLAMA_EMBED_TIMEOUT_SECONDS,
    ) -> None:
        self._client = OllamaClient(host=base_url, timeout=timeout)
        self._model = model
        self._options: dict = {}
        if num_thread is not None:
            self._options["num_thread"] = num_thread

    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in input:
            response = self._client.embeddings(
                model=self._model,
                prompt=text,
                options=self._options or None,
            )
            embeddings.append(list(response["embedding"]))
        return embeddings

    def name(self) -> str:
        return "ollama_local"


def build_embedding_function(settings: dict) -> OllamaEmbeddingFunction:
    ollama_url = settings["ollama"]["base_url"]
    embedding_model = settings["ollama"]["embedding_model"]
    num_thread = settings["ollama"].get("num_thread")

    return OllamaEmbeddingFunction(
        base_url=ollama_url,
        model=embedding_model,
        num_thread=num_thread,
    )


def get_chroma_client(db_dir: Path):
    return chromadb.PersistentClient(path=str(db_dir))


def get_collection(client, collection_name: str, embedding_function=None):
    return client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_function,
    )


def recreate_collection(client, collection_name: str, embedding_function=None):
    try:
        client.delete_collection(name=collection_name)
    except Exception:
        pass

    return client.create_collection(
        name=collection_name,
        embedding_function=embedding_function,
    )


def load_source_documents(knowledge_dir: Path) -> list[dict]:
    """Lee recursivamente todos los archivos .md y .txt de la carpeta dada.

    Devuelve una lista de diccionarios con ``source``, ``relative_path`` y
    ``content``. Los archivos vacíos se omiten. Los archivos que no estén en
    UTF-8 lanzan ValueError con el nombre del archivo problemático.
    """
    documents = []

    for file_path in sorted(knowledge_dir.rglob("*")):
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        relative_path = file_path.relative_to(knowledge_dir).as_posix()

        try:
            content = file_path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError as error:
            raise ValueError(
                f"No se pudo leer {relative_path}. Guarda el archivo en UTF-8."
            ) from error

        if not content:
            continue

        documents.append(
            {
                "source": file_path,
                "relative_path": relative_path,
                "content": content,
            }
        )

    return documents


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Divide un texto en fragmentos de ``chunk_size`` caracteres con solape.

    El solape (overlap) sirve para no perder contexto entre fragmentos
    consecutivos: las últimas ``overlap`` letras de un chunk aparecen también
    al inicio del siguiente. Si el solape es mayor o igual al tamaño se
    reduce a un cuarto del tamaño para evitar bucles infinitos.
    """
    text = text.strip()
    if not text:
        return []

    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 4)

    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = max(end - overlap, start + 1)

    return chunks


def build_records(
    documents: list[dict],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
):
    ids = []
    texts = []
    metadatas = []

    for document in documents:
        chunks = chunk_text(
            text=document["content"],
            chunk_size=chunk_size,
            overlap=overlap,
        )

        for index, chunk in enumerate(chunks, start=1):
            ids.append(f'{document["relative_path"]}::chunk_{index}')
            texts.append(chunk)
            metadatas.append(
                {
                    "source": document["relative_path"],
                    "chunk_index": index,
                }
            )

    return ids, texts, metadatas


def sync_knowledge_base(settings: dict) -> dict:
    """Recrea la colección de ChromaDB con los archivos de la carpeta knowledge_base.

    Borra la colección existente y la regenera desde cero para garantizar que
    no quedan fragmentos de archivos antiguos. Devuelve un diccionario con el
    número de archivos y fragmentos indexados, además de la colección lista
    para usar.

    Esta función es síncrona y puede tardar varios minutos en máquinas básicas.
    El bot la llama desde un executor para no bloquear el loop de asyncio.
    """
    knowledge_dir = settings["paths"]["knowledge_dir"]
    db_dir = settings["paths"]["db_dir"]
    collection_name = settings["knowledge_base"]["collection_name"]

    chunk_size = settings["indexing"]["chunk_size"]
    chunk_overlap = settings["indexing"]["chunk_overlap"]

    embedding_function = build_embedding_function(settings)
    client = get_chroma_client(db_dir)
    collection = recreate_collection(
        client=client,
        collection_name=collection_name,
        embedding_function=embedding_function,
    )

    documents = load_source_documents(knowledge_dir)

    if not documents:
        return {
            "files_indexed": 0,
            "chunks_indexed": 0,
            "collection": collection,
        }

    ids, texts, metadatas = build_records(
        documents=documents,
        chunk_size=chunk_size,
        overlap=chunk_overlap,
    )

    # Procesamos en lotes pequeños: ChromaDB llama internamente a la función
    # de embeddings para cada lote y nuestra función procesa los textos uno a
    # uno. Esto evita saturar la CPU en equipos básicos y mantiene cada
    # transacción de la base ligera.
    for start in range(0, len(ids), INDEXING_BATCH_SIZE):
        end = start + INDEXING_BATCH_SIZE
        collection.add(
            ids=ids[start:end],
            documents=texts[start:end],
            metadatas=metadatas[start:end],
        )

    return {
        "files_indexed": len(documents),
        "chunks_indexed": len(ids),
        "collection": collection,
    }
