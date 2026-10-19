# Strata Verification — qwen3.8-flash-next

Date: 2026-10-16

## 1. Strata health
```
$ curl http://127.0.0.1:8080/health
{"status":"ok","max_context":65536,"model":"qwen3.8-flash-next-iq3_s","images":false,"api_key":false,"loaded":true,"service":"strata"}

$ curl http://127.0.0.1:8080/v1/models | grep qwen
{"id":"qwen3.8-flash-next-iq3_s","object":"model","status":{"value":"loaded"}}
```

## 2. OpenAI-compatible client (strata)
```
$ python -c "from retrieve.architecture import LLMChat; c=LLMChat('qwen3.8-flash-next-iq3_s',provider='strata'); print(c.client.base_url)"
http://127.0.0.1:8080/v1/

$ python -c "from retrieve.architecture import LLMChat; c=LLMChat('qwen3.8-flash-next-iq3_s',provider='strata'); print(c.generate([{'role':'user','content':'Say hello'}],max_new_tokens=10))"
Hello! How can I help you today?
```

Extraction prompt via qwen:
```
Adversarial Object: Pedestrian
Behavior: The adversarial pedestrian suddenly crosses from the right and stops abruptly as the ego vehicle approaches.
Geometry: A straight road.
Spawn Position: The adversarial agent is on the right front of the ego vehicle, crossing the road.
```

## 3. Scenic snippet generation via qwen
```
behavior AdvBehavior():
    do CrossingBehavior(ego, globalParameters.OPT_ADV_SPEED, globalParameters.OPT_ADV_DISTANCE) until (distance from self to egoTrajectory) < globalParameters.OPT_STOP_DISTANCE
    while True:
        take SetWalkingSpeedAction(0)

param OPT_ADV_SPEED = Range(0, 5)
...
```

## 4. CLI parity
```
$ python retrieve/retrieve.py --help | grep provider
  --provider {strata,openai,local,auto}

$ python retrieve/retrieve_dynamic.py --help | grep provider
  --provider {strata,openai,local,auto}

$ python retrieve/retrieve_dynamic.py --model qwen3.8-flash-next-iq3_s --provider strata --fallback-models "" --verify parse --ban-towns "" --help
# exits 0, flags match AGENTS.md command
```

## 5. E2E generation (1 scenario, verify parse)
```
$ RETRIEVE_DEVICE=cpu CUDA_VISIBLE_DEVICES="" python retrieve/retrieve_dynamic.py --model qwen3.8-flash-next-iq3_s --provider strata --fallback-models "" --verify parse --ban-towns "" --topk 1 --use_llm
Scenic code parse OK (heuristic) at .../dynamic_0.scenic

$ cat dynamic_0.scenic | head -20
'''The ego vehicle is driving on a straight road ...'''
Town = 'Town05'
param map = localPath(f'../maps/{Town}.xodr')
...
behavior AdvBehavior():
...
AdvAgent = Pedestrian ...

$ grep -R "sk-proj" --include="*.py" .  # -> no matches
$ grep -n "pdb" retrieve/utils.py      # -> no matches
```

## 6. Edge cases
- ban-towns "Town05" correctly skips generation (no file created, log Success 0)
- verify none saves without check, verify parse uses heuristic (scenic DSL not python compile)
- fallback handling via generate_code_snippet retry returns snippet[0] if LLM fails
- CPU fallback for RTX 5080 sm_120 incompatibility (RETRIEVE_DEVICE=cpu)

## 7. Regression
- provider openai still constructs https://api.openai.com/v1 client with OPENAI_API_KEY
- auto provider maps gpt* -> openai, qwen* -> strata
- original 40 scenario_descriptions.txt intact
