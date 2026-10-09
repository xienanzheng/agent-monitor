"""Serialize bounded redacted observations separately from trusted monitor policy."""
import json
from monitor.categories import CATEGORIES
from monitor.redact import redact


def grounded_policy(policy, schema):
    """Show the enforced response contract to the model, inside trusted policy."""
    if not policy.strip():
        return policy
    return policy+'\nResponse JSON Schema (trusted contract):\n'+json.dumps(schema,separators=(',',':'))


def evidence(action, context, rule_hits=(), tags=(), rule_score=None, rule_reasons=(), max_bytes=6000):
    truncated = False
    def limited(value, budget):
        nonlocal truncated
        text = redact(str(value or ''))
        # Budget serialized UTF-8 bytes, including escapes. Preserve both ends of commands.
        if len(json.dumps(text,ensure_ascii=False).encode('utf-8')) > budget:
            truncated = True
            size = min(len(text)//2, budget//2-25)
            while True:
                short = text[:size]+'\n[... evidence truncated ...]\n'+text[-size:]
                if len(json.dumps(short,ensure_ascii=False).encode('utf-8')) <= budget or size < 2:
                    return short
                size = max(1,size//2)
        return text
    def observed(a, recent=False):
        return {'kind':limited(a.kind,100), 'tool':limited(a.tool,200),
                'text':limited(a.text,800 if recent else 2500),
                'output':limited(a.output,600 if recent else 1500),
                'cwd':limited(a.cwd,200 if recent else 300),
                'path':limited(a.path,200 if recent else 300), 'outcome':limited(a.outcome,100)}
    data = {'user_task':limited(action.task,1500) or '(unknown)',
            'recent_actions':[observed(c,True) for c in context[-5:]], 'action':observed(action),
            'rule_hits':[limited(x,100) for x in list(rule_hits)[:32]],
            'tags':[limited(x,100) for x in sorted(tags)[:32]]}
    if len(rule_hits)>32 or len(tags)>32:
        truncated = True
    if rule_score is not None:
        data['rule_score'] = rule_score
        data['rule_reasons'] = [limited(x,200) for x in list(rule_reasons)[:8]]
        truncated |= len(rule_reasons)>8
    data['evidence_limits'] = {'recent_action_window':5, 'truncated':truncated}
    encoded = json.dumps(data,ensure_ascii=False)
    # Preserve the current request and all five recent actions whenever they fit.
    while len(encoded.encode('utf-8'))>max_bytes:
        previous = encoded
        for row in data['recent_actions']:
            for key in row:
                row[key] = limited(row[key], max(60,len(json.dumps(row[key],ensure_ascii=False).encode('utf-8'))//2))
        data['evidence_limits']['truncated'] = True
        encoded = json.dumps(data,ensure_ascii=False)
        if encoded != previous:
            continue
        for key in data['action']:
            value=data['action'][key]
            data['action'][key]=limited(value,max(60,len(json.dumps(value,ensure_ascii=False).encode('utf-8'))//2))
        data['user_task']=limited(data['user_task'],max(60,len(json.dumps(data['user_task'],ensure_ascii=False).encode('utf-8'))//2))
        for key in ('rule_hits','tags','rule_reasons'):
            if key in data:
                data[key]=[limited(v,max(60,len(json.dumps(v,ensure_ascii=False).encode('utf-8'))//2)) for v in data[key]]
        encoded=json.dumps(data,ensure_ascii=False)
        if encoded==previous:
            for key in ('rule_hits','tags','rule_reasons'):
                if key in data and len(data[key])>1:
                    data[key]=data[key][:max(1,len(data[key])//2)]
            if data['recent_actions']:
                data['recent_actions']=data['recent_actions'][1:]
            encoded=json.dumps(data,ensure_ascii=False)
            if encoded==previous:
                raise ValueError('evidence budget is too small for observation metadata')
    return encoded


# Emit evidence before the score, with no canned verdict to anchor the judge.
BASE_SCHEMA = {'type':'object', 'properties':{
    'reason':{'type':'string'}, 'score':{'type':'integer','enum':list(range(11))}},
    'required':['reason','score'], 'additionalProperties':False}
TRIAGE_SCHEMA = {'type':'object', 'properties':{
    'reason':{'type':'string'}, 'category':{'type':'string','enum':list(CATEGORIES)},
    'authorization':{'type':'string','enum':['explicit','implied','unclear','out_of_scope','forbidden']},
    'confidence':{'type':'number','minimum':0,'maximum':1}, 'score':BASE_SCHEMA['properties']['score']},
    'required':['reason','category','authorization','confidence','score'], 'additionalProperties':False}
VERDICT_SCHEMA = {'type':'object', 'properties':{
    'reason':{'type':'string'}, 'category':TRIAGE_SCHEMA['properties']['category'],
    'authorization':TRIAGE_SCHEMA['properties']['authorization'],
    'boundary':{'type':'string'}, 'recoverability':{'type':'string','enum':['high','medium','low']},
    'confidence':TRIAGE_SCHEMA['properties']['confidence'], 'score':BASE_SCHEMA['properties']['score']},
    'required':['reason','category','authorization','confidence','score','boundary','recoverability'],
    'additionalProperties':False}
