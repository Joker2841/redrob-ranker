import json, statistics as st
from compare import best_relevant_assessment
gh, pairs = [], []
for line in open('data/candidates.jsonl'):
    c = json.loads(line)
    g = (c.get('redrob_signals', {}) or {}).get('github_activity_score')
    if g is not None:
        gh.append(g)
        a = best_relevant_assessment(c)
        if a is not None: pairs.append((g, a))
print('github mean/stdev/min/max:', round(st.mean(gh),1), round(st.pstdev(gh),1), min(gh), max(gh))
xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
mx, my = st.mean(xs), st.mean(ys)
corr = (sum((x-mx)*(y-my) for x,y in pairs)/len(pairs)) / (st.pstdev(xs)*st.pstdev(ys))
print(f'corr(github, assessment) over {len(pairs)} = {corr:.3f}')