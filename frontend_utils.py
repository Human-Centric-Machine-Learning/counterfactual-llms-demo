import gradio as gr
import time
import html
from generation_utils import generate_factual, generate_counterfactual, tokenize_text

scrollable_prefix = 'style="border:1px solid #ccc; padding:10px; min-height:100px; max-height: 200px; overflow-y: auto;'

tokens_style = """
    <style>
        .token-button {
            padding: 4px 6px !important;
            margin: 2px !important;
            border-radius: 6px !important;
            display: inline-block !important;
            font-family: monospace !important;
            cursor: default !important;
            color: white !important;
            transition: background-color 0.2s ease-in-out !important;
        }
        .token-button:hover {
            filter: brightness(1.4) !important;
            cursor: pointer !important; /* Change cursor on hover */
        }

        .token-span {
            padding: 4px 6px !important;
            margin: 2px !important;
            border-radius: 6px !important;
            display: inline-block !important;
            font-family: monospace !important;
            cursor: default !important;
            transition: background-color 0.2s ease-in-out !important;
        }

        .token-span-cf {
            padding: 4px 6px !important;
            margin: 2px !important;
            border-radius: 6px !important;
            display: inline-block !important;
            font-family: monospace !important;
            cursor: default !important;
        }
        .token-span-cf:hover {
            filter: brightness(1.4) !important;
        }

        .token-button,
        .token-span,
        .token-span-cf {
            font-family: monospace !important;
            font-size: 14px !important;
            font-weight: 400 !important;
            line-height: 1.5 !important;
        }
    </style>
    """


editable_prefix = f'id="editable" contenteditable="true" {scrollable_prefix} white-space: pre-wrap;'

token_selection_js = """
    // HTML updates can rerun this initializer; replace the previous listener.
    element.onclick = (event) => {
        const token = event.target.closest(".token-button");
        if (!token) return;
        trigger("select_token", {
            prefix_token: Number(token.dataset.prefixToken),
            start_from: Number(token.dataset.startFrom)
        });
    };
"""

def scrollable_text(content):
    return f'<div {scrollable_prefix} white-space: pre-wrap;">{html.escape(content)}</div>'
    # return f'<div style="border:1px solid #ccc; padding:10px; min-height:100px; max-height: 200px; overflow-y: auto; white-space: pre-wrap;">{content}</div>'

def scrollable_tokens_factual(token_list, factual_tokens, mark_token=None):
    return f'<div {scrollable_prefix}">{render_edited_tokens(token_list, factual_tokens, mark_token)}</div>'

def scrollable_tokens_cf(token_list, factual_token_list, partial_token_list, start_from_generated):
    return f'<div {scrollable_prefix}">{render_tokens_cf(token_list, factual_token_list=factual_token_list, partial_token_list=partial_token_list, start_from_generated=start_from_generated)}</div>'

def editable_text(content):
    timestamp = int(time.time() * 1000)
    html_block = f'<div {editable_prefix} data-timestamp="{timestamp}"">{html.escape(content)}</div>'
    return gr.update(value=html_block)


def render_edited_tokens(current_token_list, factual_token_list, mark_token=None):
    factual_response = "".join(factual_token_list)
    prefix_tokens = current_token_list.copy()
    suffix_tokens = current_token_list.copy()

    for i in range(len(current_token_list)):
        suffix = "".join(current_token_list[-i-1:])
        if factual_response.endswith(suffix):
            prefix_tokens.pop()
    
    suffix_tokens = suffix_tokens[len(prefix_tokens):]
    # print(mark_token)

    rendered = f"{tokens_style}"

    for i, token in enumerate(prefix_tokens):
        prefix_color = "#1f1f1f"
        rendered += f'<span class="token-span" style="background-color: {prefix_color}; color: grey">{html.escape(token)}</span>'
    for i, token in enumerate(suffix_tokens):
        suffix_color = "#3a3f5c"
        if mark_token is not None and i+len(prefix_tokens)==int(mark_token):
            suffix_color = "#007bff"
        rendered += f"""<button type='button' class='token-button' style='background-color: {suffix_color};'
                data-start-from='{i+len(factual_token_list)-len(suffix_tokens)}'
                data-prefix-token='{i+len(prefix_tokens)}'>{html.escape(token)}
            </button>
            """

    return rendered



def render_tokens_cf(token_list, factual_token_list, partial_token_list, start_from_generated):
    partial_tokens = len(partial_token_list)
    factual_tokens_to_compare = factual_token_list[int(start_from_generated):]
    cf_tokens_to_compare = token_list[partial_tokens:]

    rendered = ""

    # Render partial tokens with dark colors
    prefix_color = "#1f1f1f"
    for i, token in enumerate(partial_token_list):
        rendered += f'<span class="token-span" style="background-color: {prefix_color}; color: grey">{html.escape(token)}</span>'

    # Render cf_tokens_to_compare
    for i, token in enumerate(cf_tokens_to_compare):
        if i < len(factual_tokens_to_compare) and token == factual_tokens_to_compare[i]:
            color = "#006400"
        else:
            color = "#8B0000"
        rendered += f'<span class="token-span-cf" style="background-color: {color}; color: white">{html.escape(token)}</span>'

    return f'{tokens_style}' + rendered

