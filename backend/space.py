# /backend/space.py
import sys
import os
import gradio as gr
import uvicorn

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

demo = gr.Interface(
    fn=lambda: "LazyProf Backend API działa! Dokumentacja Swagger jest dostępna pod adresem /docs",
    inputs=[],
    outputs="text",
    title="LazyProf API",
)

app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run("space:app", host="0.0.0.0", port=7860, reload=False)