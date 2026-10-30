import json
from pathlib import Path

from content_planner.contracts import RevisionArgs, RevisePlanArgs, SavePlanArgs, SearchMaterialsArgs


ROOT = Path(__file__).resolve().parents[2]


def semantics(value):
    if isinstance(value, dict):
        result = {key: ({name: semantics(prop) for name, prop in item.items()}
                        if key == 'properties' else semantics(item))
                  for key, item in value.items() if key not in {'title', 'description', 'default'}}
        if 'enum' in result:
            result.pop('type', None)  # A string enum already restricts the type.
        if 'required' in result:
            result['required'] = sorted(result['required'])
        return result
    if isinstance(value, list):
        return [semantics(item) for item in value]
    return value


def test_local_argument_schemas_match_five_published_tool_contracts():
    tools = json.loads((ROOT / 'contracts/tools.json').read_text(encoding='utf-8'))
    arguments = {'search_materials': SearchMaterialsArgs, 'revise_plan': RevisePlanArgs,
                 'generate_script': RevisionArgs, 'estimate_cost': RevisionArgs, 'save_plan': SavePlanArgs}
    for tool in tools[:5]:
        function = tool['function']
        assert semantics(arguments[function['name']].model_json_schema()) == semantics(function['parameters'])
