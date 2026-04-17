# Discord RAG Bot

Bot de Discord con arquitectura RAG (Retrieval-Augmented Generation) para consultar una base de conocimiento local usando Ollama y ChromaDB.

Está pensado para funcionar bien en hardware modesto, pero también puede adaptarse a equipos más potentes ajustando la configuración.

---

## ¿Qué hace este proyecto?

Este proyecto crea un bot de Discord capaz de responder preguntas usando información propia almacenada en archivos locales.

En lugar de depender solo de lo que “sepa” el modelo, el bot:

1. Busca los fragmentos más relevantes dentro de una base de conocimiento local.
2. Usa esos fragmentos como contexto.
3. Genera una respuesta con un modelo local en Ollama.
4. Devuelve la respuesta dentro de Discord mediante slash commands.

Esto permite actualizar el conocimiento del bot sin reentrenar el modelo: solo hay que modificar los documentos y volver a indexarlos.

---

## Características principales

* Bot de Discord con slash commands
* Base de conocimiento local a partir de archivos `.md` y `.txt`
* Recuperación semántica con ChromaDB
* Respuestas generadas en local con Ollama
* Modelo de chat y modelo de embeddings configurables por separado
* Reindexación manual bajo demanda
* Cola de procesamiento para evitar saturar la CPU
* Optimizado para hardware modesto
* División automática de respuestas largas para cumplir con los límites de Discord
* Configuración externa con `.env` y `config.json`
* Sin indexación automática al arrancar
* Caché simple para preguntas repetidas

---

## ¿Qué significa RAG?

RAG significa **Retrieval-Augmented Generation**.

En este proyecto significa que el bot no responde únicamente con lo que “recuerda” el modelo, sino que primero busca información relevante dentro de tu base de conocimiento y luego responde usando ese contexto.

En la práctica, el flujo es este:

1. El usuario lanza `/ai`
2. El bot busca los fragmentos más relevantes en la base vectorial
3. Construye un contexto con esos fragmentos
4. Envía la pregunta y el contexto al modelo de chat
5. Devuelve la respuesta final

Esto encaja muy bien en un proyecto como este porque:

* puedes cambiar los documentos cuando quieras
* no necesitas reentrenar el modelo
* puedes adaptar el bot a cualquier temática
* funciona bien en local

---

## Tecnologías usadas

* **Python**: lenguaje principal del proyecto
* **discord.py**: librería para el bot de Discord y slash commands
* **Ollama**: ejecución local del modelo de lenguaje y del modelo de embeddings
* **ChromaDB**: base de datos vectorial persistente
* **systemd**: despliegue opcional como servicio en Linux

---

## Estructura del proyecto

```text
discord-rag-bot/
├─ bot.py
├─ config.py
├─ indexer.py
├─ rag.py
├─ utils.py
├─ requirements.txt
├─ .gitignore
├─ .env.example
├─ config.example.json
├─ README.md
├─ knowledge_base/
│  └─ .gitkeep
└─ deployment/
   └─ discord-rag-bot.service
```

---

## Requisitos previos

Antes de empezar, necesitas tener instalado lo siguiente:

* Python 3
* `pip`
* `venv`
* Ollama
* Una cuenta de Discord
* Un bot creado en el portal de desarrolladores de Discord

---

## Instalación paso a paso

### 1) Clonar el repositorio

```bash
git clone https://github.com/samu-tec/discord-rag-bot.git
cd discord-rag-bot
```

---

### 2) Crear y activar un entorno virtual

#### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

---

### 3) Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## Instalación de Ollama

Instala Ollama en tu sistema siguiendo la documentación oficial de Ollama.

Después, descarga los modelos que vas a usar. En la configuración actual del proyecto se separan:

* un modelo de chat para responder
* un modelo de embeddings para indexar y recuperar contexto

Ejemplo recomendado:

```bash
ollama pull qwen2.5:1.5b
ollama pull embeddinggemma
```

Más adelante puedes cambiar esos modelos en `config.json`.

---

## Configuración del proyecto

### 1) Crear el archivo `.env`

Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

Abre el archivo `.env` y escribe tu token real:

```env
DISCORD_TOKEN=tu_token_real_aqui
```

---

### 2) Crear el archivo `config.json`

Copia el archivo de ejemplo:

```bash
cp config.example.json config.json
```

Contenido base recomendado:

