import setGPU
import os
import csv
import pickle
import re
import argparse
from os import path as osp
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from architecture import LLMChat, STRATA_DEFAULT_MODEL
from utils import load_file, retrieve_topk, generate_code_snippet, save_scenic_code


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="ChatScene retrieval + LLM generation (Strata/qwen default)")
    parser.add_argument('--port_ip', type=int, default=2000, help='Port IP address (default: 2000)')
    parser.add_argument('--topk', type=int, default=3, help='Top K value (default: 3) for retrieval')
    parser.add_argument('--model', type=str, default=STRATA_DEFAULT_MODEL, help="Model name (default: qwen3.8-flash-next-iq3_s), also supports gpt-4o / local HF")
    parser.add_argument('--provider', type=str, default='strata', choices=['strata', 'openai', 'local', 'auto'], help='LLM provider (default: strata)')
    parser.add_argument('--fallback-models', type=str, default='', help='Comma-separated fallback models (empty = none)')
    parser.add_argument('--verify', type=str, default='parse', choices=['parse', 'scenic', 'none'], help='Verification mode (default: parse)')
    parser.add_argument('--ban-towns', type=str, default='', help='Comma-separated Town names to skip (e.g. Town03)')
    parser.add_argument('--base-url', type=str, default=None, help='Override base_url (default: STRATA_BASE_URL env or http://127.0.0.1:8080/v1)')
    parser.add_argument('--api-key', type=str, default=None, help='Override api_key (default: STRATA_API_KEY env or none)')
    parser.add_argument('--enable-thinking', action='store_true', help='Enable reasoning (thinking) for qwen model')
    parser.add_argument('--use_llm', action='store_true', help='if use llm for generating new snippets')
    return parser.parse_args(argv)


