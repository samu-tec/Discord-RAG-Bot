def normalize_query(text: str) -> str:
    return " ".join(text.lower().strip().split())


def split_hard(text: str, limit: int) -> list[str]:
    return [text[index:index + limit] for index in range(0, len(text), limit)]


def split_message(text: str, limit: int = 1900) -> list[str]:
    if limit < 1:
        raise ValueError("El límite de caracteres debe ser mayor que 0.")

    if len(text) <= limit:
        return [text]

    parts = []
    current_part = ""

    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        candidate = f"{current_part}\n\n{paragraph}".strip() if current_part else paragraph

        if len(candidate) <= limit:
            current_part = candidate
            continue

        if current_part:
            parts.append(current_part)
            current_part = ""

        if len(paragraph) <= limit:
            current_part = paragraph
            continue

        lines = paragraph.split("\n")
        temp_part = ""

        for line in lines:
            line = line.rstrip()
            candidate = f"{temp_part}\n{line}".strip() if temp_part else line

            if len(candidate) <= limit:
                temp_part = candidate
                continue

            if temp_part:
                parts.append(temp_part)
                temp_part = ""

            if len(line) <= limit:
                temp_part = line
                continue

            words = line.split(" ")
            word_part = ""

            for word in words:
                candidate = f"{word_part} {word}".strip() if word_part else word

                if len(candidate) <= limit:
                    word_part = candidate
                    continue

                if word_part:
                    parts.append(word_part)
                    word_part = ""

                if len(word) <= limit:
                    word_part = word
                else:
                    parts.extend(split_hard(word, limit))

            if word_part:
                temp_part = word_part

        if temp_part:
            current_part = temp_part

    if current_part:
        parts.append(current_part)

    return parts
