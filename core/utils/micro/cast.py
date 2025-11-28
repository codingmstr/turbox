from typing import Any, Union
import json, datetime, re, math

class Cast:

    def __init__ ( self ):
        pass

    def string ( self, value: Any ):

        if value is None: return ''
        if isinstance(value, (list, dict, set, tuple)): return json.dumps(value, ensure_ascii=False)

        return str(value).strip()

    def boolean ( self, value: Any ):

        truthy = {'true', '1', 't', 'yes', 'y', 'ya', 'yep', 'ok', 'on', 'done', 'always'}
        falsy  = {'false', '0', 'f', 'no', 'n', 'off', 'none', 'null', ''}
        s = self.string(value).lower()

        if s in truthy: return True
        if s in falsy: return False

        return bool(value)

    def integer ( self, value: Any ):

        try:
            if isinstance(value, bool): return int(value)
            return int(float(value))
        except: return 0

    def float ( self, value: Any, decimal: int = 2 ):

        try: return round(float(value), decimal)
        except: return 0.0

    def positive ( self, value: Any, decimal: int = 2 ):

        val = self.float(value, decimal)
        return val if val > 0 else 0.0

    def abs ( self, value: Any ):

        return abs(value)

    def floor ( self, value: Any ):

        return math.floor(value)

    def ceil ( self, value: Any ):

        return math.ceil(value)

    def round ( self, value: Any, decimal: int = 2 ):

        return round(value, decimal)

    def to_datetime ( self, value: Union[str, int, float], fmt: str = None ):

        if isinstance(value, datetime.datetime): return value

        try:
            if isinstance(value, (int, float)): return datetime.datetime.fromtimestamp(value)
            if fmt: return datetime.datetime.strptime(str(value), fmt)
            return datetime.datetime.fromisoformat(str(value))
        except: return None

    def to_list ( self, value: Any ):

        if value is None: return []
        if isinstance(value, list): return value
        if isinstance(value, (set, tuple)): return list(value)
        if isinstance(value, dict): return list(value.values())

        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list): return parsed
            except: pass
            return [v.strip() for v in re.split(r'[,\|;]', value) if v.strip()]

        return [value]

    def to_dict ( self, value: Any ):

        if isinstance(value, dict): return value

        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict): return parsed
            except: pass

        return {'value': value}

    def to_json ( self, value: Any, indent: int = None ):

        try: return json.dumps(value, ensure_ascii=False, indent=indent)
        except: return '{}'

    def from_json ( self, value: str ):

        try: return json.loads(value)
        except: return None

    def to_bytes ( self, value: Any ):

        try:
            if isinstance(value, bytes): return value
            return str(value).encode('utf-8', 'ignore')
        except: return b''

    def from_bytes ( self, value: bytes ):

        if isinstance(value, str): return value

        try: return value.decode('utf-8', 'ignore')
        except: return str(value)

    def auto ( self, value: Any ):

        if self.is_int(value): return self.integer(value)
        if self.is_float(value): return self.float(value)
        if self.is_bool(value): return self.boolean(value)
        if self.is_json(value): return self.from_json(value)
        if self.is_date(value): return self.to_datetime(value)

        return self.string(value)

    def unify ( self, values: list ):

        if not values: return values

        if all(self.is_int(v) for v in values): return [int(v) for v in values]
        if all(self.is_float(v) for v in values): return [float(v) for v in values]

        return [self.auto(v) for v in values]

    def is_int ( self, value: Any ):

        try: int(value); return True
        except: return False

    def is_float ( self, value: Any ):

        try: float(value); return True
        except: return False

    def is_bool ( self, value: Any ):

        s = str(value).lower()
        return s in ('true', 'false', '1', '0', 'yes', 'no')

    def is_json ( self, value: Any ):

        if not isinstance(value, str): return False

        try:
            json.loads(value)
            return True
        except: return False

    def is_empty ( self, value: Any ):

        if value is None: return True
        if isinstance(value, (str, list, tuple, set, dict)): return len(value) == 0

        return False

    def is_numeric ( self, value: Any ):

        return re.fullmatch(r'^[+-]?(\d+(\.\d+)?|\.\d+)$', str(value).strip()) is not None

    def is_positive ( self, value: Any ):

        try: return float(value) > 0
        except: return False

    def is_negative ( self, value: Any ):

        try: return float(value) < 0
        except: return False

    def is_date ( self, value: Any ):

        if isinstance(value, datetime.datetime): return True

        try:
            datetime.datetime.fromisoformat(str(value))
            return True
        except: return False

    def clamp ( self, value: Any, min_val: float, max_val: float ):

        try: return max(min(float(value), max_val), min_val)
        except: return min_val

    def safe_divide ( self, a: Any, b: Any, decimal: int = 2 ):

        try:
            result = float(a) / float(b)
            return round(result, decimal)
        except ZeroDivisionError: return 0.0
        except: return 0.0

    def percent ( self, a: Any, b: Any, decimal: int = 2 ):

        try:
            if float(b) == 0: return 0.0
            return round((float(a) / float(b)) * 100, decimal)
        except: return 0.0

    def sign ( self, value: Any ):

        try:
            val = float(value)
            return -1 if val < 0 else (1 if val > 0 else 0)
        except: return 0

    def range_check ( self, value: Any, start: float, end: float, inclusive: bool = True ):

        try:
            val = float(value)
            return start <= val <= end if inclusive else start < val < end
        except: return False

    def compare_type ( self, a: Any, b: Any ):

        return type(a) is type(b)
