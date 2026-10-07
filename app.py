import gradio as gr


import frontend_utils
from generation_utils import generate_factual, generate_counterfactual



js_code = """
    (...inputs) => {
        const editable = document.getElementById("editable");
        inputs[1] = editable ? editable.innerText : "";
        return inputs;
    }
    """

# css = """
# * {
#     font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
# }
css = """
body, * {
  font-family: 'IBM Plex Sans', sans-serif !important;
}

footer {
    display: none !important;
}
"""

custom_theme = gr.themes.Default(
    font=[
        "IBM Plex Sans",  # body
        "IBM Plex Sans",  # heading
        "IBM Plex Sans"   # monospace (optional)
    ]
)

# Gradio UI
demo = gr.Blocks(css=css,
                 analytics_enabled=False,
                 theme=custom_theme,
                 title="Counterfactual Token Generation")
with demo:
    gr.Markdown("# Counterfactual Token Generation")
    gr.Markdown("### Ivi Chatzi, Nina Corvelo Benz, Eleni Straitouri, Stratis Tsirtsis, and Manuel Gomez-Rodriguez")
    gr.Markdown("### Check out our [paper](https://arxiv.org/abs/2409.17027) 📄")
    gr.Markdown("""## How to use: \n
                - Enter your prompt, then click on **Generate Response** 🚀.
                - Click on **Edit Response** ✍️ and edit the text.
                - Click on **Show Tokens** 🔍, then **click** on the token that you wish to start generating from.
                - Click on **Generate Counterfactual Response** 🚀. Tokens that change are marked red.
                """)

    with gr.Row():
        with gr.Column():
            user_input = gr.Textbox(value="What is a very nice color?",label="Your Prompt:")
            with gr.Accordion("Additional Generation Options 💬", open=False):
                system_input = gr.Textbox(value="Keep your replies short and to the point.",label="System Prompt:")
                seed_input = gr.Number(value=987698, label="Random Seed:")
                temperature_input = gr.Number(value=0.7, label="Temperature:")
                gr.Markdown("Model: Llama-3.1-8B-Instruct")
                # with gr.Row():
                #     model_input = gr.Dropdown(choices=['Llama-3.2-1B-Instruct', 'Llama-3.2-3B-Instruct'], value='Llama-3.2-1B-Instruct', label='Model:')
                #     model_button = gr.Button("Load model")

    with gr.Row():
        generate_button = gr.Button("Generate Response 🚀")
        with gr.Column():
            edit_button = gr.Button(value="Edit Response ✍️", interactive=False)
            reset_factual_button = gr.Button("Reset Edits 🔄", interactive=False)
        
        counterfactual_button = gr.Button("Generate Counterfactual Response 🚀",interactive=False)
        toggle_counterfactual_tokens = gr.Checkbox(label="Show Counterfactual Tokens 🔍", interactive=False)


    factual_response = gr.State()
    factual_token_list = gr.State()
    factual_data = gr.State()
    factual_rngstates = gr.State()
    current_token_list = gr.State()
    start_from = gr.State()
    prefix_token = gr.State()

    cf_response = gr.State()
    cf_token_list = gr.State()
    partial_token_list = gr.State()
    start_from_generated = gr.State()

    with gr.Row():
        factual_output = gr.HTML(label="Factual Output",
                                 value=frontend_utils.scrollable_text("Response"),
                                 js_on_load=frontend_utils.token_selection_js)
        # with gr.Column():
        counterfactual_output = gr.HTML(label="Counterfactual Output",value=frontend_utils.scrollable_text('Counterfactual response'))
    gr.Markdown("[Imprint](https://imprint.mpi-klsb.mpg.de/sws/cf-token-gen.mpi-sws.org) [Data Protection](https://data-protection.mpi-klsb.mpg.de/sws/cf-token-gen.mpi-sws.org)")
    
    hidden_editable = gr.Textbox(visible="hidden", elem_id="hidden_edit")
    

    generate_button.click(fn=lambda: gr.update(interactive=False),inputs=None,outputs=generate_button)
    generate_button.click(fn=frontend_utils.sleep_button, inputs=None, outputs=generate_button)
    generate_button.click(frontend_utils.on_generate_factual,
            inputs=[user_input,system_input,seed_input,temperature_input],
            outputs=[factual_output,
                     factual_response,
                     factual_token_list,
                     factual_data,
                     factual_rngstates,
                     current_token_list])
    generate_button.click(fn=lambda : (None, None, None, 0, None, 0),
                          inputs=None,
                          outputs=[cf_response,cf_token_list,partial_token_list, start_from, prefix_token, start_from_generated])
    generate_button.click(fn=lambda _: frontend_utils.scrollable_text('Counterfactual response'),
                          outputs=counterfactual_output)
    generate_button.click(fn=lambda: gr.update(interactive=False), inputs=None, outputs=counterfactual_button)
    generate_button.click(fn=lambda: gr.update(interactive=True),inputs=None,outputs=edit_button)
    generate_button.click(fn=lambda: gr.update(interactive=True),inputs=None,outputs=reset_factual_button)
    generate_button.click(fn=lambda: gr.update(interactive=False),inputs=None,outputs=toggle_counterfactual_tokens)
    generate_button.click(fn=lambda: False, inputs=None, outputs=toggle_counterfactual_tokens)
    generate_button.click(fn=lambda: "Edit Response ✍️", inputs=None, outputs=[edit_button])
    
    factual_output.select_token(fn=frontend_utils.select_factual_token,
                                inputs=[current_token_list, factual_token_list],
                                outputs=[factual_output, prefix_token, start_from, counterfactual_button],
                                show_progress="hidden")

    # change from edit view to token view
    edit_button.click(fn=frontend_utils.update_factual_view_edit,
                      js=js_code,
                      inputs=[edit_button, hidden_editable, current_token_list, factual_token_list, factual_output],
                      outputs=[factual_output, edit_button, current_token_list, start_from, prefix_token, counterfactual_button],
                      show_progress="hidden")
    
    # reset all edits on factual text
    reset_factual_button.click(fn=frontend_utils.reset_factual_view,
                               inputs=[edit_button, factual_token_list, factual_output],
                               outputs=[factual_output, current_token_list, start_from, prefix_token, counterfactual_button],
                               show_progress="hidden")


    counterfactual_button.click(fn=lambda _: False,
                                inputs=[toggle_counterfactual_tokens],
                                outputs=[toggle_counterfactual_tokens])
    counterfactual_button.click(fn=lambda: gr.update(interactive=False),inputs=None,outputs=counterfactual_button)
    counterfactual_button.click(fn=lambda: gr.update(interactive=False),inputs=None,outputs=generate_button)
    counterfactual_button.click(fn=lambda: gr.update(interactive=True),inputs=None,outputs=toggle_counterfactual_tokens)
    counterfactual_button.click(fn=lambda: True,inputs=None,outputs=toggle_counterfactual_tokens)
    # counterfactual_button.click(fn=frontend_utils.sleep_button, inputs=None, outputs=counterfactual_button)
    counterfactual_button.click(fn=lambda: gr.update(interactive=False), inputs=None, outputs=counterfactual_button)
    counterfactual_button.click(fn=frontend_utils.sleep_button, inputs=None, outputs=generate_button)
    counterfactual_button.click(fn=frontend_utils.on_generate_counterfactual,
                                inputs=[current_token_list, prefix_token, start_from, factual_data, factual_rngstates, user_input, factual_token_list],
                                outputs=[counterfactual_output, cf_response, cf_token_list, partial_token_list, start_from_generated])
    toggle_counterfactual_tokens.change(
        frontend_utils.update_counterfactual_view,
        inputs=[toggle_counterfactual_tokens, cf_response, cf_token_list,partial_token_list, factual_token_list, start_from_generated, counterfactual_output],
        outputs=[counterfactual_output]
    )
app=demo.launch(server_name="0.0.0.0",server_port=5000, show_error=True)
