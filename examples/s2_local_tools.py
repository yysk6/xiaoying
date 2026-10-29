"""Explicit offline S2 calls, with a fixed fixture clock; this is not an Agent run."""

from datetime import datetime, timezone
import json

from content_planner.catalog import load_catalog
from content_planner.contracts import Request
from content_planner.model import FakeModelClient
from content_planner.tools import LocalTools


class FixtureClock:
    def now(self):
        return datetime(2026, 10, 29, 2, tzinfo=timezone.utc)


def main():
    request = Request(request_id='s2-demo', topic='字幕功能推广', budget_units=10,
                      deadline_at='2026-10-29T13:00:00+08:00')
    draft = {'title': '字幕编辑演示', 'hook': '试试自动字幕', 'body': '自动生成的字幕文本可以编辑。',
             'cta': '体验字幕编辑', 'source_ids': ['M01']}
    model = FakeModelClient([json.dumps(draft, ensure_ascii=False)])
    tools = LocalTools(request, load_catalog(), model, FixtureClock())
    tools.search_materials('search-empty', {'query': '不存在的功能', 'top_k': 5, 'rationale': '尝试检索'})
    tools.search_materials('search-caption', {'query': 'caption', 'top_k': 5, 'rationale': '改写检索词'})
    tools.revise_plan('revise-premium', {'material_id': 'M01', 'creative_brief': '演示字幕编辑',
                                       'production_mode': 'premium', 'rationale': '建立候选'})
    tools.generate_script('generate-first', {'plan_revision': 1, 'rationale': '生成草稿'})
    tools.estimate_cost('estimate-premium', {'plan_revision': 1, 'rationale': '核对约束'})
    tools.revise_plan('revise-basic', {'material_id': 'M01', 'creative_brief': '演示字幕编辑',
                                     'production_mode': 'basic', 'rationale': '显式选择替代档位'})
    tools.generate_script('generate-reuse', {'plan_revision': 2, 'rationale': '复用匹配草稿'})
    tools.estimate_cost('estimate-basic', {'plan_revision': 2, 'rationale': '重新核对约束'})
    print(json.dumps({'kind': 'explicit_local_tool_demo', 'clock_source': 'fixed_fixture',
                      'fake_generation_calls': len(model.requests), 'live_model_calls': 0,
                      'snapshot': tools.snapshot()}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
