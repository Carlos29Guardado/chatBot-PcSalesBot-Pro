import google.generativeai as genai

# Reemplaza con tu clave real
genai.configure(api_key='AIzaSyCU9a3JGIYC28h-qEWAKQynJVv0-IeGD8g')

print("Modelos disponibles para tu API:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)