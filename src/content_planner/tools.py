"""Local planning actions. Callers choose every action explicitly."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib

from pydantic import ValidationError

from .catalog import Catalog
from .contracts import Request, RevisionArgs, RevisePlanArgs, ScriptDraft, SearchMaterialsArgs
from .domain import AUDIENCE, PLATFORM, Clock, Fault, candidate_hash, parse_script, quote, require_complete, script_input_hash
from .model import ModelClient, ModelUnavailable


@dataclass(frozen=True)
class _QuoteClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


class LocalTools:
    def __init__(self, request: Request, catalog: Catalog, model: ModelClient, clock: Clock):
        self._request = require_complete(request, clock)
        self._catalog = deepcopy(catalog)
        self._model = model
        self._clock = clock
        self._state = {
            'request': request.model_dump(mode='json'),
            'manifest': {'schema_version': '1.0', 'catalog_sha256': catalog.catalog_hash,
                         'pricing_sha256': catalog.pricing_hash, 'aliases_sha256': catalog.aliases_hash,
                         'planner_prompt_version': 'planner-v1', 'script_prompt_version': 'script-v1',
                         'model_id': model.model_id, 'thinking': 'disabled'},
            'seen_material_ids': [], 'tool_results': [], 'last_observation': None,
            'candidate_history': {}, 'current_revision': None, 'script_artifacts': {},
            'estimate_history': {}, 'current_estimate_id': None, 'status': 'running', 'reason': None,
        }

    def snapshot(self) -> dict:
        return deepcopy(self._state)

    def _record(self, tool, call_id, data=None, error=None, reused=False):
        result = {'tool_call_id': call_id, 'tool': tool, 'ok': error is None,
                  'reused': reused, 'data': data, 'error': error}
        self._state['tool_results'].append(result)
        self._state['last_observation'] = result
        return deepcopy(result)

    def search_materials(self, tool_call_id: str, arguments: dict) -> dict:
        return self._invoke('search_materials', tool_call_id, arguments, SearchMaterialsArgs, self._search)

    def revise_plan(self, tool_call_id: str, arguments: dict) -> dict:
        return self._invoke('revise_plan', tool_call_id, arguments, RevisePlanArgs, self._revise)

    def generate_script(self, tool_call_id: str, arguments: dict) -> dict:
        return self._invoke('generate_script', tool_call_id, arguments, RevisionArgs, self._generate)

    def estimate_cost(self, tool_call_id: str, arguments: dict) -> dict:
        return self._invoke('estimate_cost', tool_call_id, arguments, RevisionArgs, self._estimate)

    def _invoke(self, tool, call_id, arguments, argument_type, operation):
        if self._state['status'] == 'incomplete':
            return self._failure(tool, call_id, Fault(self._state['reason'], 'Task has reached its revision limit'))
        try:
            args = argument_type.model_validate(arguments)
        except ValidationError:
            return self._failure(tool, call_id, Fault('INVALID_ARGUMENT', 'Invalid tool arguments'))
        try:
            data, reused = operation(args, call_id)
        except Fault as error:
            return self._failure(tool, call_id, error)
        return self._record(tool, call_id, data, reused=reused)

    def _failure(self, tool, call_id, fault):
        retryable = fault.code in {'CATALOG_UNAVAILABLE', 'SCRIPT_MODEL_UNAVAILABLE', 'ESTIMATOR_UNAVAILABLE'}
        return self._record(tool, call_id, error={'code': fault.code, 'message': fault.message,
                                                'retryable': retryable, 'details': fault.details})

    def _search(self, args, call_id):
        materials = self._catalog.search(args.query, args.top_k)
        self._state['seen_material_ids'] = sorted(set(self._state['seen_material_ids']) |
                                                 {item['material_id'] for item in materials})
        return {'query': args.query, 'catalog_hash': self._catalog.catalog_hash, 'materials': materials}, False

    def _material(self, material_id):
        for material in self._catalog.materials:
            if material.material_id == material_id:
                return material.model_dump(mode='json')
        raise Fault('MATERIAL_NOT_FOUND', 'Material does not exist')

    def _revise(self, args, call_id):
        material = self._material(args.material_id)
        if args.material_id not in self._state['seen_material_ids']:
            raise Fault('MATERIAL_NOT_OBSERVED', 'Material must be retrieved before selection')
        digest = candidate_hash(self._request, material, args.creative_brief, args.production_mode,
                                self._catalog.pricing_hash)
        script_digest = script_input_hash(self._request, material, args.creative_brief,
                                          model_id=self._model.model_id, script_prompt_version='script-v1')
        revision = self._state['current_revision']
        current = self._state['candidate_history'].get(str(revision))
        reused = current is not None and current['candidate_hash'] == digest
        script_reused = script_digest in self._state['script_artifacts']
        invalidated = []
        if not reused:
            revision = (revision or 0) + 1
            if revision > 4:
                self._state.update(status='incomplete', reason='REVISION_LIMIT_REACHED')
                raise Fault('REVISION_LIMIT_REACHED', 'At most four candidate revisions are allowed')
            candidate = {'revision': revision, 'candidate_hash': digest, 'material_id': args.material_id,
                         'creative_brief': args.creative_brief, 'production_mode': args.production_mode,
                         'script_input_hash': script_digest}
            if current and current['script_input_hash'] != script_digest and current['script_input_hash'] in self._state['script_artifacts']:
                invalidated.append('script')
            if self._state['current_estimate_id'] is not None:
                invalidated.append('estimate')
            self._state['candidate_history'][str(revision)] = candidate
            self._state['current_revision'] = revision
            self._state['current_estimate_id'] = None
            current = candidate
        return {**current, 'script_reused': script_reused, 'invalidated': invalidated}, reused

    def _current_candidate(self, revision):
        if self._state['current_revision'] is None:
            raise Fault('PRECONDITION_FAILED', 'A candidate must be selected first')
        if revision != self._state['current_revision']:
            raise Fault('STALE_REVISION', 'Action must use the current revision')
        return self._state['candidate_history'][str(revision)]

    def _generate(self, args, call_id):
        candidate = self._current_candidate(args.plan_revision)
        digest = candidate['script_input_hash']
        if digest in self._state['script_artifacts']:
            return self._state['script_artifacts'][digest], True
        material = self._material(candidate['material_id'])
        context = {'topic': self._request.topic,
                   'material': {'material_id': material['material_id'], 'facts': material['facts']},
                   'creative_brief': candidate['creative_brief'], 'audience': AUDIENCE, 'platform': PLATFORM,
                   'output_schema': ScriptDraft.model_json_schema()}
        try:
            raw = self._model.generate_script(context)
        except ModelUnavailable as error:
            raise Fault('SCRIPT_MODEL_UNAVAILABLE', 'Script model is unavailable') from error
        draft = parse_script(raw, material)
        artifact = {'script_id': 'script_' + digest, 'script_input_hash': digest, **draft.model_dump(mode='json')}
        self._state['script_artifacts'][digest] = artifact
        return artifact, False

    def _estimate(self, args, call_id):
        candidate = self._current_candidate(args.plan_revision)
        script = self._state['script_artifacts'].get(candidate['script_input_hash'])
        if script is None:
            raise Fault('PRECONDITION_FAILED', 'A matching script is required before estimation')
        material = self._material(candidate['material_id'])
        pricing = self._catalog.pricing.model_dump(mode='json')
        mode = candidate['production_mode']
        try:
            clock = _QuoteClock(self._clock.now())
        except OSError as error:
            raise Fault('ESTIMATOR_UNAVAILABLE', 'Estimator clock is unavailable') from error
        value = quote(self._request, material, pricing, mode, clock)
        other = 'basic' if mode == 'premium' else 'premium'
        alternative = quote(self._request, material, pricing, other, clock)
        alternative = {key: value for key, value in alternative.items() if key not in {'line_items', 'quoted_at'}}
        alternative['production_mode'] = other
        estimate_id = 'estimate_' + hashlib.sha256(call_id.encode('utf-8')).hexdigest()
        estimate = {'estimate_id': estimate_id, 'revision': candidate['revision'],
                    'candidate_hash': candidate['candidate_hash'], 'script_id': script['script_id'],
                    'pricing_hash': self._catalog.pricing_hash, **value, 'alternatives': [alternative]}
        self._state['estimate_history'][estimate_id] = estimate
        self._state['current_estimate_id'] = estimate_id
        return estimate, False
