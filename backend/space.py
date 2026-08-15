# /backend/space.py
import os
import sys

# Wyłączamy serwer SSR Node.js w Gradio przed zaimportowaniem biblioteki
os.environ["GRADIO_SSR_MODE"] = "false"

import gradio as gr

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

with gr.Blocks(title="LazyProf API") as demo:
    gr.Markdown(
        "# 🚀 LazyProf Backend API\n\n"
        "Serwer działa poprawnie!\n\n"
        "* **Dokumentacja Swagger UI:** [/docs](/docs)\n"
        "* **Status serwera:** [/health](/health)"
    )

app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, ssr_mode=False)