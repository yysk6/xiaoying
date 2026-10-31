"""Bounded requirement collection before any business task is registered."""

from datetime import datetime, timedelta, timezone
from copy import deepcopy
import re
import uuid

from .contracts import Deadline, Request, StrictDTO, normalize_text
from .domain import SystemClock, require_complete
from .model import ModelUnavailable
from pydantic import Field, TypeAdapter, ValidationError


LOCAL = timezone(timedelta(hours=8))
DIGITS = dict(zip('零〇一二两三四五六七八九', [0, 0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9]))


def chinese_integer(text):
    if re.fullmatch(r'\d+', text):
        return int(text)
    total, section, number = 0, 0, 0
    for char in text:
        if char in DIGITS:
            number = DIGITS[char]
        elif char in '十百千':
            section += (number or 1) * {'十': 10, '百': 100, '千': 1000}[char]
            number = 0
        elif char == '万':
            total += (section + number or 1) * 10000
            section, number = 0, 0
        else:
            raise ValueError('请明确整数数值')
    value = total + section + number
    if text.replace('两', '二').replace('〇', '零') != _chinese_numeral(value):
        raise ValueError('中文数字不明确，请使用阿拉伯整数')
    return value


def _chinese_numeral(value):
    if value >= 10000:
        high, low = divmod(value, 10000)
        return (_chinese_numeral(high) + '万' +
                (('零' if low < 1000 else '') + _chinese_numeral(low) if low else ''))
    result, pending_zero = '', False
    for unit, label in ((1000, '千'), (100, '百'), (10, '十'), (1, '')):
        digit, value = divmod(value, unit)
        if digit:
            result += ('零' if pending_zero else '') + '零一二三四五六七八九'[digit] + label
            pending_zero = False
        elif result and value:
            pending_zero = True
    return (result[1:] if result.startswith('一十') else result) or '零'


def parse_budget(text, utterance=None):
    if utterance is not None:
        for match in re.finditer(re.escape(text), utterance):
            before, after = utterance[:match.start()], utterance[match.end():]
            if (re.search(r'(?:[\d.+\-¥￥$~～]|到|至|大约|大概|约|差不多|人民币|美元)\s*$', before)
                    or re.match(r'\s*(?:[\d.]|元|块|美元|人民币|港币|美金|左右|到|至|[~～-]\s*\d)', after)):
                raise ValueError('预算原文包含货币、范围或不明确的数值，请重述模拟单位上限')
    if re.search(r'元|美元|美金|人民币|港币|块|[¥￥$]|左右|大概|差不多|大约|约|到|至|[~～]', text):
        raise ValueError('请明确预算上限，使用整数模拟单位，不换算货币或范围')
    numbers = re.findall(r'[+-]?\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万]+', text)
    if len(numbers) != 1 or '.' in numbers[0] or numbers[0].startswith(('-', '+')):
        raise ValueError('预算必须是一个正整数模拟单位')
    value = chinese_integer(numbers[0])
    if not 1 <= value <= 100000:
        raise ValueError('预算必须在1至100000个模拟单位之间')
    return value


