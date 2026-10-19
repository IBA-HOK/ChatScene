import re
from os import path as osp
import shutil
from safebench.util.scenic_utils import ScenicSimulator

def load_file(file_path):
    with open(file_path, 'r') as file:
        return file.read()

def retrieve_topk(model, topk, descriptions, snippets, embeddings, current_description):
    try:
        current_embedding = model.encode([current_description], device='cuda', convert_to_tensor=True)
        scores = (current_embedding @ embeddings.T).squeeze(0)
    except Exception:
        import os
        cur_emb = model.encode([current_description], device='cpu', convert_to_tensor=True)
        # ensure embeddings on same device for scoring
        try:
            scores = (cur_emb @ embeddings.T).squeeze(0)
        except Exception:
            # embeddings may be cuda tensors; move to cpu
            if hasattr(embeddings, 'cpu'):
                embeddings = embeddings.cpu()
            if hasattr(cur_emb, 'cpu'):
                cur_emb = cur_emb.cpu()
            scores = (cur_emb @ embeddings.T).squeeze(0)
        current_embedding = cur_emb
    top_indices = scores.topk(k=topk).indices
    # top_indices may be on cuda/cpu; move to cpu for indexing
    try:
        idx_list = top_indices.cpu().tolist() if hasattr(top_indices, 'cpu') else top_indices.tolist()
    except Exception:
        idx_list = [int(i) for i in top_indices]
    top_descriptions = [descriptions[i] for i in idx_list]
    top_snippets = [snippets[i] for i in idx_list]
    return top_descriptions, top_snippets

def extract_scenic_code(text):
    if not text:
        raise ValueError("No scenic fence found: empty response")
    pattern = r"```(?:scenic|python)?\s*(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    for m in matches:
        stripped = m.strip()
        if stripped:
            return stripped
    if text.strip():
        for kw in ("param ", "behavior ", "import ", "model "):
            if kw in text.lower():
                return text.strip()
    raise ValueError("No scenic fence found")

def generate_code_snippet(llm_model, category_prompt, descriptions, snippets, current_description, topk, use_llm, max_retries: int = 1):
    system_prompt = '''Your goal is to assist me in writing snippets using Scenic 2.1 for CARLA simulation. Scenic is a domain-specific probabilistic programming language designed for modeling environments in cyber-physical systems like robots and autonomous vehicles. Please adhere strictly to the Scenic 2.1 API, avoiding the use of any non-existent APIs or the Python random package.'''
    if not use_llm:
        return snippets[0]
    content = '\n'
    for j in range(topk):
        content += f'Description: {descriptions[j]}\nSnippet:\n```scenic\n{snippets[j]}```\n'
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": category_prompt.format(content=content, current_description=current_description)},
    ]
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            generated_code = llm_model.generate(messages)
            if not generated_code or not str(generated_code).strip():
                raise ValueError("empty LLM response")
            return extract_scenic_code(str(generated_code))
        except Exception as e:
            last_error = e
            print(f"generate_code_snippet attempt {attempt + 1}/{max_retries + 1} failed: {e}")
            if attempt >= max_retries:
                break
    print(f"generate_code_snippet failed after {max_retries + 1} attempts: {last_error}")
    if snippets:
        return snippets[0]
    raise ValueError(f"generate_code_snippet exhausted retries: {last_error}")

def save_scenic_code(local_path, port_ip, scenic_code, q, verify: str = "scenic"):
    file_path = osp.join(local_path, f'safebench/scenario/scenario_data/scenic_data/dynamic_scenario/dynamic_{q}.scenic')
    backup_path = osp.join(local_path, f'safebench/scenario/scenario_data/scenic_data/dynamic_scenario/dynamic_{q}.txt')
    with open(file_path, 'w') as file:
        file.write(scenic_code)
    if verify == "none":
        print(f"Scenic code saved (verify=none) at {file_path}")
        return True
    if verify == "parse":
        if "param map" in scenic_code and "AdvBehavior" in scenic_code and "Town" in scenic_code:
            print(f"Scenic code parse OK (heuristic) at {file_path}")
            return True
        print(f"Parse heuristic failed for {q}: missing required keywords")
        shutil.move(file_path, backup_path)
        print(f"Moved to {backup_path}")
        return False
    extra_params = {'port': port_ip, 'traffic_manager_port': port_ip + 6000}
    try:
        print("Checking if the Scenic code is compilable...")
        ScenicSimulator(file_path, extra_params)
        print(f"Scenic code saved and verified as compilable at {file_path}")
        return True
    except Exception as e:
        print(f"Failure in compiling Scenic code with ID {q}: {str(e)}")
        shutil.move(file_path, backup_path)
        print(f"Moved problematic Scenic file to {backup_path}")
        return False