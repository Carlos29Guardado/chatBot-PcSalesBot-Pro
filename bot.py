import datetime
import logging
import os

import certifi
import telebot
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pc-salesbot")

# 1. Variables de entorno (archivo .env en el servidor)
load_dotenv()
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MONGO_URI = os.environ["MONGO_URI"]

SYSTEM_PROMPT = (
    "Eres PC-SalesBot Pro, un asesor de ventas de computadoras y hardware. "
    "Tu objetivo es recomendar componentes, verificar disponibilidad en catálogo y guiar la compra. "
    "Si te piden algo fuera del catálogo de tecnología, indica amablemente que llamen al +503 2222-1111."
)

# 2. Conexión a MongoDB Atlas
cliente_mongo = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
coleccion_historial = cliente_mongo["pc_sales_db"]["historial_chats"]

# 3. Configuración de Gemini
cliente_gemini = genai.Client(api_key=GEMINI_API_KEY)

bot = telebot.TeleBot(TELEGRAM_TOKEN)


def guardar_mensaje(chat_id, rol, mensaje):
    # Si Mongo falla, el bot debe seguir respondiendo
    try:
        coleccion_historial.insert_one(
            {"chat_id": chat_id, "rol": rol, "mensaje": mensaje, "fecha": datetime.datetime.now()}
        )
    except Exception as e:
        log.error("No se pudo guardar el historial: %s", e)


@bot.message_handler(content_types=["text"])
def procesar_mensaje(message):
    chat_id = message.chat.id
    texto_usuario = message.text
    guardar_mensaje(chat_id, "usuario", texto_usuario)

    try:
        respuesta = cliente_gemini.models.generate_content(
            model=GEMINI_MODEL,
            contents=texto_usuario,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
        )
        texto_respuesta = respuesta.text
        bot.reply_to(message, texto_respuesta.replace("**", ""))
        guardar_mensaje(chat_id, "bot", texto_respuesta)
    except Exception as e:
        log.error("Error con Gemini: %s", e)
        bot.reply_to(message, "Lo siento, tuve un problema procesando tu solicitud.")


if __name__ == "__main__":
    log.info("Bot en línea (modelo %s)...", GEMINI_MODEL)
    bot.infinity_polling(timeout=30, long_polling_timeout=25)
