"""Bounded local inference with validated completion and diagnostic timing."""
import json
import math
import time
import urllib.error


class InferenceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def failure_code(exc):
    if isinstance(exc, InferenceError):
        return exc.code
    if isinstance(exc, TimeoutError) or isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError):
        return 'timeout'
    if isinstance(exc, urllib.error.HTTPError):
        return 'model_unavailable' if exc.code == 404 else 'http_error'
    if isinstance(exc, (ConnectionError, urllib.error.URLError)):
        return 'unavailable'
    return 'invalid_response' if isinstance(exc, (ValueError, TypeError, KeyError)) else 'transport_error'


def timing(reply):
    result = {}
    for source, target in (('load_duration','load_s'), ('prompt_eval_duration','prompt_s'),
                           ('eval_duration','generation_s'), ('total_duration','server_s')):
        value = reply.get(source)
        if isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value) and value >= 0:
            result[target] = round(value / 1e9, 3)
    for source,target in (('eval_count','output_tokens'),('prompt_eval_count','input_tokens')):
        value = reply.get(source)
        if isinstance(value,int) and not isinstance(value,bool) and value >= 0:
            result[target] = value
    return result


def evidence_budget(policy, max_tokens):
    # Qwen's byte-level vocabulary: reserve worst-case UTF-8 bytes for policy,
    # then generated tokens and chat-template overhead inside the 8192 window.
    available = 8192 - len(policy.encode('utf-8')) - max_tokens - 512
    if available < 2048:
        raise InferenceError('context_budget', 'monitor policy leaves insufficient context for evidence')
    return min(6000,available)


def request(transport, url, model, policy, observations, schema, timeout, max_tokens, diagnostics=None):
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.update(request_attempts=0,retry_errors=[])
    deadline = time.monotonic() + timeout
    if not policy.strip():
        raise InferenceError('empty_policy', 'monitor policy is empty')
    if len(observations.encode('utf-8')) > evidence_budget(policy,max_tokens):
        raise InferenceError('context_budget', 'observations exceed the reserved context budget')
    payload = {'model':model, 'stream':False, 'think':False, 'keep_alive':'10m', 'format':schema,
               'options':{'temperature':0, 'num_predict':max_tokens, 'num_ctx':8192},
               'messages':[{'role':'system','content':policy}, {'role':'user','content':observations}]}
    retry_error = None
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('inference request budget exhausted')
        diagnostics['request_attempts'] += 1
        if retry_error is not None:
            diagnostics['retry_errors'].append(retry_error)
        started = time.monotonic()
        try:
            reply = transport(f'{url}/api/chat', payload, remaining)
            break
        except urllib.error.HTTPError as exc:
            # Assessment requests execute no agent tools. Retry only temporary
            # server failures once, with backoff charged to the same deadline.
            if attempt or exc.code not in (500,502,503,504) or deadline-time.monotonic() <= .25:
                raise
            retry_error = {'error_code':'http_error','http_status':exc.code,
                'elapsed_s':round(time.monotonic()-started,3)}
            exc.close()
            time.sleep(.25)
    if time.monotonic() > deadline:
        raise TimeoutError('inference request budget exhausted')
    if not isinstance(reply,dict):
        raise InferenceError('invalid_response', 'Ollama returned a non-object response')
    if reply.get('done_reason') == 'length':
        raise InferenceError('truncated', 'generation limit reached; assessment was not completed')
    if reply.get('done') is not True or reply.get('done_reason') != 'stop':
        raise InferenceError('incomplete_response', 'Ollama response was not completed')
    try:
        text = reply['message']['content']
        data = json.loads(text)
        if not isinstance(data,dict) or not all(k in data for k in schema['required']):
            raise ValueError('missing assessment fields')
        for key, spec in schema['properties'].items():
            if key not in data:
                continue
            value = data[key]
            kind = spec['type']
            if kind in ('number','integer'):
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
                    raise ValueError(f'{key} must be a finite number')
                if kind == 'integer' and value != int(value):
                    raise ValueError(f'{key} must be an integer')
                if value < spec.get('minimum',-math.inf) or value > spec.get('maximum',math.inf):
                    raise ValueError(f'{key} is outside its allowed range')
            elif kind == 'string' and not isinstance(value,str):
                raise ValueError(f'{key} must be text')
            elif kind == 'array' and (not isinstance(value,list) or not all(isinstance(x,str) for x in value)):
                raise ValueError(f'{key} must be a list of evidence strings')
            if 'enum' in spec and value not in spec['enum']:
                raise ValueError(f'{key} is not an allowed value')
        if not data['reason'].strip():
            raise ValueError('assessment reason is empty')
    except (KeyError,ValueError,TypeError) as exc:
        raise InferenceError('invalid_response', f'unusable assessment: {exc}') from exc
    return text, timing(reply)
