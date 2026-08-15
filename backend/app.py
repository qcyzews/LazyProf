# /backend/app.py
import sys
import os
import gradio as gr
import uvicorn

# Dodajemy katalog główny (w którym znajduje się app.py i folder app/) do ścieżki Pythona
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

# Prosty widok demo na głównej stronie Space
demo = gr.Interface(
    fn=lambda: "LazyProf Backend API działa! Dokumentacja Swagger jest dostępna pod adresem /docs",
    inputs=[],
    outputs="text",
    title="LazyProf API",
)

# Montujemy FastAPI w aplikacji Gradio
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    # HF Spaces wymaga uruchomienia serwera na porcie 7860 i adresie 0.0.0.0
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=False)