def update_factual_view_edit(action, partial_response, token_list, factual_tokens, current_view):
    if token_list is None:
        view = current_view
    elif action == "Edit Response ✍️":
        view = editable_text("".join(token_list))
        action = "Show Tokens 🔍"
    elif action == "Show Tokens 🔍":
        view, token_list = retokenize_edit(action, partial_response, token_list, factual_tokens)
        action = "Edit Response ✍️"
    else:
        view = current_view
    return view, action, token_list, 0, None, gr.update(interactive=False)
    
def reset_factual_view(action, factual_tokens, current_view):
    if factual_tokens is None:
        view = current_view
    elif action == "Show Tokens 🔍":
        view = editable_text("".join(factual_tokens))
    elif action == "Edit Response ✍️":
        view = scrollable_tokens_factual(factual_tokens, factual_tokens)
    else:
        view = current_view
    return view, factual_tokens, 0, None, gr.update(interactive=False)


def update_counterfactual_view(show_tokens, response, token_list, partial_tokens, factual_tokens, start_from_generated, current_view):
    if response is None or token_list is None:
        return current_view
    
    if show_tokens:
        scrollable_response = scrollable_tokens_cf(token_list, factual_token_list=factual_tokens, partial_token_list=partial_tokens, start_from_generated=start_from_generated)
    else:
        scrollable_response = scrollable_text(response)
    return scrollable_response

def retokenize_edit(action, partial_response, current_tokens, factual_tokens):
    if action == "Edit Response ✍️":
        return editable_text("".join(current_tokens)), current_tokens
    
    token_list = tokenize_text(partial_response)
    if token_list==['\n']:
        token_list=[]

    timestamp = int(time.time() * 1000)
    html_block = f'<div {scrollable_prefix} data-timestamp="{timestamp}"">{render_edited_tokens(token_list, factual_tokens)}</div>'
    return gr.update(value=html_block), token_list

def update_clicked_token(current_tokens, factual_tokens, mark_token):
    # print(current_tokens[:int(mark_token)])
    timestamp = int(time.time() * 1000)
    html_block = f'<div {scrollable_prefix} data-timestamp="{timestamp}">{render_edited_tokens(current_tokens, factual_tokens, mark_token)}</div>'
    return gr.update(value=html_block)

def select_factual_token(current_tokens, factual_tokens, event: gr.EventData):
    prefix_token = int(event.prefix_token)
    start_from = int(event.start_from)
    view = update_clicked_token(current_tokens, factual_tokens, prefix_token)
    return view, prefix_token, start_from, gr.update(interactive=True)


# def copy_tokens_to_partial_response(token_list, start_from):
#     # Assuming token_list is a list of tokens and start_from is an integer index
#     copied_tokens = "".join(token_list[:int(start_from)])
#     # print('copy',token_list[:int(start_from)])
#     # return copied_tokens
#     timestamp = int(time.time() * 1000) # Unique identifier to force update
#     html_block = f'''<div id="editable" contenteditable="true" 
#          style="border:1px solid #ccc; padding:10px; min-height:100px; max-height: 200px; overflow-y: auto; white-space: pre-wrap;" 
#          data-timestamp="{timestamp}">{copied_tokens}</div>'''
#     return gr.update(value=html_block), start_from

def sleep_button():
    time.sleep(10)
    return gr.update(interactive=True)

def on_generate_factual(user, system, seed, temperature):
        yield scrollable_text('Generating response...'),None, None, None, None, None

        try:
            seed = int(seed)
            temperature = float(temperature)
            if seed < 0 or seed >= 2**32:
                raise ValueError("Invalid seed")
            if temperature < 0 or temperature > 1:
                raise ValueError("Invalid temperature")
            
            response, token_list, factual_data, rngstates = generate_factual(html.unescape(user), system=html.unescape(system), seed=seed, temperature=temperature)
        except ValueError as e:
            yield scrollable_text(str(e)), None, None, None, None, None
        except TypeError as e:
            yield scrollable_text("Invalid seed or temperature"), None, None, None, None, None
        except RuntimeError as e:
            yield scrollable_text(str(e)), None, None, None, None, None
            
        scrollable_response = scrollable_tokens_factual(token_list, token_list, mark_token=None)
        yield scrollable_response, response, token_list, factual_data, rngstates, token_list  # show, state1, state2


def on_generate_counterfactual(current_tokens, prefix_token, start_from, factual_data, rngstates, user, factual_token_list):
        # Display "Generating response..." while processing
        yield scrollable_text('Generating response...'),None,None, None, None

        # print('p',[c for c in partial_response])
        if prefix_token is None:
            prefix_token = len(current_tokens)
        partial_response = "".join(current_tokens[:int(prefix_token)])
        try:
            response, token_list, fixed_tokens = generate_counterfactual(html.unescape(partial_response),start_from, factual_data, rngstates, html.unescape(user))
        except RuntimeError as e:
            yield scrollable_text(str(e)), None, None, None, None, None

        # scrollable_response = scrollable_text(response)
        scrollable_response = scrollable_tokens_cf(token_list, factual_token_list=factual_token_list, partial_token_list=fixed_tokens, start_from_generated=start_from)
        yield scrollable_response, response, token_list, fixed_tokens, start_from