```json
{
  "bot": {
    "activity_message": "Local knowledge assistant",
    "split_message_limit": 1900
  },
  "knowledge_base": {
    "knowledge_dir": "./knowledge_base",
    "db_dir": "./chroma_db",
    "collection_name": "discord_rag_knowledge"
  },
  "retrieval": {
    "top_k": 3
  },
  "indexing": {
    "chunk_size": 1200,
    "chunk_overlap": 150
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "chat_model": "qwen2.5:1.5b",
    "embedding_model": "embeddinggemma",
    "temperature": 0.2,
    "num_thread": 3,
    "num_predict": 850
  },
  "prompts": {
    "system_prompt": "Eres un asistente útil, claro y preciso. Responde usando el contexto recuperado de la base de conocimiento. Si la información no aparece en el contexto, dilo claramente y no inventes datos."
  }
}
```

---

## Explicación de `config.json`

### `bot`

Opciones generales del bot.

* `activity_message`: texto que aparecerá como actividad del bot
* `split_message_limit`: límite de caracteres por bloque antes de dividir la respuesta

### `knowledge_base`

Configuración de la base de conocimiento.

* `knowledge_dir`: carpeta donde estarán tus documentos
* `db_dir`: carpeta donde se guardará ChromaDB
* `collection_name`: nombre interno de la colección vectorial

### `retrieval`

Configuración de recuperación semántica.

* `top_k`: número de fragmentos que se recuperan antes de generar la respuesta

### `indexing`

Configuración de indexación y fragmentación del contenido.

* `chunk_size`: tamaño máximo aproximado de cada fragmento
* `chunk_overlap`: solape entre fragmentos consecutivos

### `ollama`

Configuración del motor local.

* `base_url`: dirección donde corre Ollama
* `chat_model`: modelo de chat que genera la respuesta final
* `embedding_model`: modelo usado para generar embeddings
* `temperature`: nivel de creatividad
* `num_thread`: número de hilos de CPU permitidos
* `num_predict`: longitud máxima aproximada de la respuesta

### `prompts`

Comportamiento general del asistente.

* `system_prompt`: instrucción principal que guía el estilo y el comportamiento del bot

---

## Añadir documentos a la base de conocimiento

Guarda tus archivos dentro de:

```text
knowledge_base/
```

Actualmente el proyecto está preparado para leer:

* `.md`
* `.txt`

Puedes organizarlos en subcarpetas.

Ejemplo:

```text
knowledge_base/
├─ minecraft/
│  ├─ biomas.md
│  └─ mobs.md
├─ reglas/
│  └─ normas.txt
└─ faq.md
```

---

## Cómo crear el bot en Discord y conseguir el token

Esta parte es importante porque sin ella no podrás arrancar el proyecto.

### 1) Entrar en el portal de desarrolladores

Entra al **Discord Developer Portal** con tu cuenta de Discord.

### 2) Crear una nueva aplicación

* Pulsa en **New Application**
* Ponle un nombre
* Crea la aplicación

La aplicación es el contenedor principal del proyecto dentro de Discord.

### 3) Crear el bot dentro de la aplicación

Dentro de tu aplicación:

* Ve al apartado **Bot**
* Crea el bot si todavía no está creado

Ahí es donde tendrás el usuario bot real que se conectará a Discord.

### 4) Obtener el token

En la pestaña **Bot** encontrarás el token del bot.

Ese token es el que debes copiar en tu archivo `.env`:

```env
DISCORD_TOKEN=tu_token_real_aqui
```
Si regeneras el token, tendrás que actualizar también tu archivo `.env`.


### 5) Trata el token como una contraseña

Muy importante:

* no lo subas a GitHub
* no lo pegues en capturas
* no lo compartas con nadie
* si crees que se ha filtrado, regénéralo desde el portal

---

## Cómo invitar el bot a tu servidor

Después de crear el bot, tienes que invitarlo a un servidor donde tengas permisos.

### 1) Ir a la sección de instalación / OAuth2

Dentro del portal de desarrolladores, ve a la sección relacionada con **OAuth2** o la instalación de la aplicación.

### 2) Seleccionar los scopes necesarios

Asegúrate de incluir al menos estos scopes:

* `bot`
* `applications.commands`

Esto es importante porque:

* `bot` permite añadir el bot al servidor
* `applications.commands` permite usar slash commands como `/ai` y `/sync_knowledge`

### 3) Seleccionar permisos recomendados

Permisos recomendados para este proyecto:

* **View Channels**
* **Send Messages**
* **Read Message History**

Con eso suele ser suficiente para empezar.

### 4) Generar la URL e invitar el bot

Genera la URL de invitación, ábrela en el navegador y añade el bot al servidor deseado.

---

## Arranque del proyecto

### 1) Iniciar Ollama

Asegúrate de que Ollama esté funcionando en tu sistema.

