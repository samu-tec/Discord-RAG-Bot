from ollama import Client

from indexer import build_embedding_function, get_chroma_client, get_collection


def build_ollama_client(settings: dict) -> Client:
    base_url = settings["ollama"]["base_url"]
    return Client(host=base_url)


def load_knowledge_collection(settings: dict):
    db_dir = settings["paths"]["db_dir"]
    collection_name = settings["knowledge_base"]["collection_name"]
    embedding_function = build_embedding_function(settings)

    client = get_chroma_client(db_dir)
    return get_collection(
        client=client,
        collection_name=collection_name,
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