def resolve_deadline(text, anchor):
    text = re.sub(r'\s+', '', normalize_text(text))
    text = re.sub(r'(之前|以前|前)?(完成|截止)?$', '', text)
    text = re.sub(r'(之前|以前|前)$', '', text)
    try:
        instant = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        instant = None
    if instant is not None and ('T' in text or ':' in text):
        if instant.tzinfo is not None:
            return TypeAdapter(Deadline).validate_python(text)
        return instant.replace(tzinfo=LOCAL).astimezone(timezone.utc).isoformat()
    relative = re.fullmatch(r'(今天|明天|后天)(.+)', text)
    absolute = re.fullmatch(r'(\d{4})(?:年|-)(\d{1,2})(?:月|-)(\d{1,2})(?:日|号|T)?(.+)', text)
    if relative:
        date = (anchor.astimezone(LOCAL) + timedelta(days={'今天': 0, '明天': 1, '后天': 2}[relative[1]])).date()
        clock_text = relative[2]
    elif absolute:
        date = datetime(int(absolute[1]), int(absolute[2]), int(absolute[3])).date()
        clock_text = absolute[4]
    else:
        raise ValueError('请提供明确日期和时刻，例如“明天下午六点”或“2026-11-01 18:00”')
    clock = re.fullmatch(r'(上午|下午|晚上|凌晨|中午|早上)?([0-9零〇一二两三四五六七八九十]+)(?:点|时|:)(?:([0-9零〇一二两三四五六七八九十]+)分?)?(半)?', clock_text)
    if not clock or (clock[3] and clock[4]):
        raise ValueError('请明确小时和分钟')
    hour = chinese_integer(clock[2])
    minute = 30 if clock[4] else (chinese_integer(clock[3]) if clock[3] else 0)
    period = clock[1]
    if period:
        if period in {'上午', '早上', '凌晨'} and 0 <= hour < 12:
            pass
        elif period == '下午' and 1 <= hour <= 12:
            hour = hour if hour == 12 else hour + 12
        elif period == '晚上' and 1 <= hour < 12:
            hour += 12
        elif period == '中午' and hour in {11, 12}:
            pass
        else:
            raise ValueError('这个时刻有歧义，请使用24小时制')
    instant = datetime(date.year, date.month, date.day, hour, minute, tzinfo=LOCAL)
    return instant.astimezone(timezone.utc).isoformat()


class FieldUpdate(StrictDTO):
    value: str | None
    source: str = Field(min_length=1, max_length=2000)


class IntakePatch(StrictDTO):
    topic: FieldUpdate | None = None
    budget_units: FieldUpdate | None = None
    deadline_at: FieldUpdate | None = None


