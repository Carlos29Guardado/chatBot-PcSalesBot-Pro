import datetime
import logging
import os
import unicodedata

import certifi
import httpx
import telebot
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pc-salesbot")

# 1. Variables de entorno (archivo .env en el servidor)
load_dotenv()
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
# Segundos máximos de espera por modelo antes de pasar al de respaldo
GEMINI_TIMEOUT = int(os.environ.get("GEMINI_TIMEOUT", "25"))
MONGO_URI = os.environ["MONGO_URI"]

SYSTEM_PROMPT = (
    "Eres PC-SalesBot Pro, un asesor de ventas de computadoras y hardware. "
    "Tu objetivo es recomendar componentes, verificar disponibilidad en catálogo y guiar la compra. "
    "Si te piden algo fuera del catálogo de tecnología, indica amablemente que llamen al +503 2222-1111."
)

# 2. Conexión a MongoDB Atlas (se abre al guardar el primer mensaje, así el bot
#    arranca aunque el cluster esté pausado)
coleccion_historial = None


def obtener_historial():
    global coleccion_historial
    if coleccion_historial is None:
        cliente_mongo = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        coleccion_historial = cliente_mongo["pc_sales_db"]["historial_chats"]
    return coleccion_historial

# 3. Configuración de Gemini
cliente_gemini = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT * 1000),  # en milisegundos
)

bot = telebot.TeleBot(TELEGRAM_TOKEN)


def guardar_mensaje(chat_id, rol, mensaje):
    # Si Mongo falla, el bot debe seguir respondiendo
    try:
        obtener_historial().insert_one(
            {"chat_id": chat_id, "rol": rol, "mensaje": mensaje, "fecha": datetime.datetime.now()}
        )
    except Exception as e:
        log.error("No se pudo guardar el historial: %s", e)


def generar_respuesta(texto_usuario):
    # Si el modelo principal está saturado (5xx) o sin cuota (429), se intenta con el de respaldo
    ultimo_error = None
    for modelo in (GEMINI_MODEL, GEMINI_FALLBACK_MODEL):
        try:
            respuesta = cliente_gemini.models.generate_content(
                model=modelo,
                contents=texto_usuario,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            return respuesta.text
        except errors.APIError as e:
            if not (isinstance(e, errors.ServerError) or e.code == 429):
                raise
            log.warning("Modelo %s no disponible: %s", modelo, e)
            ultimo_error = e
        except httpx.TimeoutException as e:
            log.warning("Modelo %s no respondió en %s s", modelo, GEMINI_TIMEOUT)
            ultimo_error = e
    raise ultimo_error


MENSAJE_BIENVENIDA = (
    "¡Hola! 👋 Soy PC-SalesBot Pro, tu asesor de computadoras y hardware.\n\n"
    "Puedo ayudarte a:\n"
    "• Armar una PC según tu presupuesto y uso (gaming, programación, diseño, oficina)\n"
    "• Recomendarte componentes: procesador, tarjeta gráfica, RAM, almacenamiento\n"
    "• Comparar opciones y resolver dudas antes de comprar\n\n"
    "Por ejemplo, escríbeme: \"Quiero una PC para programar con $600\"."
)

SALUDOS = {
    "hola", "holaa", "hi", "hello", "hey", "buenas", "buenos dias", "buenas tardes",
    "buenas noches", "que tal", "saludos",
}


def es_saludo(texto):
    normalizado = unicodedata.normalize("NFD", texto.lower())
    normalizado = "".join(c for c in normalizado if c.isalnum() or c.isspace())
    return " ".join(normalizado.split()) in SALUDOS


@bot.message_handler(commands=["start", "help", "ayuda"])
def bienvenida(message):
    bot.reply_to(message, MENSAJE_BIENVENIDA)


@bot.message_handler(content_types=["text"])
def procesar_mensaje(message):
    chat_id = message.chat.id
    texto_usuario = message.text
    guardar_mensaje(chat_id, "usuario", texto_usuario)

    # Los saludos se responden sin llamar a Gemini
    if es_saludo(texto_usuario):
        bot.reply_to(message, MENSAJE_BIENVENIDA)
        guardar_mensaje(chat_id, "bot", MENSAJE_BIENVENIDA)
        return

    try:
        # Muestra "escribiendo..." en Telegram mientras Gemini responde
        bot.send_chat_action(chat_id, "typing")
        texto_respuesta = generar_respuesta(texto_usuario)
        bot.reply_to(message, texto_respuesta.replace("**", ""))
        guardar_mensaje(chat_id, "bot", texto_respuesta)
    except Exception as e:
        log.error("Error con Gemini: %s", e)
        bot.reply_to(message, "Lo siento, tuve un problema procesando tu solicitud.")


if __name__ == "__main__":
    log.info("Bot en línea (modelo %s)...", GEMINI_MODEL)
    bot.infinity_polling(timeout=30, long_polling_timeout=25)
