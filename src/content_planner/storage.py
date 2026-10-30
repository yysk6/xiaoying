"""SQLite request index and atomic plan/event persistence."""

import json
from pathlib import Path
import sqlite3
from datetime import timezone

from .contracts import Request
from .domain import Clock, Fault, input_hash, require_complete


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS requests (
        request_id TEXT PRIMARY KEY, input_hash TEXT NOT NULL, input_json TEXT NOT NULL,
        backend TEXT NOT NULL, model TEXT NOT NULL, manifest_json TEXT NOT NULL,
        created_at TEXT NOT NULL, schema_version INTEGER NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS events (
        event_id INTEGER PRIMARY KEY, request_id TEXT NOT NULL REFERENCES requests(request_id),
        kind TEXT NOT NULL CHECK(kind IN ('model','tool','control','validation','lifecycle')),
        operation_id TEXT NOT NULL,
        phase TEXT NOT NULL CHECK(phase IN ('started','succeeded','failed','rejected','interrupted')),
        name TEXT NOT NULL, args_json TEXT NOT NULL, result_json TEXT, state_patch_json TEXT,
        error_code TEXT, rationale TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(request_id, operation_id, phase))''',
    '''CREATE TABLE IF NOT EXISTS plans (
        plan_id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE REFERENCES requests(request_id),
        content_hash TEXT NOT NULL, payload_json TEXT NOT NULL, saved_at TEXT NOT NULL)''',
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class Repository:
    def __init__(self, path: Path | str):
        try:
            self._db = sqlite3.connect(path, timeout=5)
            self._db.row_factory = sqlite3.Row
            self._db.execute('PRAGMA foreign_keys=ON')
            self._db.execute('PRAGMA busy_timeout=5000')
            version = self._db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                self._db.close()
                raise Fault('SCHEMA_VERSION_MISMATCH', 'Unsupported database schema version')
            self._db.execute('PRAGMA journal_mode=WAL')
            with self._db:
                for statement in SCHEMA:
                    self._db.execute(statement)
                self._db.execute('PRAGMA user_version=1')
        except sqlite3.Error as error:
            if hasattr(self, '_db'):
                self._db.close()
            raise Fault('STORAGE_UNAVAILABLE', 'Cannot open the database') from error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._db.close()

    def get_request(self, request_id: str) -> dict:
        try:
            row = self._db.execute('SELECT * FROM requests WHERE request_id=?', (request_id,)).fetchone()
        except sqlite3.Error as error:
            raise Fault('STORAGE_UNAVAILABLE', 'Cannot read request') from error
        if row is None:
            raise Fault('REQUEST_NOT_FOUND', 'Request does not exist')
        result = dict(row)
        result['input'] = json.loads(result.pop('input_json'))
        result['manifest'] = json.loads(result.pop('manifest_json'))
        return result

    def get_plan(self, request_id: str) -> dict | None:
        try:
            row = self._db.execute('SELECT * FROM plans WHERE request_id=?', (request_id,)).fetchone()
        except sqlite3.Error as error:
            raise Fault('STORAGE_UNAVAILABLE', 'Cannot read plan') from error
        if row is None:
            return None
        data = dict(row)
        data['saved_plan'] = json.loads(data.pop('payload_json'))
        return data

    def save_plan(self, payload: dict, tool_call_id: str, arguments: dict) -> tuple[dict, bool]:
        patch = {'status': 'completed', 'saved_plan_id': payload['plan_id']}
        try:
            with self._db:
                cursor = self._db.execute('''INSERT INTO plans VALUES (?,?,?,?,?)
                    ON CONFLICT(request_id) DO NOTHING''',
                    (payload['plan_id'], payload['request_id'], payload['content_hash'],
                     _json(payload), payload['saved_at']))
                data = self.get_plan(payload['request_id'])
                if data['content_hash'] != payload['content_hash']:
                    raise Fault('SAVE_CONFLICT', 'Request already has a different committed plan')
                reused = cursor.rowcount == 0
                result = {'tool_call_id': tool_call_id, 'tool': 'save_plan', 'ok': True, 'reused': reused,
                          'data': data, 'error': None}
                self._insert_event(payload['request_id'], 'tool:' + tool_call_id, 'succeeded', kind='tool',
                                   name='save_plan', args=arguments, rationale=arguments['rationale'],
                                   created_at=payload['saved_at'], result=result, state_patch=patch)
        except sqlite3.Error as error:
            raise Fault('SAVE_FAILED', 'Plan transaction could not be committed') from error
        return data, reused

    def register(self, request: Request, *, backend: str, model: str, manifest: dict, clock: Clock) -> dict:
        try:
            existing = self.get_request(request.request_id)
        except Fault as error:
            if error.code != 'REQUEST_NOT_FOUND':
                raise
        else:
            if existing['input_hash'] != input_hash(request):
                raise Fault('REQUEST_CONFLICT', 'Request ID already has different business input')
            return existing
        require_complete(request, clock)
        try:
            with self._db:
                self._db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,1)',
                                 (request.request_id, input_hash(request), _json(request.model_dump(mode='json')),
                                  backend, model, _json(manifest), clock.now().astimezone(timezone.utc).isoformat()))
        except sqlite3.Error as error:
            raise Fault('STORAGE_UNAVAILABLE', 'Cannot register request') from error
        return self.get_request(request.request_id)

    def _insert_event(self, request_id, operation_id, phase, *, kind, name, args, rationale,
                      created_at, result=None, state_patch=None, error_code=None):
        self._db.execute('''INSERT INTO events
            (request_id,operation_id,phase,kind,name,args_json,rationale,created_at,
             result_json,state_patch_json,error_code) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(request_id,operation_id,phase) DO NOTHING''',
            (request_id, operation_id, phase, kind, name, _json(args), rationale, created_at,
             _json(result) if result is not None else None,
             _json(state_patch) if state_patch is not None else None, error_code))

    def record_event(self, request_id, operation_id, phase, **fields) -> dict:
        try:
            with self._db:
                self._insert_event(request_id, operation_id, phase, **fields)
            return next(event for event in self.events(request_id)
                        if event['operation_id'] == operation_id and event['phase'] == phase)
        except sqlite3.Error as error:
            raise Fault('STORAGE_UNAVAILABLE', 'Cannot write event') from error

    def events(self, request_id: str) -> list[dict]:
        try:
            rows = self._db.execute('SELECT * FROM events WHERE request_id=? ORDER BY event_id',
                                    (request_id,)).fetchall()
        except sqlite3.Error as error:
            raise Fault('STORAGE_UNAVAILABLE', 'Cannot read events') from error
        result = []
        for row in rows:
            event = dict(row)
            for name in ('args', 'result', 'state_patch'):
                raw = event.pop(name + '_json')
                event[name] = json.loads(raw) if raw is not None else None
            result.append(event)
        return result
