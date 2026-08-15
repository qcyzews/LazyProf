# /backend/space.py
import sys
import os
import gradio as gr

# Dodajemy bieżący katalog do sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

# Prosty interfejs startowy Gradio
with gr.Blocks(title="LazyProf API") as demo:
    gr.Markdown(
        "# 🚀 LazyProf Backend API\n\n"
        "Serwer działa poprawnie!\n\n"
        "* **Dokumentacja Swagger UI:** [/docs](/docs)\n"
        "* **Status serwera:** [/health](/health)"
    )

# Montujemy FastAPI na aplikacji Gradio
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    # demo.launch() bezpiecznie zarządza portem 7860 w środowisku Hugging Face
    demo.launch(server_name="0.0.0.0", server_port=7860)