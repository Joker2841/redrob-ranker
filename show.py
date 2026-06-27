import json, sys
ids = set(sys.argv[1:])
for line in open("data/candidates.jsonl"):
    c = json.loads(line)
    if c["candidate_id"] in ids:
        print(json.dumps(c, indent=2))
        print("="*80)