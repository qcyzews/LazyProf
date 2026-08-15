# /backend/space.py
import os
import sys

os.environ["GRADIO_SSR_MODE"] = "false"

import gradio as gr
import spaces

@spaces.GPU
def _dummy_gpu_check():
    pass

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

# Prosty interfejs Gradio
with gr.Blocks(title="LazyProf API") as demo:
    gr.Markdown(
        "# 🚀 LazyProf Backend API\n\n"
        "Serwer działa poprawnie!\n\n"
        "* **Dokumentacja Swagger UI:** [/docs](/docs)\n"
        "* **Status serwera:** [/health](/health)"
    )

# MOUNTUJEMY GRADIO POD ŚCIEŻKĄ /ui ZAMIAST ROOTA "/"
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)