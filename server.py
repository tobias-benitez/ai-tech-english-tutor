import os
import sqlite3
import requests
import uvicorn
from fastapi import FastAPI, Request, Query, Response, BackgroundTasks
from google import genai
from google.genai import types
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI(title="AI Technical English Tutor - Multi-Tenant")

# --- Configuración y Credenciales ---
META_TOKEN = os.environ.get("META_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "1261888910352307")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "english_tutor_secret_2026")

if not GEMINI_API_KEY:
    print("⚠️ ADVERTENCIA: La variable GEMINI_API_KEY está vacía o no existe en el entorno.")

ai_client = genai.Client(api_key=GEMINI_API_KEY or None)

# --- Capa de Persistencia y Multi-Tenancy (SQLite) ---
def get_db():
    conn = sqlite3.connect("tutor_memory.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processed_messages (
                    msg_id TEXT PRIMARY KEY,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    phone TEXT PRIMARY KEY,
                    level TEXT DEFAULT 'B1',
                    focus TEXT DEFAULT 'Fullstack / General IT',
                    state TEXT DEFAULT 'idle',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_phone TEXT,
                    role TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_phone) REFERENCES users(phone)
                )''')
    conn.commit()
    conn.close()

init_db()

def is_message_processed(msg_id: str) -> bool:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT msg_id FROM processed_messages WHERE msg_id = ?", (msg_id,))
    row = c.fetchone()
    if row:
        conn.close()
        return True
    c.execute("INSERT INTO processed_messages (msg_id) VALUES (?)", (msg_id,))
    conn.commit()
    conn.close()
    return False

def get_or_create_user(phone: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE phone = ?", (phone,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (phone, level, focus, state) VALUES (?, 'B1', 'Fullstack / General IT', 'idle')", (phone,))
        conn.commit()
        c.execute("SELECT * FROM users WHERE phone = ?", (phone,))
        user = c.fetchone()
    user_dict = dict(user)
    conn.close()
    return user_dict

def update_user(phone: str, **kwargs):
    conn = get_db()
    c = conn.cursor()
    fields = [f"{k} = ?" for k in kwargs.keys()]
    values = list(kwargs.values()) + [phone]
    c.execute(f"UPDATE users SET {', '.join(fields)} WHERE phone = ?", values)
    conn.commit()
    conn.close()

def save_message(user_phone: str, role: str, content: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO messages (user_phone, role, content) VALUES (?, ?, ?)", (user_phone, role, content))
    conn.commit()
    conn.close()

def get_recent_history(user_phone: str, limit: int = 4):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages WHERE user_phone = ? ORDER BY id DESC LIMIT ?", (user_phone, limit))
    rows = c.fetchall()
    conn.close()
    return "\n".join([f"{r['role'].upper()}: {r['content']}" for r in reversed(rows)])

# --- Cliente Meta WhatsApp API ---
def send_whatsapp(recipient: str, text: str):
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"preview_url": False, "body": text}
    }
    res = requests.post(url, headers=headers, json=payload)
    print(f"📤 Meta Send to {recipient} ({res.status_code}): {res.text}")
    return res

def download_whatsapp_media(media_id: str) -> bytes:
    url = f"https://graph.facebook.com/v22.0/{media_id}"
    headers = {"Authorization": f"Bearer {META_TOKEN}"}
    res = requests.get(url, headers=headers)
    download_url = res.json().get("url")
    audio_res = requests.get(download_url, headers=headers)
    return audio_res.content

# --- Motor Pedagógico y Generación de Contenido ---
def deliver_daily_lesson(user_phone: str, user_profile: dict):
    level = user_profile.get("level", "B1")
    focus = user_profile.get("focus", "Fullstack / General IT")

    prompt = f"""
Sos un Staff Software Engineer y mentor bilingüe especializado en inglés técnico para la industria de software.
Generá la micro-lección diaria personalizada para este estudiante:
- Nivel objetivo: {level}
- Especialidad / Foco: {focus}

APLICÁ EL MÉTODO DE INPUT COMPRENSIBLE (i+1):
- Vocabulario y estructuras gramaticales desafiantes pero alcanzables para nivel {level}.
- Contextualizado en situaciones reales de trabajo remoto (Slack, Daily Standup, PR Review, Incident Post-mortem).

FORMATO OBLIGATORIO (Usá exactamente estos 3 bloques):
📌 *IDIOM / EXPRESSION (Natural Workplace):*
- Una frase de uso diario en startups/tech (ej. "push back", "blocker", "touch base", "on the fence").
- Breve significado en español y 1 ejemplo claro.

💻 *TECHNICAL TERM ({focus}):*
- Un término o concepto técnico clave.
- Explicación breve en español y una oración en inglés mostrando cómo se usa.

🎯 *DAILY DRILL (Tu reto de hoy):*
- Una consigna directa pidiéndole al alumno que responda con 1 o 2 oraciones (escritas o en nota de voz) aplicando uno de los términos o resolviendo un mini escenario laboral.

Sé sintético, directo y profesional. Cero introducciones vacías.
"""
    res = ai_client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
    lesson_text = res.text.strip()
    save_message(user_phone, "tutor", lesson_text)
    update_user(user_phone, state="lesson_active")
    send_whatsapp(user_phone, lesson_text)

def broadcast_morning_checkin():
    """Ejecutado por Scheduler o llamado vía endpoint para todos los usuarios"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT phone, level, focus FROM users")
    users = c.fetchall()
    conn.close()

    for u in users:
        phone = u["phone"]
        update_user(phone, state="waiting_start")
        msg = (
            f"¡Buen día! ☀️ Hora de afilar tu inglés técnico.\n"
            f"Nivel actual: *{u['level']}* | Foco: *{u['focus']}*\n\n"
            f"¿Arrancamos la práctica de hoy? Respondé *start* (o mandá un audio) y te paso el reto."
        )
        save_message(phone, "tutor", msg)
        send_whatsapp(phone, msg)

# --- Scheduler de Respaldo Local ---
scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")
scheduler.add_job(broadcast_morning_checkin, "cron", hour=9, minute=0, day_of_week="mon-fri")
scheduler.start()

# --- Manejador de Comandos del Sistema ---
def handle_command(command_text: str, user: dict) -> str:
    parts = command_text.strip().split()
    cmd = parts[0].lower()
    phone = user["phone"]

    if cmd == "/help":
        return (
            "🛠️ *COMANDOS DISPONIBLES:*\n\n"
            "• */level <A1|A2|B1|B2|C1>*: Cambia tu nivel pedagógico.\n"
            "• */focus <Backend|Frontend|DevOps|Data|General>*: Cambia tu área técnica.\n"
            "• */status*: Muestra tu perfil actual.\n"
            "• */start*: Dispara la lección del día inmediatamente.\n"
            "• */help*: Muestra este menú."
        )

    if cmd == "/level":
        if len(parts) > 1 and parts[1].upper() in ["A1", "A2", "B1", "B2", "C1"]:
            new_level = parts[1].upper()
            update_user(phone, level=new_level)
            return f"✅ Nivel actualizado a *{new_level}*. Las próximas correcciones y retos se adaptarán a este estándar."
        return "⚠️ Nivel inválido. Opciones válidas: */level A1*, *A2*, *B1*, *B2*, *C1*."

    if cmd == "/focus":
        if len(parts) > 1:
            new_focus = " ".join(parts[1:])
            update_user(phone, focus=new_focus)
            return f"✅ Área técnica actualizada a: *{new_focus}*."
        return "⚠️ Por favor indicá el área. Ejemplo: */focus Backend* o */focus DevOps*."

    if cmd == "/status":
        return (
            f"📊 *TU PERFIL DE APRENDIZAJE:*\n\n"
            f"• *Teléfono:* {phone}\n"
            f"• *Nivel:* {user.get('level', 'B1')}\n"
            f"• *Foco Técnico:* {user.get('focus', 'Fullstack')}\n"
            f"• *Estado Actual:* {user.get('state', 'idle')}\n\n"
            f"Escribí */help* para ver cómo cambiar estos valores."
        )

    if cmd == "/start":
        deliver_daily_lesson(phone, user)
        return ""

    return "⚠️ Comando no reconocido. Escribí */help* para ver las opciones."

# --- Tarea en Segundo Plano para Procesar Mensajes ---
def process_incoming_message(recipient_phone: str, user_content: str, is_audio: bool):
    user = get_or_create_user(recipient_phone)

    # 1. Comandos del sistema
    if user_content.startswith("/"):
        reply = handle_command(user_content, user)
        if reply:
            send_whatsapp(recipient_phone, reply)
        return

    cleaned = user_content.lower().strip().replace(".", "").replace("!", "")

    # 2. Saludos simples
    if cleaned in ["hello", "hi", "hey", "good morning", "hola", "buen dia", "buenas"]:
        reply = (
            f"Hi there! 👋 Glad to see you.\n\n"
            f"Tu nivel configurado es *{user.get('level', 'B1')}* ({user.get('focus')}).\n"
            f"¿Listo para la lección de hoy? Respondé *'start'* o enviá una nota de voz para comenzar."
        )
        update_user(recipient_phone, state="waiting_start")
        save_message(recipient_phone, "student", user_content)
        save_message(recipient_phone, "tutor", reply)
        send_whatsapp(recipient_phone, reply)
        return

    # 3. Confirmación de inicio
    if user.get("state") == "waiting_start" or cleaned in ["start", "ready", "dale", "si", "yes", "arrancamos"]:
        deliver_daily_lesson(recipient_phone, user)
        return

    # 4. Flujo Pedagógico Principal: SLA Feedback
    history = get_recent_history(recipient_phone, limit=4)
    source_label = "NOTA DE VOZ (AUDIO TRANSCRIPTO)" if is_audio else "TEXTO ESCRITO"
    level = user.get("level", "B1")
    focus = user.get("focus", "Fullstack")

    prompt_eval = f"""
Sos un Tech Lead bilingüe y mentor experto en la enseñanza de inglés como segundo idioma (SLA) para ingenieros de software.
Perfil del estudiante:
- Nivel actual: {level}
- Foco: {focus}

HISTORIAL RECIENTE:
{history}

INPUT DEL ESTUDIANTE [{source_label}]:
"{user_content}"

DIRECTIVAS PEDAGÓGICAS ESTRICTAS:
1. No uses saludos genéricos.
2. Si fue audio, comenzá con: 🎙️ *Lo que escuché:* "{user_content}"
3. Ajustá tu evaluación al nivel {level}: no penalices detalles ultra-avanzados si el nivel es A2, pero exigí precisión y naturalidad si es B2/C1.
4. Generá exactamente esta estructura visual para WhatsApp:

1. 🔍 *ANÁLISIS GRAMATICAL & VOCABULARIO:*
   - Identificá aciertos y errores específicos (concordancia de tiempos, pronombres sujeto, preposiciones técnicas como in/on/at).
   - Explicación concisa en español (máximo 2 oraciones).

2. ✍️ *CORRECCIÓN DIRECTA:*
   - La misma frase corregida para que sea 100% válida.

3. 🚀 *VERSIÓN PRO / TECH SENIOR:*
   - Cómo lo diría un ingeniero nativo en un Standup, Slack o PR review (conciso, natural y profesional).

4. 💬 *FOLLOW-UP CHALLENGE:*
   - Una única pregunta de seguimiento en inglés conectada con la respuesta para que el estudiante siga practicando.

Mantené las negritas de WhatsApp (*texto*) y no uses títulos Markdown con almohadillas (#).
"""
    response_ai = ai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt_eval
    )
    feedback_text = response_ai.text.strip()

    save_message(recipient_phone, "student", user_content)
    save_message(recipient_phone, "tutor", feedback_text)
    send_whatsapp(recipient_phone, feedback_text)

# --- Endpoints de la Aplicación ---
@app.get("/")
def root():
    return {"status": "ok", "service": "AI Technical English Tutor"}

@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(content="Token de verificación inválido", status_code=403)

@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})

        if "messages" not in value:
            return {"status": "ignored"}

        message = value["messages"][0]
        msg_id = message.get("id")

        if is_message_processed(msg_id):
            return {"status": "duplicate"}

        raw_phone = message.get("from", "")
        if raw_phone.startswith("54911"):
            recipient_phone = "5411" + raw_phone[5:]
        else:
            recipient_phone = raw_phone

        user_content = ""
        is_audio = False

        if message.get("type") == "text":
            user_content = message["text"]["body"].strip()
        elif message.get("type") == "audio":
            is_audio = True
            audio_id = message["audio"]["id"]
            audio_bytes = download_whatsapp_media(audio_id)
            transcribe_res = ai_client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                    "Transcribe the English speech verbatim. Output ONLY the transcription."
                ]
            )
            user_content = transcribe_res.text.strip()

        if user_content:
            background_tasks.add_task(process_incoming_message, recipient_phone, user_content, is_audio)

    except Exception as e:
        print("⚠️ Error procesando webhook:", e)

    return {"status": "ok"}

@app.get("/test/checkin")
def test_checkin():
    broadcast_morning_checkin()
    return {"status": "Check-in matutino ejecutado a todos los usuarios"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

