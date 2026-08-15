# /backend/space.py
import sys
import os
import gradio as gr

# Dodajemy bieżący katalog do sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

# Prosty interfejs Gradio
demo = gr.Interface(
    fn=lambda: "LazyProf Backend API działa! Dokumentacja Swagger jest dostępna pod adresem /docs",
    inputs=[],
    outputs="text",
    title="LazyProf API",
)

# Łączymy FastAPI i Gradio w jedną aplikację
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

# USUŃ / ZAKOMENTUJ PONIŻSZY BLOK:
# if __name__ == "__main__":
#     uvicorn.run(app, host="0.0.0.0", port=7860)