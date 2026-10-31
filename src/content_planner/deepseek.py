"""Thin official DeepSeek Chat Completions adapter."""

import json
import os

import httpx

from .domain import Fault
from .model import ModelUnavailable
from .prompts import SCRIPT


class DeepSeekModelClient:
    model_id = 'deepseek-v4-pro'

    def __init__(self, client=None):
        key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        base = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com').strip().rstrip('/')
        model = os.environ.get('DEEPSEEK_MODEL', self.model_id).strip()
        if not key or base != 'https://api.deepseek.com' or model != self.model_id:
            raise Fault('CONFIG_ERROR', 'Configure the official DeepSeek API key, base URL and deepseek-v4-pro model',
                        {'backend': 'deepseek'})
        self._key = key
        self._owned = client is None
        self._client = client or httpx.Client(timeout=httpx.Timeout(connect=5, read=45, write=10, pool=5),
                                               follow_redirects=False)
        self.last_usage = None
        self.http_attempts = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self._owned:
            self._client.close()

    def _complete(self, messages, max_tokens, **options):
        self.last_usage = None
        self.http_attempts += 1
        try:
            response = self._client.post('https://api.deepseek.com/chat/completions',
                headers={'Authorization': 'Bearer ' + self._key}, follow_redirects=False,
                timeout=httpx.Timeout(connect=5, read=45, write=10, pool=5),
                json={'model': self.model_id, 'messages': messages, 'temperature': 0,
                      'max_tokens': max_tokens, 'stream': False, 'thinking': {'type': 'disabled'}, **options})
        except httpx.RequestError:
            raise ModelUnavailable('DeepSeek connection or timeout failure') from None
        if response.status_code != 200:
            status = response.status_code
            code = 'AUTH_ERROR' if status in (401, 403) else (
                'MODEL_UNAVAILABLE' if status == 429 or status >= 500 else 'MODEL_CONFIG_ERROR')
            raise ModelUnavailable(f'DeepSeek request failed (HTTP {status})', code=code,
                                   retryable=code == 'MODEL_UNAVAILABLE')
        try:
            body = response.json()
        except ValueError:
            raise self._protocol_error() from None
        if not isinstance(body, dict):
            raise self._protocol_error()
        usage = body.get('usage')
        self.last_usage = {target: usage.get(source) if isinstance(usage, dict)
                           and type(usage.get(source)) is int and usage[source] >= 0 else None
                           for target, source in (('input_tokens', 'prompt_tokens'), ('output_tokens', 'completion_tokens'))}
        choices = body.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise self._protocol_error()
        reason = choices[0].get('finish_reason')
        if reason in {'insufficient_system_resource', 'aborted'}:
            raise ModelUnavailable('DeepSeek generation interrupted', usage=self.last_usage)
        if reason not in {'stop', 'tool_calls'}:
            raise self._protocol_error()
        message = choices[0].get('message')
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            raise self._protocol_error()
        return {key: value for key, value in message.items() if key in {'role', 'content', 'tool_calls'}}

    def _protocol_error(self):
        return ModelUnavailable('Invalid or incomplete DeepSeek response', code='MODEL_PROTOCOL_ERROR',
                                retryable=False, usage=self.last_usage)

    def decide(self, context):
        facts = {key: context[key] for key in ('memory', 'history_summary', 'limits')}
        messages = [{'role': 'system', 'content': context['system']},
                    {'role': 'user', 'content': json.dumps(facts, ensure_ascii=False)}, *context['messages']]
        return self._complete(messages, 2048, tools=context['tools'], tool_choice='auto')

    def generate_script(self, context):
        message = self._complete([{'role': 'system', 'content': SCRIPT},
            {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}], 1536,
            response_format={'type': 'json_object'})
        if not isinstance(message.get('content'), str) or not message['content'].strip():
            raise self._protocol_error()
        return message['content']