class IntakeSession:
    """Collect and confirm requirements; never starts tools or writes a business DB."""
    def __init__(self, extractor, clock=None):
        self.extractor, self.clock = extractor, clock or SystemClock()
        self.draft = dict(topic=None, budget_units=None, deadline_at=None)
        self.deadline_anchor = None
        self.version, self.draft_calls = 0, 0
        self.request = None
        self.issues, self.events, self.usages = {}, [], []

    def usage(self):
        values = {'model_requests': len(self.usages), 'api_cost_usd': None}
        for field in ('input_tokens', 'output_tokens'):
            counts = [(item or {}).get(field) for item in self.usages]
            values[field] = sum(counts) if counts and all(type(n) is int and n >= 0 for n in counts) else None
        return values

    def _reply(self, state=None, message=None, request=None):
        missing = [label for field, label in (('topic', '主题'), ('budget_units', '预算'), ('deadline_at', '截止时间'))
                   if self.draft[field] is None]
        valid = not missing and not self.issues
        if valid and datetime.fromisoformat(self.draft['deadline_at']) <= self.clock.now():
            valid = False
            missing = ['未来的截止时间']
        state = state or ('ready' if valid else 'collecting')
        if message is None:
            message = ('请输入“确认”开始，或描述修改内容；“取消”清空草稿。' if valid else
                       '请补充或明确：' + '、'.join(missing + list(self.issues.values())))
        return {'state': state, 'message': message, 'draft': deepcopy(self.draft),
                'version': self.version, 'deadline_anchor': self.deadline_anchor,
                'request': deepcopy(request), 'intake_usage': self.usage()}

    def receive(self, text):
        text = normalize_text(text)
        if text in {'取消', '新建', '重新开始'}:
            self.draft = dict(topic=None, budget_units=None, deadline_at=None)
            self.request, self.deadline_anchor = None, None
            self.issues, self.draft_calls = {}, 0
            self.version += 1
            self.events.append({'kind': 'cancel', 'version': self.version})
            return self._reply(message='草稿已清空，请描述主题、模拟预算和截止时间。')
        if text in {'确认', '确认开始'}:
            if self.request is not None:
                return self._reply('submitted', '读取已确认任务。', self.request)
            current = self._reply()
            if current['state'] != 'ready':
                return current
            if self.request is None:
                request = Request(request_id='nl-' + uuid.uuid4().hex, **self.draft)
                require_complete(request, self.clock)
                self.request = request.model_dump(mode='json')
                self.events.append({'kind': 'confirmed', 'version': self.version,
                                    'request_id': request.request_id})
            return self._reply('submitted', '需求已确认。', self.request)
        if not text or len(text) > 2000 or text.startswith(('{', '[')):
            return self._reply('error', '请用2000字以内的自然语言描述需求；JSON请使用显式JSON模式。')
        if self.draft_calls >= 8:
            return self._reply('error', '本草稿已达8次需求理解上限；可确认完整需求，或取消后新建。')
        anchor = self.clock.now()
        self.draft_calls += 1
        try:
            raw = self.extractor.extract_intake({'text': text, 'draft': deepcopy(self.draft),
                'now': anchor.astimezone(LOCAL).isoformat(), 'output_schema': IntakePatch.model_json_schema()})
        except ModelUnavailable as error:
            self.usages.append(error.usage)
            self.events.append({'kind': 'extraction_failed', 'code': error.code, 'version': self.version})
            return self._reply('error', error.code + '：需求理解暂不可用，原草稿保留。')
        self.usages.append(deepcopy(getattr(self.extractor, 'last_usage', None)))
        rejection = 'INVALID_PATCH'
        try:
            patch = IntakePatch.model_validate_json(raw)
            for field in patch.model_fields_set:
                item = getattr(patch, field)
                if item is None or item.source not in text:
                    rejection = 'MISSING_SOURCE:' + field
                    raise ValueError('字段缺少本轮原文依据')
                if item.value is None:
                    if not re.search(r'没定|未定|不定|清空|取消|暂不|删除|不确定|还不知道', item.source):
                        rejection = 'UNSUPPORTED_CLEAR:' + field
                        raise ValueError('清除字段需要明确依据')
                elif field != 'topic' and item.value != item.source:
                    rejection = 'SOURCE_VALUE_MISMATCH:' + field
                    raise ValueError('预算和时间必须保留原文')
        except (ValidationError, ValueError, TypeError) as error:
            diagnostics = []
            if isinstance(error, ValidationError):
                for item in error.errors(include_input=False, include_context=False, include_url=False):
                    diagnostics.append({'code': item['type'], 'field': '.'.join(
                        str(part) if part in {'topic', 'budget_units', 'deadline_at', 'value', 'source'} else 'other'
                        for part in item['loc'])})
            self.events.append({'kind': 'extraction_rejected', 'version': self.version,
                                'code': rejection, 'diagnostics': diagnostics})
            return self._reply('error', '需求理解结果无效，原草稿保留，请明确重述。')
        changed = {}
        for field in patch.model_fields_set:
            item = getattr(patch, field)
            value = item.value
            self.issues.pop(field, None)
            try:
                if value is not None:
                    if field == 'budget_units':
                        value = parse_budget(value, text)
                    elif field == 'deadline_at':
                        value = resolve_deadline(value, anchor)
                        if datetime.fromisoformat(value) <= anchor:
                            raise ValueError('请提供未来的截止时间')
                    value = getattr(Request(request_id='preview', **{field: value}), field)
            except (ValueError, ValidationError):
                value = None
                self.issues[field] = {'topic': '主题需为1—200字', 'budget_units': '预算需为明确的正整数模拟单位',
                                      'deadline_at': '截止时间需包含明确日期和时刻，且在未来'}[field]
            if self.draft[field] != value:
                changed[field] = value
                self.draft[field] = value
                self.request = None
            if field == 'deadline_at':
                self.deadline_anchor = anchor.isoformat() if value is not None else None
        if changed:
            self.version += 1
        self.events.append({'kind': 'updated', 'version': self.version, 'changes': changed,
                            'deadline_anchor': self.deadline_anchor, 'usage': self.usages[-1]})
        return self._reply()
