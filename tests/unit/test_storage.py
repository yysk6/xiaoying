from datetime import datetime, timezone
import sqlite3

import pytest

from content_planner.contracts import Request
from content_planner.domain import Fault
from content_planner.storage import Repository


class FixedClock:
    value = datetime(2026, 10, 30, 4, tzinfo=timezone.utc)

    def now(self):
        return self.value


def request(**changes):
    return Request.model_validate({'request_id': 's3', 'topic': '字幕', 'budget_units': 10,
                                   'deadline_at': '2026-10-30T16:00:00+08:00', **changes})


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'runtime.db'
    repo = Repository(path)
    yield path, repo
    repo.close()


def register(repo, value=None, clock=None):
    return repo.register(value or request(), backend='mock', model='mock',
                         manifest={'schema_version': '1.0'}, clock=clock or FixedClock())


def test_registered_request_survives_reopening(database):
    path, repo = database
    original = register(repo)
    with Repository(path) as reopened:
        assert reopened.get_request('s3') == original
    assert original['input']['budget_units'] == 10
    assert original['manifest'] == {'schema_version': '1.0'}
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM requests').fetchone()[0] == 1


def test_repeat_registration_reads_original_before_checking_current_deadline(database):
    path, repo = database
    original = register(repo)
    clock = FixedClock()
    clock.value = datetime(2026, 11, 1, tzinfo=timezone.utc)
    assert register(repo, clock=clock) == original
    with pytest.raises(Fault, match='REQUEST_CONFLICT'):
        register(repo, request(budget_units=9), clock)
    assert repo.get_request('s3') == original


def test_events_preserve_phase_order_and_replayed_phase_does_not_overwrite_fact(database):
    path, repo = database
    register(repo)
    fields = dict(kind='tool', name='save_plan', args={'plan_revision': 1}, rationale='保存',
                  created_at='2026-10-30T04:00:00+00:00')
    first = repo.record_event('s3', 'tool:save-1', 'started', **fields)
    finished = repo.record_event('s3', 'tool:save-1', 'failed', error_code='SAVE_FAILED', **fields)
    replay = repo.record_event('s3', 'tool:save-1', 'failed', error_code='different', **fields)
    assert replay == finished
    assert repo.events('s3') == [first, finished]
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM events').fetchone()[0] == 2


def test_new_incomplete_request_does_not_consume_id(database):
    path, repo = database
    with pytest.raises(Fault, match='NEEDS_INPUT'):
        register(repo, Request(request_id='s3'))
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT count(*) FROM requests').fetchone()[0] == 0
    assert register(repo)['request_id'] == 's3'


def test_unknown_database_version_is_refused_without_reinitialization(tmp_path):
    path = tmp_path / 'future.db'
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA user_version=2')
    with pytest.raises(Fault, match='SCHEMA_VERSION_MISMATCH'):
        Repository(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0


def test_version_wal_timeout_and_foreign_key_enforcement(database):
    path, repo = database
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
        assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    with pytest.raises(Fault, match='STORAGE_UNAVAILABLE'):
        repo.record_event('unregistered', 'tool:bad', 'started', kind='tool', name='save_plan', args={},
                          rationale='检查', created_at='2026-10-30T04:00:00+00:00')
    assert repo.events('unregistered') == []


def test_unavailable_database_and_missing_request_have_explicit_errors(tmp_path):
    with pytest.raises(Fault, match='STORAGE_UNAVAILABLE'):
        Repository(tmp_path / 'missing' / 'runtime.db')
    with Repository(tmp_path / 'empty.db') as repo:
        with pytest.raises(Fault, match='REQUEST_NOT_FOUND'):
            repo.get_request('missing')
        assert repo.get_plan('missing') is None
