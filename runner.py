import time
import requests
from google import genai

# --- Credenciales ---
META_TOKEN = "EAAPlKXzyKx0BSo8KYsjggnLB6JKgxirCnhOoVcp54w5zEXi7xnwCYqGXoaPkDSyXMRakZAJAHWZBUiusbQgzlUK9We02ejW92CJevY4WWH3oM3jmfcuadsIFH7MoTGJM0mankjziVfcRhJMFJ0XrMZA81QjuqLveyRIhVm3OiZCKdZA58uZC2OBrzmvQEnFSDEtXOSMhiwZBNhMD0768rg0sYgIDomIziaY0VQkVw51BPs9beVSzJyf0MHjwhQlAxrtHorDpxE59YthxrVKJYe3eAt7keABq5CIesl2LT0ZD"
PHONE_NUMBER_ID = "1261888910352307"
GEMINI_API_KEY = "AQ.Ab8RN6JkMOaSBbVyj-QCqCd_mTFRiDPDvE6OGw3B8ITzJuwSlw"

ai_client = genai.Client(api_key=GEMINI_API_KEY)

def responder_a_mensaje(user_phone: str, user_text: str):
    print(f"\n📩 Procesando mensaje de {user_phone}: '{user_text}'")

    # Normalización del prefijo para Argentina
    if user_phone.startswith("54911"):
        recipient_phone = "5411" + user_phone[5:]
    else:
        recipient_phone = user_phone

    prompt_feedback = f"""
Sos un tutor de inglés bilingüe enfocado en ayudar a un estudiante argentino de nivel A2 a alcanzar el nivel B1 en ingeniería informática.
El estudiante envió este mensaje como respuesta al reto de práctica diaria:
"{user_text}"

Tu tarea:
1. Explicá brevemente en español si la frase es clara y si utilizó bien los términos técnicos o cotidianos.
2. Si cometió errores gramaticales o de vocabulario, dale la corrección exacta en inglés y explicale el porqué en español.
3. Si la frase está perfecta, proponé una alternativa más natural o profesional (nivel B1) para seguir sumando vocabulario.
4. Mantené un tono cercano, motivador, con emojis y formato de negrita de WhatsApp (*texto*).
"""

    print("🤖 Consultando a Gemini 3.5 Lite...")
    response_ai = ai_client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt_feedback
    )
    feedback_text = response_ai.text

    # Envío de vuelta a WhatsApp
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_phone,
        "type": "text",
        "text": {"preview_url": False, "body": feedback_text}
    }
    
    res = requests.post(url, headers=headers, json=payload)
    if res.status_code == 200:
        print("✅ ¡Respuesta pedagógica enviada a WhatsApp con éxito!")
    else:
        print(f"⚠️ Error de Meta ({res.status_code}): {res.text}")

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 TUTOR DE INGLÉS B1 (Modo Directo)")
    print("=" * 50)
    
    # Para procesar cualquier mensaje enviado:
    # Podés ingresar el texto manualmente o dejar que corra la prueba
    while True:
        texto = input("\n✍️ Ingresá el mensaje del alumno (o 'salir'): ")
        if texto.lower() == "salir":
            break
        responder_a_mensaje("541123588856", texto)