# /backend/app/__init__.py
from app.main import app as fastapi_app
import gradio as gr

# Widok demo dla interfejsu Gradio
demo = gr.Interface(
    fn=lambda: "LazyProf Backend API działa! Dokumentacja Swagger jest dostępna pod adresem /docs",
    inputs=[],
    outputs="text",
    title="LazyProf API",
)

# Eksport zmiennej 'app' wymaganej przez serwer Uvicorn / HF Spaces
app = gr.mount_gradio_app(fastapi_app, demo, path="/")