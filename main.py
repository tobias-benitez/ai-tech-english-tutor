import requests
from google import genai

# 1. Credenciales
META_TOKEN = "EAAPlKXzyKx0BSo8KYsjggnLB6JKgxirCnhOoVcp54w5zEXi7xnwCYqGXoaPkDSyXMRakZAJAHWZBUiusbQgzlUK9We02ejW92CJevY4WWH3oM3jmfcuadsIFH7MoTGJM0mankjziVfcRhJMFJ0XrMZA81QjuqLveyRIhVm3OiZCKdZA58uZC2OBrzmvQEnFSDEtXOSMhiwZBNhMD0768rg0sYgIDomIziaY0VQkVw51BPs9beVSzJyf0MHjwhQlAxrtHorDpxE59YthxrVKJYe3eAt7keABq5CIesl2LT0ZD"
PHONE_NUMBER_ID = "1261888910352307"
DESTINATARIO = "541123588856"
GEMINI_API_KEY = "AQ.Ab8RN6JkMOaSBbVyj-QCqCd_mTFRiDPDvE6OGw3B8ITzJuwSlw"

# 2. Conexión con Gemini y generación de contenido
print("Consultando a Gemini para generar la lección...")
ai_client = genai.Client(api_key=GEMINI_API_KEY)

prompt = """
Sos un tutor de inglés bilingüe enfocado en llevar a un estudiante de nivel A2 a B1. 
Él estudia ingeniería informática.

Generá una micro-lección clara para WhatsApp con esta estructura exacta:
- Un saludo breve y motivador en español.
- 🗣️ *Daily Expression (B1):* Frase en inglés, explicación clara de su significado en español y un ejemplo en inglés con su traducción al español.
- 💻 *Tech Keyword:* Término de programación o sistemas en inglés, definición en español y un ejemplo de uso cotidiano en IT.
- ✍️ *Tu reto de hoy:* Pedile en español que te responda con una oración en inglés utilizando alguna de las dos opciones aprendidas.

El tono debe ser amigable y didáctico. Usá emojis y formato de negrita de WhatsApp (*texto*).
"""

response_ai = ai_client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents=prompt
)
mensaje_leccion = response_ai.text

# 3. Envío del mensaje por WhatsApp
url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
headers = {
    "Authorization": f"Bearer {META_TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "messaging_product": "whatsapp",
    "recipient_type": "individual",
    "to": DESTINATARIO,
    "type": "text",
    "text": {
        "preview_url": False,
        "body": mensaje_leccion
    }
}

print("Enviando lección a WhatsApp...")
meta_response = requests.post(url, headers=headers, json=payload)

print("Estado HTTP:", meta_response.status_code)
print("Respuesta de Meta:", meta_response.json())