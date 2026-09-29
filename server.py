import os
import sqlite3
import datetime
import requests
import uvicorn
from fastapi import FastAPI, Request, Query, Response
from google import genai
from google.genai import types
from pyngrok import ngrok
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI()

# --- Configuración y Credenciales ---
META_TOKEN = "EAAPlKXzyKx0BSt68bIwJDwTv6MdLUtuMPoHmwUqDTfl5LdQ8tUnwOmR8R7zZCitEx4ZCPss4LIXhRlycsOrqyeSt3KyyyNdr6eZBNr29tYxj4QmMO6D3ScC0oSXYFtYfE1JSEsOnZCPfwPgsShzA8pDC7CeGElyVjMKlvGAB9XjVhAy3ZA9y3ZB5Ehdo1PZBtBSDwZDZD"
PHONE_NUMBER_ID = "1261888910352307"
GEMINI_API_KEY = "AQ.Ab8RN6JkMOaSBbVyj-QCqCd_mTFRiDPDvE6OGw3B8ITzJuwSlw"
VERIFY_TOKEN = "english_tutor_secret_2026"
MY_PHONE = "541123588856"

ai_client = genai.Client(api_key=GEMINI_API_KEY)

# --- Capa de Persistencia (SQLite) ---
def init_db():
    conn = sqlite3.connect("tutor_memory.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day_name TEXT,
                    expression TEXT,
                    tech_word TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )''')
    conn.commit()
    conn.close()

init_db()

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
    # 1. Obtener URL del archivo binario
    url = f"https://graph.facebook.com/v22.0/{media_id}"
    headers = {"Authorization": f"Bearer {META_TOKEN}"}
    res = requests.get(url, headers=headers)
    download_url = res.json().get("url")

    # 2. Descargar bytes del stream de audio
    audio_res = requests.get(download_url, headers=headers)
    return audio_res.content

# --- Lógica Pedagógica y Generación de Retos ---
def prompt_morning_checkin():
    set_state("waiting_start")
    msg = "¡Buen día! ☀️ Nuevo día para entrenar el inglés técnico.\n\n¿Arrancamos con la lección de hoy? Respondeme con un texto o una nota de voz corta y largamos."
    save_message("tutor", msg)
    send_whatsapp(MY_PHONE, msg)

def deliver_daily_lesson():
    prompt = """
Generá la lección técnica de hoy para un estudiante argentino de ingeniería informática (transición A2 -> B1).
Estructura obligatoria:

1. *EXPRESIÓN NATIVA / COLLOQUIAL:*
   - Idiom o frase coloquial usada en equipos globales. Significado en español y un ejemplo en inglés.

2. *TÉRMINO IT:*
   - Palabra técnica clave (ej: throughput, race condition, deployment, throttling). Significado en español y un ejemplo técnico.

3. *TU MISIÓN:*
   - Pedile que escriba o envíe un audio de 1-2 oraciones en inglés usándolas en un contexto laboral.

Sé conciso, directo y usá negritas (*texto*).
"""
    res = ai_client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
    save_message("tutor", res.text)
    set_state("lesson_active")
    send_whatsapp(MY_PHONE, res.text)

def send_saturday_scenario():
    set_state("lesson_active")
    prompt = """
Planteá un reto situacional de sábado para un futuro ingeniero informático (nivel A2 -> B1).
- Contexto: Incidente en producción o daily meeting.
- Misión: Pedile que responda cómo comunicaría el status a su líder técnico. Formato breve.
"""
    res = ai_client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
    msg = f"🧩 *SITUACIÓN DE SÁBADO: CASO IT*\n\n{res.text}"
    save_message("tutor", msg)
    send_whatsapp(MY_PHONE, msg)

def send_sunday_review():
    set_state("lesson_active")
    prompt = "Es domingo de repaso. Enviá un mensaje corto animándolo a armar un resumen de 2 oraciones integrando conceptos aprendidos durante la semana."
    res = ai_client.models.generate_content(model="gemini-3.5-flash-lite", contents=prompt)
    msg = f"📚 *REPASO SEMANAL DE DOMINGO*\n\n{res.text}"
    save_message("tutor", msg)
    send_whatsapp(MY_PHONE, msg)

# --- Scheduler ---
scheduler = BackgroundScheduler(timezone="America/Argentina/Buenos_Aires")
scheduler.add_job(prompt_morning_checkin, "cron", hour=9, minute=0, day_of_week="mon-fri")
scheduler.add_job(send_saturday_scenario, "cron", hour=10, minute=0, day_of_week="sat")
scheduler.add_job(send_sunday_review, "cron", hour=11, minute=0, day_of_week="sun")
scheduler.start()

# --- Endpoints FastAPI ---
@app.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        print("\n✅ Webhook validado correctamente por Meta!")
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(content="Error en token de verificación", status_code=403)

@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})

        if "messages" not in value:
            return {"status": "ignored"}

        message = value["messages"][0]
        raw_phone = message.get("from", "")

        if raw_phone == "16315551181" or not raw_phone.startswith("54"):
            recipient_phone = MY_PHONE
        elif raw_phone.startswith("54911"):
            recipient_phone = "5411" + raw_phone[5:]
        else:
            recipient_phone = raw_phone

        user_content = ""
        is_audio = False

        # Procesamiento de Texto
        if message.get("type") == "text":
            user_content = message["text"]["body"].strip()
            print(f"\n📩 Texto recibido: '{user_content}'")

        # Procesamiento de Audio / Notas de Voz
        elif message.get("type") == "audio":
            is_audio = True
            audio_id = message["audio"]["id"]
            print(f"\n🎙️ Nota de voz recibida (ID: {audio_id}). Descargando binario...")
            audio_bytes = download_whatsapp_media(audio_id)

            # Transcripción directa con Gemini multimodal
            transcribe_res = ai_client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                    "Transcribe the English audio verbatim. If words are unclear, transcribe the best phonetic match. Output ONLY the transcription, nothing else."
                ]
            )
            user_content = transcribe_res.text.strip()
            print(f"📝 Transcripción generada: '{user_content}'")

        if user_content:
            current_state = get_state()

            # Máquina de estados: Salida del check-in
            if current_state == "waiting_start":
                deliver_daily_lesson()
                return {"status": "lesson_delivered"}

            # Corrección gramatical y pedagógica exhaustiva
            history = get_recent_history(limit=4)
            prompt_eval = f"""
Sos un mentor de inglés técnico para un futuro ingeniero en informática argentino (nivel actual A2, objetivo B1).

HISTORIAL DE CONVERSACIÓN:
{history}

INPUT DEL ESTUDIANTE ({'AUDIO TRANSCRIPTO' if is_audio else 'TEXTO ESCRITO'}):
"{user_content}"

INSTRUCCIONES DE CORRECCIÓN:
1. Sin introducciones repetitivas. Si vino de un audio, aclará brevemente qué se transcribió: "🎙️ *Escuché:* \"...\""
2. *ANÁLISIS GRAMATICAL ESTRICTO:*
   - Analizá concordancia de tiempos verbales, preposiciones (ej: on/in/at en sistemas), artículos y orden de palabras.
   - Explicá la regla gramatical en español en 1-2 oraciones claras.
3. *VERSIÓN EXACTA Y VERSIÓN ÓPTIMA B1:*
   - *Corrección directa:* La frase corregida sin errores básicos.
   - *Versión Pro/Senior (B1+):* Cómo lo diría un dev nativo de forma concisa.
4. Mantené la conversación viva con una pregunta técnica corta de seguimiento en inglés.
Formato limpio con negritas (*texto*).
"""

            response_ai = ai_client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt_eval
            )
            feedback_text = response_ai.text

            save_message("student", user_content)
            save_message("tutor", feedback_text)
            send_whatsapp(recipient_phone, feedback_text)

    except Exception as e:
        print("⚠️ Error en procesamiento:", e)

    return {"status": "ok"}

# Endpoints de prueba manual
@app.get("/test/checkin")
def test_checkin():
    prompt_morning_checkin()
    return {"status": "Check-in matutino ejecutado"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # Si estamos en tu compu (local), abre ngrok para pruebas
    if not os.environ.get("RENDER"):
        try:
            from pyngrok import ngrok
            public_url = ngrok.connect(port).public_url
            print("\n" + "=" * 50)
            print(f"🚀 URL PÚBLICA LOCAL:\n{public_url}/webhook")
            print("=" * 50 + "\n")
        except Exception:
            pass
    uvicorn.run(app, host="0.0.0.0", port=port)