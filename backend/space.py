# /backend/space.py
import os
import sys
import uvicorn
import gradio as gr
import spaces

# Wymuszenie braku SSR dla Gradio na Hugging Face Spaces
os.environ["GRADIO_SSR_MODE"] = "false"

@spaces.GPU
def _dummy_gpu_check():
    pass

# Dodanie ścieżki do importów
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app as fastapi_app

# Prosty panel informacyjny w Gradio
with gr.Blocks(title="LazyProf API") as demo:
    gr.Markdown(
        "# 🚀 LazyProf Backend API\n\n"
        "Serwer działa poprawnie!\n\n"
        "* **Dokumentacja API (Swagger):** [/docs](/docs)\n"
        "* **Status serwera:** [/health](/health)"
    )

# Montujemy Gradio na podścieżce /ui, dzięki czemu FastAPI zachowuje główny ruch na "/"
app = gr.mount_gradio_app(fastapi_app, demo, path="/ui")

if __name__ == "__main__":
    # Uruchomienie serwera Uvicorn na porcie 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)