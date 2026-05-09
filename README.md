# Discord RAG Bot

Bot RAG para Discord configurable, capaz de responder preguntas usando una base de conocimiento local con Ollama y ChromaDB, optimizado para hardware modesto.

El proyecto está pensado para que una persona pueda clonarlo, ajustar `.env` y `config.json`, añadir sus documentos, ejecutar `/sync_knowledge` y empezar a usar `/ai` sin tocar el código.

## Lo mínimo que tienes que cambiar

Si solo te interesa poner el bot en marcha rápido, esto es lo único que **debes** modificar después de clonar el repo:

| Archivo | Qué cambiar |
| --- | --- |
| `.env` | Pegar tu token de Discord (ver sección [Crear el bot en Discord](#crear-el-bot-en-discord)) |
| `config.json` | Copia `config.example.json` y, como mínimo, pon en `ollama.chat_model` y `ollama.embedding_model` los modelos que tengas descargados en Ollama |
| `knowledge_base/` | Añadir tus archivos `.md` o `.txt` con la información que el bot debe conocer |
| `deployment/discord-rag-bot.service` | Solo si despliegas con systemd: cambiar `TU_USUARIO` y `/ruta/completa/a/discord-rag-bot` por los valores reales |

Todo lo demás (comportamiento del bot, chunking, prompt, etc.) tiene valores por defecto razonables.

## Qué hace

El bot responde en Discord a partir de documentos locales en formato `.md` y `.txt`.

Flujo básico:

1. Un usuario pregunta con `/ai`.
2. El bot busca fragmentos relevantes en ChromaDB.
3. Envía esos fragmentos como contexto a un modelo local en Ollama.
4. Devuelve la respuesta en Discord.

No indexa documentos al arrancar. La indexación se hace manualmente con `/sync_knowledge`.

## Qué significa RAG

RAG significa **Retrieval-Augmented Generation**.

En este proyecto quiere decir que el modelo no responde solo con su conocimiento interno. Primero se recuperan fragmentos de tus documentos locales y después el modelo genera una respuesta usando ese contexto.

Esto permite cambiar el conocimiento del bot modificando archivos, sin reentrenar modelos.

## Características

* Slash command `/ai` para hacer preguntas.
* Slash command `/sync_knowledge` para reindexar manualmente.
* Base de conocimiento local en archivos `.md` y `.txt`.
* ChromaDB como base vectorial persistente.
* Ollama para chat y embeddings locales.
* Modelo de chat y modelo de embeddings configurables por separado.
* Cola simple para procesar una generación pesada a la vez.
* Estados visibles: búsqueda, procesamiento y posición en cola.
* Límite de hilos configurable con `num_thread`.
* División automática de respuestas largas para Discord.
* Caché simple para preguntas repetidas.
* Sin secretos en el código.

## Estructura

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
├─ LICENSE
├─ knowledge_base/
│  └─ .gitkeep
└─ deployment/
   └─ discord-rag-bot.service
```

## Requisitos

* Python 3.10 o superior.
* `pip` y `venv`.
* Ollama instalado y funcionando.
* Una cuenta de Discord.
* Un bot creado en el Discord Developer Portal.

El bot usa slash commands, así que no necesita activar el privileged intent de contenido de mensajes.

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/samu-tec/discord-rag-bot.git
cd discord-rag-bot
```

### 2. Crear y activar un entorno virtual

Linux o macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Instalar dependencias

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Instalar Ollama y modelos

Instala Ollama desde:

```text
https://ollama.com/download
```

Comprueba que Ollama está funcionando. En muchos sistemas queda iniciado como servicio. Si necesitas arrancarlo manualmente:

```bash
ollama serve
```

Descarga el modelo de chat y el modelo de embeddings definidos en `config.example.json`:

```bash
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text
```

Puedes cambiar ambos modelos en `config.json` sin modificar código.

## Crear el bot en Discord

### 1. Abrir el portal de desarrolladores

Entra en:

```text
https://discord.com/developers/applications
```

### 2. Crear una aplicación

Pulsa **New Application**, ponle un nombre y crea la aplicación.

### 3. Crear el usuario bot

Dentro de la aplicación, entra en **Bot** y crea el bot si todavía no existe.

### 4. Copiar el token

En la sección **Bot**, pulsa **Reset Token**, copia el token nuevo y guárdalo en `.env` del proyecto:

```env
DISCORD_TOKEN=pega-aqui-tu-token
```

Trata el token como una contraseña:

* No lo subas a GitHub (el `.gitignore` ya lo excluye, pero comprueba siempre antes de hacer push).
* No lo compartas con nadie.
* Si se filtra o sospechas que se ha expuesto, vuelve al portal y pulsa **Reset Token** otra vez. Después actualiza el `.env` y reinicia el bot.

### 5. Invitar el bot a tu servidor

En el portal de Discord, ve a **OAuth2** o **Installation** y genera una URL de invitación con estos scopes:

* `bot`
* `applications.commands`

Permisos recomendados:

* View Channels
* Send Messages
* Read Message History

Abre la URL generada e invita el bot al servidor donde quieras usarlo.

## Configuración

### 1. Crear `.env`

Linux o macOS:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edita `.env`:

```env
DISCORD_TOKEN=tu_token_real_aqui
```

### 2. Crear `config.json`

Linux o macOS:

```bash
cp config.example.json config.json
```

Windows PowerShell:

```powershell
Copy-Item config.example.json config.json
```

Configuración base (copiada de `config.example.json`):

```json
{
    "bot": {
        "activity_message": "Base de conocimiento local",
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
        "embedding_model": "nomic-embed-text",
        "temperature": 0.2,
        "num_thread": 3,
        "num_predict": 850
    },
    "prompts": {
        "system_prompt": "Eres un asistente útil, claro y preciso. Responde usando el contexto recuperado de la base de conocimiento. Si la información no aparece en el contexto, dilo claramente y no inventes datos."
    }
}
```

Si has descargado modelos diferentes en Ollama, cambia `chat_model` y `embedding_model` por los nombres exactos que aparezcan al ejecutar `ollama list`.

## Qué puedes cambiar en `config.json`

`bot`:

* `activity_message`: texto de actividad del bot en Discord.
* `split_message_limit`: límite usado para dividir respuestas largas. Debe ser menor o igual que 2000.

`knowledge_base`:

* `knowledge_dir`: carpeta con tus documentos.
* `db_dir`: carpeta donde se guarda ChromaDB.
* `collection_name`: nombre interno de la colección.

Las rutas deben ser relativas al proyecto, por ejemplo `./knowledge_base`.

`retrieval`:

* `top_k`: número de fragmentos recuperados por pregunta.

`indexing`:

* `chunk_size`: tamaño aproximado de cada fragmento.
* `chunk_overlap`: solape entre fragmentos para no perder contexto.

`ollama`:

* `base_url`: URL local de Ollama.
* `chat_model`: modelo que genera respuestas.
* `embedding_model`: modelo que convierte textos en embeddings.
* `temperature`: creatividad de la respuesta.
* `num_thread`: hilos de CPU que puede usar Ollama.
* `num_predict`: longitud máxima aproximada de respuesta.

`prompts`:

* `system_prompt`: instrucción principal del asistente.

Si cambias `embedding_model`, vuelve a ejecutar `/sync_knowledge`. Si cambias solo `chat_model` o el prompt, no necesitas reindexar.

## Añadir documentos

Guarda tus archivos en:

```text
knowledge_base/
```

Formatos soportados:

* `.md`
* `.txt`

Puedes usar subcarpetas:

```text
knowledge_base/
├─ guias/
│  ├─ instalacion.md
│  └─ mantenimiento.md
├─ normas/
│  └─ servidor.txt
└─ faq.md
```

Los archivos deben estar guardados en UTF-8.

## Arrancar el bot

Asegúrate de que Ollama está activo y ejecuta:

```bash
python bot.py
```

Al arrancar, el bot sincroniza automáticamente los slash commands con Discord y queda listo para recibir preguntas. No indexa la base de conocimiento al arrancar — eso se hace manualmente con `/sync_knowledge`.

## Uso en Discord

### 1. Indexar documentos

Un administrador debe ejecutar:

```text
/sync_knowledge
```

Este comando:

* Lee los archivos `.md` y `.txt`.
* Divide el contenido en fragmentos.
* Genera embeddings con Ollama.
* Recrea la colección de ChromaDB.
* Limpia la caché de respuestas.

### 2. Hacer preguntas

```text
/ai pregunta: ¿Qué pasos indica la guía de instalación?
```

Si el sistema está ocupado, el bot muestra que la pregunta está en cola. Cuando le toque, mostrará que está procesando.

## Hardware modesto

El proyecto está pensado para equipos pequeños o mini PC.

Recomendaciones:

* Usa modelos de chat pequeños al empezar.
* Mantén `top_k` bajo, por ejemplo `3`.
* Mantén `chunk_size` alrededor de `1000` a `1500`.
* Ajusta `num_thread` para dejar margen al sistema.
* Evita procesar varias generaciones a la vez. El bot ya usa una cola simple para esto.

## Despliegue con systemd

El repo incluye una plantilla en:

```text
deployment/discord-rag-bot.service
```

La plantilla tiene **dos placeholders** que **debes** sustituir antes de instalarla:

* `TU_USUARIO` → el nombre del usuario Linux que ejecutará el bot (ej. `samuel`)
* `/ruta/completa/a/discord-rag-bot` → la ruta absoluta donde clonaste el repo (ej. `/home/samuel/discord-rag-bot`)

Usa la ruta de sistema (`/etc/systemd/system/`), no la de usuario, para que el bot arranque automáticamente en el boot sin depender de sesión activa.

Ejemplo ya completado con usuario `samuel`:

```ini
[Unit]
Description=Discord RAG Bot
After=network-online.target ollama.service
Wants=network-online.target
Requires=ollama.service

[Service]
Type=simple
User=samuel
Group=samuel
WorkingDirectory=/home/samuel/discord-rag-bot
ExecStart=/home/samuel/discord-rag-bot/venv/bin/python /home/samuel/discord-rag-bot/bot.py
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Instalar y arrancar:

```bash
sudo cp deployment/discord-rag-bot.service /etc/systemd/system/discord-rag-bot.service
sudo systemctl daemon-reload
sudo systemctl enable discord-rag-bot
sudo systemctl start discord-rag-bot
```

Ver estado y logs:

```bash
sudo systemctl status discord-rag-bot
journalctl -u discord-rag-bot -f
```

## Actualizar el bot

Para aplicar cambios del repositorio sin tener que escribir comandos manualmente cada vez, crea un script de actualización dentro del proyecto:

```bash
nano ~/discord-rag-bot/update.sh
```

Pega el contenido siguiente (cambia `/home/samuel/discord-rag-bot` por la ruta donde tengas tu instalación):

```bash
#!/bin/bash
set -e

cd /home/samuel/discord-rag-bot

echo "Descargando cambios..."
git pull

echo "Actualizando dependencias..."
venv/bin/pip install -r requirements.txt -q

echo "Reiniciando bot..."
sudo systemctl restart discord-rag-bot

echo "Listo."
sudo systemctl status discord-rag-bot --no-pager
```

Hazlo ejecutable:

```bash
chmod +x ~/discord-rag-bot/update.sh
```

Ejecútalo cuando quieras actualizar:

```bash
~/discord-rag-bot/update.sh
```

Al reiniciar el servicio el bot vuelve a sincronizar los slash commands con Discord, así que si has añadido o cambiado comandos solo tienes que esperar (puede tardar hasta una hora en propagarse del lado de Discord la primera vez).

## Archivos que normalmente tocarás

* `.env`: token de Discord.
* `config.json`: modelos, rutas, prompt y límites.
* `knowledge_base/`: tus documentos.

Normalmente no necesitas modificar `bot.py`, `config.py`, `indexer.py`, `rag.py` ni `utils.py`.

## Solución de problemas

### El bot no arranca

Revisa:

* Que existe `.env`.
* Que `DISCORD_TOKEN` está definido.
* Que existe `config.json`.
* Que `config.json` es JSON válido.
* Que las dependencias están instaladas.

### El bot responde que no hay documentos indexados

Revisa:

* Que hay archivos `.md` o `.txt` en `knowledge_base/`.
* Que ejecutaste `/sync_knowledge`.
* Que el modelo de embeddings está descargado en Ollama.

### Falla la sincronización

Revisa:

* Que Ollama está iniciado.
* Que `embedding_model` existe localmente.
* Que los documentos están en UTF-8.
* Que `chunk_overlap` es menor que `chunk_size`.

### Los comandos no aparecen en Discord

Revisa:

* Que invitaste el bot con el scope `applications.commands`.
* Que el bot está dentro del servidor.
* Que el token pertenece al bot correcto.
* Que el bot se ha iniciado al menos una vez (la sincronización ocurre al arrancar).

## Notas de publicación

No subas a GitHub:

* `.env`
* `config.json`
* `chroma_db/`
* documentos privados

El repo está preparado para ser reutilizable con cualquier temática: documentación técnica, normas de servidores, wikis, manuales, apuntes o preguntas frecuentes.

## Licencia

MIT. Consulta el archivo `LICENSE`.
