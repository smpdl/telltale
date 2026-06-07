import gradio as gr

def create_app() -> gr.Blocks:
    with gr.Blocks(title="Telltale") as demo:
        gr.Markdown("# Telltale")
        gr.Markdown("Telltale backend ready")
    return demo

if __name__ == "__main__":
    create_app().launch()