def main(args=None):
    if args is None:
        args = parse_args()
    port_ip = args.port_ip
    topk = args.topk
    use_llm = args.use_llm
    verify = args.verify
    ban_towns = [t.strip() for t in args.ban_towns.split(',') if t.strip()] if args.ban_towns else []
    fallback_models = [m.strip() for m in args.fallback_models.split(',') if m.strip()] if args.fallback_models else []

    llm_model = LLMChat(
        args.model,
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        enable_thinking=args.enable_thinking,
        fallback_models=fallback_models,
    )
    local_path = osp.abspath(osp.dirname(osp.dirname(osp.realpath(__file__))))
    extraction_prompt = load_file(osp.join(local_path, 'retrieve', 'prompts', 'extraction.txt'))
    behavior_prompt = load_file(osp.join(local_path, 'retrieve', 'prompts', 'behavior.txt'))
    geometry_prompt = load_file(osp.join(local_path, 'retrieve', 'prompts', 'geometry.txt'))
    spawn_prompt = load_file(osp.join(local_path, 'retrieve', 'prompts', 'spawn.txt'))
    scenario_descriptions_raw = load_file(osp.join(local_path, 'retrieve', 'scenario_descriptions.txt'))
    scenario_descriptions = [s for s in scenario_descriptions_raw.split('\n') if s.strip()]

    device = os.environ.get("RETRIEVE_DEVICE", "cuda")
    if device == "cpu":
        encoder = SentenceTransformer('sentence-transformers/sentence-t5-large', device='cpu')
        encode_kwargs = {"device": "cpu", "convert_to_tensor": True}
    else:
        try:
            encoder = SentenceTransformer('sentence-transformers/sentence-t5-large', device='cuda')
            encode_kwargs = {"device": "cuda", "convert_to_tensor": True}
        except Exception:
            encoder = SentenceTransformer('sentence-transformers/sentence-t5-large', device='cpu')
            encode_kwargs = {"device": "cpu", "convert_to_tensor": True}

    with open(osp.join(local_path, 'retrieve/database_v1.pkl'), 'rb') as file:
        database = pickle.load(file)
    behavior_descriptions = database['behavior']['description']
    geometry_descriptions = database['geometry']['description']
    spawn_descriptions = database['spawn']['description']
    behavior_snippets = database['behavior']['snippet']
    geometry_snippets = database['geometry']['snippet']
    spawn_snippets = database['spawn']['snippet']

    def _safe_encode(descs):
        try:
            return encoder.encode(descs, **encode_kwargs)
        except Exception:
            cpu_kwargs = {"device": "cpu", "convert_to_tensor": True}
            try:
                enc_cpu = SentenceTransformer('sentence-transformers/sentence-t5-large', device='cpu')
                return enc_cpu.encode(descs, **cpu_kwargs)
            except Exception:
                return encoder.encode(descs, **cpu_kwargs)

    behavior_embeddings = _safe_encode(behavior_descriptions)
    geometry_embeddings = _safe_encode(geometry_descriptions)
    spawn_embeddings = _safe_encode(spawn_descriptions)

    head = '''param map = localPath(f'../maps/{Town}.xodr') 
param carla_map = Town
model scenic.simulators.carla.model
EGO_MODEL = "vehicle.lincoln.mkz_2017"
'''

    os.makedirs(osp.join(local_path, 'safebench', 'scenario', 'scenario_data', 'scenic_data', 'dynamic_scenario'), exist_ok=True)
    log_file_path = osp.join(local_path, 'safebench', 'scenario', 'scenario_data', 'scenic_data', 'dynamic_scenario', 'dynamic_log.csv')
    with open(log_file_path, mode='w', newline='') as file:
        log_writer = csv.writer(file)
        log_writer.writerow(['Scenario', 'AdvObject', 'Behavior Description', 'Behavior Snippet', 'Geometry Description', 'Geometry Snippet', 'Spawn Description', 'Spawn Snippet', 'Success'])

        for q, current_scenario in tqdm(enumerate(scenario_descriptions)):
            try:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": extraction_prompt.format(scenario=current_scenario)},
                ]
                response = llm_model.generate(messages)
                if not response or not isinstance(response, str):
                    raise ValueError("empty extraction response")
                match = re.search(r"Adversarial Object:(.*?)Behavior:(.*?)Geometry:(.*?)Spawn Position:(.*)", response, re.DOTALL)
                if not match:
                    raise ValueError(f"extraction regex failed for response: {response[:500]!r}")
                current_adv_object, current_behavior, current_geometry, current_spawn = [s.strip() for s in match.groups()]

                def _gen_with_fallback(category_prompt, descs, snips, cur_desc):
                    try:
                        return generate_code_snippet(llm_model, category_prompt, descs, snips, cur_desc, topk, use_llm)
                    except Exception as e:
                        if not fallback_models:
                            raise
                        last_e = e
                        for fb in fallback_models:
                            try:
                                fb_model = LLMChat(fb, provider=args.provider, base_url=args.base_url, api_key=args.api_key, enable_thinking=args.enable_thinking)
                                return generate_code_snippet(fb_model, category_prompt, descs, snips, cur_desc, topk, use_llm)
                            except Exception as e2:
                                last_e = e2
                                continue
                        raise last_e

                top_behavior_descriptions, top_behavior_snippets = retrieve_topk(encoder, topk, behavior_descriptions, behavior_snippets, behavior_embeddings, current_behavior)
                top_geometry_descriptions, top_geometry_snippets = retrieve_topk(encoder, topk, geometry_descriptions, geometry_snippets, geometry_embeddings, current_geometry)
                top_spawn_descriptions, top_spawn_snippets = retrieve_topk(encoder, topk, spawn_descriptions, spawn_snippets, spawn_embeddings, current_spawn)

                generated_behavior_code = _gen_with_fallback(behavior_prompt, top_behavior_descriptions, top_behavior_snippets, current_behavior)
                generated_geometry_code = _gen_with_fallback(geometry_prompt, top_geometry_descriptions, top_geometry_snippets, current_geometry)
                generated_spawn_code = _gen_with_fallback(spawn_prompt, top_spawn_descriptions, top_spawn_snippets, current_spawn)

                log_writer.writerow([current_scenario, current_adv_object, current_behavior, generated_behavior_code, current_geometry, generated_geometry_code, current_spawn, generated_spawn_code, 1])

                Town, generated_geometry_code_tail = generated_geometry_code.split('\n', 1)
                town_name = Town.strip().split('=')[-1].strip().strip("'\"") if '=' in Town else Town.strip()
                if ban_towns and town_name in ban_towns:
                    print(f"Skipping {q} banned town {town_name}")
                    log_writer.writerow([current_scenario, current_adv_object, current_behavior, generated_behavior_code, current_geometry, generated_geometry_code, current_spawn, generated_spawn_code, 0])
                    continue
                scenic_code = '\n'.join([f"'''{current_scenario}'''", Town, head, generated_behavior_code, generated_geometry_code_tail, generated_spawn_code.format(AdvObject=current_adv_object)])
                save_scenic_code(local_path, port_ip, scenic_code, q, verify=verify)
            except Exception as e:
                print(f"Failure for scenario {q}: {current_scenario[:80]}: {e}")
                try:
                    log_writer.writerow([current_scenario, '', '', '', '', '', '', '', 0])
                except Exception:
                    pass
                continue
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
