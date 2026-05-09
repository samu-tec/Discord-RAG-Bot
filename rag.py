from ollama import Client

from indexer import build_embedding_function, get_chroma_client, get_collection

# Timeout en segundos para llamadas a Ollama. La inferencia en CPU puede ser
# lenta, pero por encima de 5 minutos asumimos que algo va mal y abortamos
# para que el bot no quede colgado indefinidamente.
OLLAMA_TIMEOUT_SECONDS = 300


def build_ollama_client(settings: dict) -> Client:
    base_url = settings["ollama"]["base_url"]
    # Los kwargs adicionales se reenvían a httpx.Client. ``timeout`` cubre tanto
    # la conexión como la respuesta completa.
    return Client(host=base_url, timeout=OLLAMA_TIMEOUT_SECONDS)


def load_knowledge_collection(settings: dict):
    """Carga la colección de ChromaDB al arrancar el bot.

    Si la base existente tiene metadatos incompatibles (por ejemplo, porque
    se creó con otra versión del bot o quedó corrupta tras un fallo), borra
    la colección y crea una vacía. El bot arranca igualmente y el admin
    podrá reindexar con ``/sync_knowledge``.
    """
    db_dir = settings["paths"]["db_dir"]
    collection_name = settings["knowledge_base"]["collection_name"]
    embedding_function = build_embedding_function(settings)

    client = get_chroma_client(db_dir)

    try:
        return get_collection(
            client=client,
            collection_name=collection_name,
            embedding_function=embedding_function,
        )
    except Exception:
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass
        return client.create_collection(
            name=collection_name,
            embedding_function=embedding_function,
        )


def get_collection_count(collection) -> int:
    return collection.count()


def retrieve_relevant_chunks(question: str, collection, top_k: int) -> list[dict]:
    results = collection.query(
        query_texts=[question],
        n_results=top_k,
    )

    documents = results.get("documents", [[]])
    metadatas = results.get("metadatas", [[]])

    if not documents or not documents[0]:
        return []

    chunks = []

    for index, text in enumerate(documents[0]):
        metadata = {}
        if metadatas and metadatas[0] and index < len(metadatas[0]):
            metadata = metadatas[0][index] or {}

        chunks.append(
            {
                "text": text,
                "source": metadata.get("source", "unknown"),
                "chunk_index": metadata.get("chunk_index", index + 1),
            }
        )

    return chunks


def build_context(chunks: list[dict]) -> str:
    context_blocks = []

    for chunk in chunks:
        source = chunk["source"]
        chunk_index = chunk["chunk_index"]
        text = chunk["text"].strip()

        if not text:
            continue

        context_blocks.append(
            f"[Fuente: {source} | Fragmento: {chunk_index}]\n{text}"
        )

    return "\n\n---\n\n".join(context_blocks)


def generate_rag_answer(question: str, settings: dict, collection) -> dict:
    """Ejecuta el pipeline RAG completo: recupera contexto y genera respuesta.

    Devuelve un diccionario con el campo ``has_context`` que indica si se
    encontró información relevante. Si la colección está vacía, devuelve
    ``needs_sync=True`` para que el bot le pida al admin reindexar.
    """
    top_k = settings["retrieval"]["top_k"]
    chat_model = settings["ollama"]["chat_model"]
    temperature = settings["ollama"]["temperature"]
    num_thread = settings["ollama"]["num_thread"]
    num_predict = settings["ollama"]["num_predict"]
    system_prompt = settings["prompts"]["system_prompt"]

    collection_count = get_collection_count(collection)

    if collection_count == 0:
        return {
            "answer": "",
            "chunks": [],
            "context": "",
            "has_context": False,
            "needs_sync": True,
        }

    # Limitamos top_k a la cantidad real de chunks para evitar que ChromaDB
    # devuelva un error si pedimos más fragmentos de los que existen.
    chunks = retrieve_relevant_chunks(
        question=question,
        collection=collection,
        top_k=min(top_k, collection_count),
    )

    if not chunks:
        return {
            "answer": "",
            "chunks": [],
            "context": "",
            "has_context": False,
            "needs_sync": False,
        }

    context = build_context(chunks)
    ollama_client = build_ollama_client(settings)

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": f"CONTEXTO:\n{context}\n\nPREGUNTA:\n{question}",
        },
    ]

    response = ollama_client.chat(
        model=chat_model,
        messages=messages,
        options={
            "temperature": temperature,
            "num_thread": num_thread,
            "num_predict": num_predict,
        },
    )

    answer = response["message"]["content"].strip()

    return {
        "answer": answer,
        "chunks": chunks,
        "context": context,
        "has_context": True,
        "needs_sync": False,
    }
