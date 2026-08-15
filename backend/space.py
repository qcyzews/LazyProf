# /backend/space.py
import sys
import os
import gradio as gr
import uvicorn

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

# Tworzymy widok Gradio bez zbędnych funkcji pomocniczych
with gr.Blocks(title="LazyProf API") as demo:
    gr.Markdown(
        "# 🚀 LazyProf Backend API\n\n"
        "Serwer działa poprawnie!\n\n"
        "* **Dokumentacja Swagger UI:** [/docs](/docs)\n"
        "* **Status serwera:** [/health](/health)"
    )

# Montujemy Gradio na aplikacji FastAPI
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    # Przekazujemy bezpośrednio obiekt `app` (zamiast napisu "space:app")
    uvicorn.run(app, host="0.0.0.0", port=7860)