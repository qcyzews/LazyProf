# /backend/space.py
import os
import sys
import gradio as gr
import spaces

# Wymuszenie braku SSR dla Gradio na Hugging Face Spaces
os.environ["GRADIO_SSR_MODE"] = "false"

@spaces.GPU
def _dummy_gpu_check():
    pass

# Dodanie ścieżki do importów lokalnych
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

# Tworzymy widok Gradio
with gr.Blocks(title="LazyProf API") as demo:
    gr.Markdown(
        "# 🚀 LazyProf Backend API\n\n"
        "Serwer działa poprawnie!\n\n"
        "* **Dokumentacja API (Swagger):** [/docs](/docs)\n"
        "* **Status serwera:** [/health](/health)"
    )

# Montujemy Gradio pod ścieżką /ui, dzięki czemu FastAPI odpowiada na korzeniu /
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == "__main__":
    # Standardowe uruchomienie aplikacji Gradio z montowanym FastAPI dla HF Spaces
    demo.launch(server_name="0.0.0.0", server_port=7860, ssr_mode=False)