### 2) Ejecutar el bot

```bash
python bot.py
```

Si todo está bien configurado, el bot arrancará y sincronizará sus slash commands.

---

## Primer uso dentro de Discord

### 1) Indexar la base de conocimiento

Antes de hacer preguntas, debes indexar tus documentos.

Usa este comando:

```text
/sync_knowledge
```

Este comando:

* borra la colección anterior
* vuelve a leer los documentos de `knowledge_base/`
* genera los embeddings
* reconstruye la base vectorial

### 2) Hacer preguntas

Después de indexar, ya puedes consultar al bot:

```text
/ai pregunta: ¿Tu pregunta aquí?
```

Ejemplo:

```text
/ai pregunta: ¿Cómo funciona un beacon?
```

---

## Comportamiento del sistema

El bot está diseñado para no saturar la máquina, especialmente en hardware modesto.

Características importantes:

* solo procesa una petición pesada a la vez
* usa una cola visible para el usuario si ya hay otra solicitud en marcha
* informa con estados intermedios
* divide mensajes largos para no superar el límite de Discord
* guarda respuestas simples en caché para repetir menos trabajo
* no indexa automáticamente al arrancar
* permite ajustar el uso de CPU desde `config.json`

---

## Despliegue permanente con systemd en Linux

El proyecto incluye un ejemplo de servicio en:

```text
deployment/discord-rag-bot.service
```

### Qué tienes que editar en ese archivo

Debes cambiar:

* `User`
* `Group`
* `WorkingDirectory`
* `ExecStart`

para que coincidan con tu usuario y con la ruta real de tu proyecto.

### Ejemplo típico

```ini
[Unit]
Description=Discord RAG Bot
After=network.target
Wants=network.target

[Service]
Type=simple
User=samuel
Group=samuel
WorkingDirectory=/home/samuel/discord-rag-bot
ExecStart=/home/samuel/discord-rag-bot/venv/bin/python /home/samuel/discord-rag-bot/bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Pasos para activarlo

#### 1) Copiar el archivo del servicio

```bash
sudo cp deployment/discord-rag-bot.service /etc/systemd/system/discord-rag-bot.service
```

#### 2) Recargar systemd

```bash
sudo systemctl daemon-reload
```

#### 3) Habilitar el servicio al arrancar

```bash
sudo systemctl enable discord-rag-bot
```

#### 4) Iniciar el servicio

```bash
sudo systemctl start discord-rag-bot
```

#### 5) Ver el estado

```bash
sudo systemctl status discord-rag-bot
```

#### 6) Reiniciarlo después de cambios

```bash
sudo systemctl restart discord-rag-bot
```

---

## Actualizar la base de conocimiento

Cada vez que:

* añadas archivos nuevos
* borres archivos
* modifiques contenido dentro de `knowledge_base/`

deberás volver a ejecutar:

```text
/sync_knowledge
```

---

## Buenas prácticas

* No subas `.env`
* No subas tu `config.json` real si contiene valores personalizados de tu máquina
* No subas `chroma_db/`
* Mantén separados el modelo de chat y el modelo de embeddings
* Ajusta `num_thread` según el hardware disponible
* Si usas un mini PC modesto, empieza con valores conservadores

---

## Solución de problemas

### El bot no arranca

Revisa:

* que `.env` exista
* que `DISCORD_TOKEN` esté bien escrito
* que `config.json` exista
* que Ollama esté funcionando
* que hayas instalado las dependencias

### El bot arranca pero no responde bien

Revisa:

* que hayas ejecutado `/sync_knowledge`
* que los documentos estén en `knowledge_base/`
* que los archivos sean `.md` o `.txt`
* que el modelo de embeddings esté descargado

### Los comandos no aparecen en Discord

Revisa:

* que hayas invitado el bot con el scope `applications.commands`
* que el bot esté realmente dentro del servidor
* que el token corresponda al bot correcto

---

## Objetivo del proyecto

Este repositorio está pensado como una base general para crear bots RAG de Discord alimentados por conocimiento local.

Se puede adaptar a muchos casos:

* Minecraft
* documentación técnica
* manuales internos
* normas de servidores
* apuntes
* preguntas frecuentes
* wikis temáticas

---

## Ideas futuras

* Soporte para PDF y DOCX
* Citas de fuentes en las respuestas
* Re-ranking de resultados
* Soporte para varias colecciones
* Interfaz web de administración
* Logs y métricas más avanzadas

---

## Licencia

Este proyecto está licenciado bajo la licencia MIT. Consulta el archivo `LICENSE` para más información.
