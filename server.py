import os
import sqlite3
import datetime
import requests
import uvicorn
from fastapi import FastAPI, Request, Query, Response, BackgroundTasks
from google import genai
from google.genai import types
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

# --- Configuración y Variables de Entorno ---
META_TOKEN = os.environ.get("META_TOKEN", "TU_TOKEN_AQUI")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "1261888910352307")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "TU_API_KEY_AQUI")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "english_tutor_secret_2026")
MY_PHONE = "541123588856"

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# --- Base de Datos y Persistencia ---
def init_db():
    conn = sqlite3.connect("tutor_memory.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processed_messages (
                    msg_id TEXT PRIMARY KEY,
                    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

def is_message_processed(msg_id: str) -> bool:
    conn = sqlite3.connect("tutor_memory.db")
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

def set_state(value: str):
    conn = sqlite3.connect("tutor_memory.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO user_state (key, value) VALUES ('status', ?)", (value,))
    conn.commit()
    conn.close()

def get_state() -> str:
    conn = sqlite3.connect("tutor_memory.db")
    c = conn.cursor()
    c.execute("SELECT value FROM user_state WHERE key = 'status'")
    row = c.fetchone()
    conn.close()
    return row[0] if row else "idle"

def save_message(role: str, content: str):
    conn = sqlite3.connect("tutor_memory.db")
    c = conn.cursor()
    c.execute("INSERT INTO messages (role, content) VALUES (?, ?)", (role, content))
    conn.commit()
    conn.close()

def get_recent_history(limit: int = 4):
    conn = sqlite3.connect("tutor_memory.db")
    c = conn.cursor()
    c.execute("SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    rows.reverse()
    return "\n".join([f"{role.upper()}: {text}" for role, text in rows])

# --- Integración con Meta API ---
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
    print(f"📤 Meta API Send ({res.status_code}): {res.text}")
    return res

def download_whatsapp_media(media_id: str) -> bytes:
    url = f"https://graph.facebook.com/v22.0/{media_id}"
    headers = {"Authorization": f"Bearer {META_TOKEN}"}
    res = requests.get(url, headers=headers)
    download_url = res.json().get("url")
    audio_res = requests.get(download_url, headers=headers)
    return audio_res.content

# --- Lógica de Lecciones y Tareas ---
def prompt_morning_checkin():
    set_state("waiting_start")
    msg = "¡Buen día! ☀️ Hora de afilar el inglés técnico.\n\n¿Arrancamos con la lección de hoy? Respondeme con un texto o un audio corto y largamos."
    save_message("tutor", msg)
    send_whatsapp(MY_PHONE, msg)

def deliver_daily_lesson():
    prompt = """
Sos un Senior Software Engineer y tutor técnico de inglés para un estudiante universitario de Ingeniería en Informática (transición A2 -> B1).
Generá la lección de hoy con este formato estricto:

📌 *EXPRESIÓN NATIVA / COLLOQUIAL (IT):*
- Frase usada comúnmente en startups o equipos globales (ej: "touch base", "heads up", "on the same page"). Significado en español y un ejemplo.

💻 *TÉRMINO TÉCNICO DEV:*
- Concepto clave (ej: payload, race condition, bottleneck, debounce, middleware). Significado técnico conciso y un ejemplo de uso.

🎯 *TU RETO DE HOY:*
- Pedile que escriba o mande un audio de 1-2 oraciones combinando ambos términos o respondiendo a una situación donde los aplicaría.

Sé directo y claro.
"""
    res = ai_client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
    save_message("tutor", res.text)
    set_state("lesson_active")
    send_whatsapp(MY_PHONE, res.text)

# --- Scheduler de Fondo ---
scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")
scheduler.add_job(prompt_morning_checkin, "cron", hour=9, minute=0, day_of_week="mon-fri")
scheduler.start()

# --- Endpoints FastAPI ---
@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(content="Error en token de verificación", status_code=403)

# Función ejecutada en segundo plano para no demorar la respuesta HTTP 200 a Meta
def process_incoming_message(recipient_phone: str, user_content: str, is_audio: bool):
    current_state = get_state()
    cleaned_lower = user_content.lower().strip().replace(".", "").replace("!", "")

    # 1. Si es solo un saludo aislado
    common_greetings = ["hello", "hi", "hey", "good morning", "good afternoon", "hola"]
    if cleaned_lower in common_greetings:
        reply = (
            "Hi there! 👋 Glad to see you here.\n\n"
            "¿Querés que arranquemos con la práctica técnica de hoy? Respondeme *'start'* o *'ready'* y te paso el reto."
        )
        set_state("waiting_start")
        save_message("student", user_content)
        save_message("tutor", reply)
        send_whatsapp(recipient_phone, reply)
        return

    # 2. Si estaba esperando arrancar y confirma
    if current_state == "waiting_start" or cleaned_lower in ["start", "ready", "dale", "si", "yes"]:
        deliver_daily_lesson()
        return

    # 3. Flujo principal: Evaluación técnica y pedagógica B1
    history = get_recent_history(limit=4)
    source_label = "NOTA DE VOZ (AUDIO TRANSCRIPTO)" if is_audio else "TEXTO ESCRITO"

    prompt_eval = f"""
Sos un Senior Dev y mentor bilingüe de inglés para un estudiante de Ingeniería Informática argentino (A2 alto apuntando a B1 operativo).

CONTEXTO RECIENTE:
{history}

MENSAJE DEL ESTUDIANTE [{source_label}]:
"{user_content}"

INSTRUCCIONES DE RESPUESTA:
- Cero saludos genéricos ni introducciones vacías.
- Si fue audio, iniciá con: 🎙️ *Lo que escuché:* "{user_content}"
- Tu respuesta DEBE tener estrictamente estos 4 apartados separados:

1. 🔍 *ANÁLISIS GRAMATICAL:*
   - Analizá concordancia de tiempos verbales, pronombres sujeto y preposiciones de sistemas (in/on/at). Explicación en español clara en 1-2 oraciones.

2. ✍️️ *CORRECCIÓN DIRECTA:*
   - La misma frase corregida formalmente.

3. 🚀 *VERSIÓN PRO / SENIOR (B1/B2):*
   - Cómo lo diría un dev nativo de forma concisa y natural en Slack o en un PR review.

4. 💬 *FOLLOW-UP CHALLENGE:*
   - Una sola pregunta técnica de seguimiento EN INGLÉS para que continúe la conversación.

Formato limpio sin títulos con almohadillas (#).
"""
    response_ai = ai_client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt_eval
    )
    feedback_text = response_ai.text

    save_message("student", user_content)
    save_message("tutor", feedback_text)
    send_whatsapp(recipient_phone, feedback_text)

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

        # Deduplicación: Si Meta reenvía el mismo mensaje, lo descartamos
        if is_message_processed(msg_id):
            print(f"⚠️ Mensaje duplicado {msg_id} ignorado.")
            return {"status": "duplicate"}

        raw_phone = message.get("from", "")
        if raw_phone.startswith("54911"):
            recipient_phone = "5411" + raw_phone[5:]
        elif not raw_phone.startswith("54"):
            recipient_phone = MY_PHONE
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
                model="gemini-3.5-flash-lite",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                    "Transcribe the English speech verbatim. Output ONLY the transcription."
                ]
            )
            user_content = transcribe_res.text.strip()

        if user_content:
            # Enviamos el procesamiento a segundo plano y respondemos 200 OK inmediatamente a Meta
            background_tasks.add_task(process_incoming_message, recipient_phone, user_content, is_audio)

    except Exception as e:
        print("⚠️ Error en webhook:", e)

    # Respuesta inmediata a Meta para evitar reintentos automáticos
    return {"status": "ok"}

@app.get("/test/checkin")
def test_checkin():
    prompt_morning_checkin()
    return {"status": "Check-in matutino ejecutado"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)