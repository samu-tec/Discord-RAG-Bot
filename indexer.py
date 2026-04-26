from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions.ollama_embedding_function import (
    OllamaEmbeddingFunction,
)

SUPPORTED_EXTENSIONS = {".md", ".txt"}
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150


def build_embedding_function(settings: dict):
    ollama_url = settings["ollama"]["base_url"]
    embedding_model = settings["ollama"]["embedding_model"]

    return OllamaEmbeddingFunction(
        url=ollama_url,
        model_name=embedding_model,
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

    if ids:
        collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
        )

    return {
        "files_indexed": len(documents),
        "chunks_indexed": len(ids),
        "collection": collection,
    }
