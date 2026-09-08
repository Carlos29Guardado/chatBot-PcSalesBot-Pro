import telebot
import certifi
import google.generativeai as genai
from pymongo import MongoClient
import datetime
import os
from flask import Flask
from threading import Thread


app = Flask(__name__)
@app.route('/')
def home():
    return "PC-SalesBot está corriendo perfectamente en la nube."

def run_server():
    port = int(os.environ.get('PORT', 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Variables de entorno
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
MONGO_URI = os.environ.get('MONGO_URI')

# 3. Conexión a MongoDB Atlas
ca = certifi.where()
cliente_mongo = MongoClient(MONGO_URI, tlsCAFile=ca)
db = cliente_mongo['pc_sales_db']
coleccion_historial = db['historial_chats']

# 4. Configuración de Gemini
genai.configure(api_key=GEMINI_API_KEY)
modelo = genai.GenerativeModel(
    model_name="gemini-3.8-flash", 
    system_instruction="Eres PC-SalesBot Pro, un asesor de ventas de computadoras y hardware. Tu objetivo es recomendar componentes, verificar disponibilidad en catálogo y guiar la compra. Si te piden algo fuera del catálogo de tecnología, indica amablemente que llamen al +503 2222-1111."
)

bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(func=lambda message: True)
def procesar_mensaje(message):
    chat_id = message.chat.id
    texto_usuario = message.text

    coleccion_historial.insert_one({"chat_id": chat_id, "rol": "usuario", "mensaje": texto_usuario, "fecha": datetime.datetime.now()})

    try:
        respuesta_gemini = modelo.generate_content(texto_usuario)
        texto_respuesta = respuesta_gemini.text
        bot.reply_to(message, texto_respuesta)
        coleccion_historial.insert_one({"chat_id": chat_id, "rol": "bot", "mensaje": texto_respuesta, "fecha": datetime.datetime.now()})
    except Exception as e:
        bot.reply_to(message, "Lo siento, tuve un problema procesando tu solicitud.")

if __name__ == "__main__":
    # Iniciar el servidor web en un hilo paralelo
    t = Thread(target=run_server)
    t.start()
    
    # Iniciar el bot de Telegram
    print("Bot en línea...")
    bot.infinity_polling()