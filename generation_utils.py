import torch
import json
import os
import time
from transformers import AutoTokenizer, AutoModelForCausalLM, DynamicCache
from functools import wraps

def rate_limit(interval):
    def decorator(func):
        last_called = [0]  # Use a mutable object to store the last call time

        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            if now - last_called[0] < interval:
                raise RuntimeError(f"Rate limit exceeded.")
            last_called[0] = now
            return func(*args, **kwargs)
        return wrapper
    return decorator

# Model parameters
CACHE_DIR = "./models"  # Local cache directory
MODEL_NAME="meta-llama/Llama-3.1-8B-Instruct"

print("Loading model and tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir=CACHE_DIR)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, cache_dir=CACHE_DIR, device_map="cuda:0")
# model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, cache_dir=CACHE_DIR)

n_total = len(tokenizer.get_vocab())  # Total number of tokens in vocabulary

# Gumbel-Max SCM sampling
def sampler(probs, n_total, rng):
    u = torch.rand(n_total, generator=rng, device=probs.device)
    gumbels = -torch.log(-torch.log(u + 1e-20) + 1e-20)
    # print(gumbels)
    total_probs = torch.log(probs + 1e-20) + gumbels
    argmax = torch.argmax(total_probs, dim=-1)
    return torch.tensor([[argmax.item()]], device=probs.device)

# Factual generation function
# @rate_limit(5)
def generate_factual(user, seed=42,system='Keep your replies short and to the point.', temperature=0.7, max_length=1000):
    chat = [
        {"role": "system", "content": system},
        {"role": "user", "content": user}
    ]
    inputs = tokenizer.apply_chat_template(chat, add_generation_prompt=True, return_tensors="pt", return_dict=True).to(model.device)

    # initialize the random number generator
    rng = torch.Generator(device=model.device)
    rng.manual_seed(seed)

    # generate the response
    eos_token_id = tokenizer.eos_token_id
    past_key_values = DynamicCache()
    cache_position = torch.arange(inputs.input_ids.shape[1], dtype=torch.int64, device=model.device)
    generated_ids = inputs.input_ids
    query_length = inputs.input_ids.shape[1]
    model.eval()

    token_genstates = torch.zeros((max_length, rng.get_state().numel()), dtype=torch.uint8)

    with torch.no_grad():
        for token_counter in range(max_length):
            outputs = model(**inputs, cache_position=cache_position, past_key_values=past_key_values, use_cache=True)
            logits = outputs.logits[:, -1, :n_total]
            probs = torch.nn.functional.softmax(logits / temperature, dim=-1, dtype=torch.float32)

            # Sample next token
            token_genstates[token_counter] = rng.get_state()
            next_token_ids = sampler(probs, n_total, rng)

            generated_ids = torch.cat([generated_ids, next_token_ids], dim=-1)

            attention_mask = inputs["attention_mask"]
            attention_mask = torch.cat([attention_mask, attention_mask.new_ones((attention_mask.shape[0], 1))], dim=-1)
            inputs = {"input_ids": next_token_ids, "attention_mask": attention_mask}
            cache_position = cache_position[-1:] + 1

            if next_token_ids.item() == eos_token_id:
                break

    response_tokens = generated_ids[0, query_length:]
    response = tokenizer.decode(response_tokens, skip_special_tokens=True)
    token_list = [tokenizer.decode(response_tokens[i]) for i in range(len(response_tokens)-1)]

    # Store factual data
    factual_data = {
        "user": user,
        "system":system,
        "seed": seed,
        "temperature": temperature,
        "max_length": max_length,
        "factual_response": response,
        # "partial_response": response,  # Initially, partial_response is the same
        # "start_from": 0,
        "token_list": token_list,
    }
    # if not os.path.exists(OUTPUT_DIR):
    #     os.makedirs(OUTPUT_DIR)
    # with open(os.path.join(OUTPUT_DIR, "factual.json"), "w") as f:
    #     json.dump(factual_data, f, indent=4)
    # torch.save(token_genstates, os.path.join(OUTPUT_DIR, 'rngstates.pt'))
    # print('f',token_list[:15])
    return response,token_list, factual_data, token_genstates

def tokenize_text(text):
    tokens=tokenizer.encode(text, add_special_tokens=False)
    token_list=[tokenizer.decode(tokens[i]) for i in range(len(tokens))]
    return token_list

# @rate_limit(5)
def generate_counterfactual(partial_response,start_from, factual_data, rngstates, user=None):
    # print(partial_response)
    # factual_data_path = os.path.join(OUTPUT_DIR, "factual.json")
    # if not os.path.exists(factual_data_path):
    #     return "Run factual generation first!"

    # with open(factual_data_path, "r") as f:
    #     factual_data = json.load(f)

    # rngstates = torch.load(os.path.join(OUTPUT_DIR, 'rngstates.pt'))
    init_rng_state = rngstates[int(start_from),:]
    if user is not None:
        pass
    else:
        user = factual_data["user"]
    
    chat = [
        {"role": "system", "content": factual_data['system']},
        {"role": "user", "content": user}
    ]
    inputs = tokenizer.apply_chat_template(chat, add_generation_prompt=True, return_tensors="pt", return_dict=True).to(model.device)
    fixed_tokens = tokenizer.encode(partial_response)
    fixed_tokens = fixed_tokens[1:]
    print([tokenizer.decode(fixed_tokens[i]) for i in range(len(fixed_tokens))])

    if len(fixed_tokens) > 0:
        inputs['input_ids'] = torch.cat([inputs['input_ids'][0], torch.tensor(fixed_tokens,device=model.device)], dim=-1).unsqueeze(0)
        inputs['attention_mask'] = torch.cat([inputs['attention_mask'], inputs['attention_mask'].new_ones((inputs['attention_mask'].shape[0], len(fixed_tokens)))], dim=-1)

    # modified_tokens = tokenizer.encode(modified_text, add_special_tokens=False)
    
    # if str(start_from) not in factual_data["random_states"]:
    #     return "Invalid start position. Choose a valid token index."

    # rng_state = tuple(factual_data["random_states"][str(start_from)])

    # rng = torch.Generator(device=model.device)
    # rng.set_state(torch.tensor(rng_state, dtype=torch.uint8))

    rng = torch.Generator(device=model.device)
    rng.manual_seed(factual_data["seed"])
    rng.set_state(init_rng_state)

    # input_ids = tokenizer(modified_text, return_tensors="pt").input_ids
    # output = modified_tokens[:]
    # generate the response

    eos_token_id = tokenizer.eos_token_id
    past_key_values = DynamicCache()
    cache_position = torch.arange(inputs.input_ids.shape[1], dtype=torch.int64, device=model.device)
    generated_ids = inputs.input_ids
    query_length = inputs.input_ids.shape[1]
    model.eval()

    with torch.no_grad():
        for token_counter in range(factual_data['max_length']):
            outputs = model(**inputs, cache_position=cache_position, past_key_values=past_key_values, use_cache=True)

            logits = outputs.logits[:, -1, :n_total]
            probs = torch.nn.functional.softmax(logits / factual_data['temperature'], dim=-1, dtype=torch.float32)

            # sample the next token using the Gumbel-Max SCM over the joint vocabulary
            next_token_ids = sampler(probs, n_total, rng)
            # print(tokenizer.decode(next_token_ids[0]))

            generated_ids = torch.cat([generated_ids, next_token_ids], dim=-1)      

            # NOTE: use caching to speed-up the autoregressive generation
            # see https://huggingface.co/docs/transformers/kv_cache#under-the-hood-how-cache-object-works-in-attention-mechanism
            attention_mask = inputs["attention_mask"]
            attention_mask = torch.cat([attention_mask, attention_mask.new_ones((attention_mask.shape[0], 1))], dim=-1)
            inputs = {"input_ids": next_token_ids, "attention_mask": attention_mask}
            cache_position = cache_position[-1:] + 1 # add one more position for the next token

            if next_token_ids.item() == eos_token_id:
                break

    # for _ in range(50 - len(modified_tokens)):
    #     logits = model(input_ids).logits[:, -1, :]
    #     probs = torch.softmax(logits, dim=-1).detach().numpy()

    #     gumbel_noise = torch.rand(probs.shape).numpy()
    #     sampled_token = torch.argmax(torch.log(torch.tensor(probs)) + gumbel_noise)

    #     output.append(sampled_token.item())
    #     input_ids = torch.cat([input_ids, torch.tensor([[sampled_token]])], dim=1)
    # get the generated response (after the generation prompt token)
    response_tokens = generated_ids[0, query_length-len(fixed_tokens):]
    response = tokenizer.decode(response_tokens, skip_special_tokens=True)

    token_list=[tokenizer.decode(response_tokens[i]) for i in range(len(response_tokens)-1)]
    # print('c',token_list[:15])

    # print("Response: ", response)
    return response, token_list, [tokenizer.decode(fixed_tokens[i]) for i in range(len(fixed_tokens))]
    # return tokenizer.decode(output)