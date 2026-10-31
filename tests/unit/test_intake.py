from datetime import datetime, timezone

import pytest
import json

from content_planner.model import ModelUnavailable


NOW = datetime(2026, 10, 31, 2, tzinfo=timezone.utc)


@pytest.mark.parametrize('text,expected', [
    ('明天下午六点前', '2026-11-01T10:00:00+00:00'),
    ('后天上午九点半', '2026-11-02T01:30:00+00:00'),
    ('2026-11-01 18:30', '2026-11-01T10:30:00+00:00'),
    ('2026年11月1日下午6点', '2026-11-01T10:00:00+00:00'),
    ('2026-11-01T18:00:00+08:00', '2026-11-01T10:00:00+00:00'),
])
def test_deadline_normalization_uses_the_explicit_anchor_and_local_timezone(text, expected):
    from content_planner.intake import resolve_deadline
    assert resolve_deadline(text, NOW) == expected


@pytest.mark.parametrize('text', ['尽快', '明天', '周五六点', '明天晚上十二点', '明天下午十三点',
                                 '2026年2月30日18:00', '2026-11-01T18:00:00+08:60'])
def test_ambiguous_or_invalid_deadline_is_not_guessed(text):
    from content_planner.intake import resolve_deadline
    with pytest.raises(ValueError):
        resolve_deadline(text, NOW)


class Clock:
    instant = NOW

    def now(self):
        return self.instant


class Extractor:
    last_usage = {'input_tokens': 10, 'output_tokens': 5}

    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []

    def extract_intake(self, context):
        self.requests.append(context)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response, ensure_ascii=False)


def update(value):
    return {'value': value, 'source': value}


def test_multiturn_collection_and_confirmation_return_one_stable_request():
    from content_planner.intake import IntakeSession
    extractor = Extractor({'topic': update('字幕推广')},
                          {'budget_units': update('预算10'), 'deadline_at': update('明天下午六点')})
    session = IntakeSession(extractor, Clock())
    first = session.receive('字幕推广')
    assert first['state'] == 'collecting' and first['request'] is None
    assert '预算' in first['message'] and '时间' in first['message']
    ready = session.receive('预算10，明天下午六点')
    assert ready['state'] == 'ready' and ready['request'] is None
    confirmed = session.receive('确认')
    assert confirmed['request']['budget_units'] == 10
    assert confirmed['request']['deadline_at'] == '2026-11-01T10:00:00+00:00'
    assert session.receive('确认')['request'] == confirmed['request']
    assert len(extractor.requests) == 2


def complete_patch():
    return {'topic': update('字幕推广'), 'budget_units': update('预算10'), 'deadline_at': update('明天下午六点')}


def test_edit_preserves_other_fields_and_time_anchor_but_requires_new_confirmation():
    from content_planner.intake import IntakeSession
    clock = Clock()
    extractor = Extractor(complete_patch(), {'budget_units': update('预算8')})
    session = IntakeSession(extractor, clock)
    original = session.receive('字幕推广，预算10，明天下午六点')
    first_id = session.receive('确认')['request']['request_id']
    clock.instant = NOW + __import__('datetime').timedelta(days=1)
    edited = session.receive('预算8，其他不变')
    assert edited['state'] == 'ready' and edited['request'] is None
    assert edited['draft'] == {**original['draft'], 'budget_units': 8}
    assert edited['deadline_anchor'] == original['deadline_anchor']
    assert session.receive('确认')['request']['request_id'] != first_id


@pytest.mark.parametrize('source', ['预算10.0', '预算10元', '预算10到15', '预算大约10', '预算0', '预算-1'])
def test_invalid_budget_is_not_rounded_converted_or_guessed(source):
    from content_planner.intake import IntakeSession
    session = IntakeSession(Extractor({'budget_units': update(source)}), Clock())
    reply = session.receive(source)
    assert reply['draft']['budget_units'] is None and reply['state'] == 'collecting'
    assert reply['request'] is None


@pytest.mark.parametrize('patch', [{'unknown': 'x'}, {'budget_units': None},
    {'budget_units': {'value': '10', 'source': '预算10'}},
    {'budget_units': {'value': '预算10', 'source': '不存在'}},
    {'budget_units': {'value': None, 'source': '预算10'}}])
def test_protocol_rejection_preserves_the_previous_draft(patch):
    from content_planner.intake import IntakeSession
    session = IntakeSession(Extractor(complete_patch(), patch), Clock())
    initial = session.receive('字幕推广，预算10，明天下午六点')
    reply = session.receive('预算10')
    assert reply['state'] == 'error' and reply['draft'] == initial['draft']


def test_clear_cancel_expiry_and_limits_do_not_create_requests():
    from content_planner.intake import IntakeSession
    clock = Clock()
    session = IntakeSession(Extractor(complete_patch(), {'budget_units': {'value': None, 'source': '预算没定'}}), clock)
    session.receive('字幕推广，预算10，明天下午六点')
    assert session.receive('预算没定')['draft']['budget_units'] is None
    assert session.receive('确认')['request'] is None
    assert session.receive('取消')['draft'] == dict(topic=None, budget_units=None, deadline_at=None)
    session = IntakeSession(Extractor(complete_patch()), clock)
    session.receive('字幕推广，预算10，明天下午六点')
    clock.instant = datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert session.receive('确认')['request'] is None
    session = IntakeSession(Extractor(*([{}] * 8)), Clock())
    for _ in range(8):
        session.receive('还没定')
    assert session.receive('再说一次')['state'] == 'error'
    assert len(session.extractor.requests) == 8


def test_transient_extraction_error_keeps_draft_and_unknown_usage():
    from content_planner.intake import IntakeSession
    session = IntakeSession(Extractor(complete_patch(), ModelUnavailable('safe failure')), Clock())
    draft = session.receive('字幕推广，预算10，明天下午六点')['draft']
    reply = session.receive('预算改成8')
    assert reply['state'] == 'error' and reply['draft'] == draft
    assert reply['intake_usage']['model_requests'] == 2 and reply['intake_usage']['input_tokens'] is None


def test_extractor_cannot_hide_currency_by_selecting_only_the_digits():
    from content_planner.intake import IntakeSession
    session = IntakeSession(Extractor({'budget_units': update('10')}), Clock())
    reply = session.receive('预算10元')
    assert reply['draft']['budget_units'] is None


def test_extractor_cannot_select_the_upper_end_of_a_budget_range():
    from content_planner.intake import IntakeSession
    session = IntakeSession(Extractor({'budget_units': update('15')}), Clock())
    assert session.receive('预算10到15')['draft']['budget_units'] is None


@pytest.mark.parametrize('text', ['一二', '十十', '一百五'])
def test_malformed_or_ambiguous_chinese_numerals_are_not_guessed(text):
    from content_planner.intake import chinese_integer
    with pytest.raises(ValueError):
        chinese_integer(text)


def test_reconfirmation_after_deadline_returns_the_original_submitted_request():
    from content_planner.intake import IntakeSession
    clock = Clock()
    session = IntakeSession(Extractor(complete_patch()), clock)
    session.receive('字幕推广，预算10，明天下午六点')
    original = session.receive('确认')['request']
    clock.instant = datetime(2026, 11, 2, tzinfo=timezone.utc)
    assert session.receive('确认')['request'] == original
