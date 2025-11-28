import time, datetime, calendar, zoneinfo
from typing import Any
from .parser import Parser

class Date:

    def __init__ ( self, timezone: str = "UTC", locale: str = "en", fmt: str = "%Y-%m-%d %H:%M:%S" ):

        self.timezone    = zoneinfo.ZoneInfo(timezone)
        self.parser      = Parser()
        self.locale      = locale
        self.default_fmt = fmt

    def configure ( self, **options ):

        if 'timezone' in options: self.timezone = zoneinfo.ZoneInfo(options['timezone'])
        if 'fmt' in options: self.default_fmt = options['fmt']
        if 'locale' in options: self.locale = options['locale']

        return self


    def now ( self ):

        return int(datetime.datetime.now(self.timezone).timestamp())

    def now_ms ( self ):

        return int(datetime.datetime.now(self.timezone).timestamp() * 1000)

    def now_dt ( self ):

        return datetime.datetime.now(self.timezone)

    def now_iso ( self ):

        return self.now_dt().isoformat(timespec='milliseconds') + 'Z'

    def now_str ( self, fmt: str = None ):

        return self.now_dt().strftime(fmt or self.default_fmt)

    def utc_str ( self, fmt: str = None ):

        return datetime.datetime.now(datetime.timezone.utc).strftime(fmt or self.default_fmt)

    def utc_offset ( self ):

        local = datetime.datetime.now(self.timezone)
        utc   = datetime.datetime.now(datetime.timezone.utc)

        return round((local - utc).total_seconds() / 3600, 2)


    def extract ( self, value: Any = None, key: str = None ):

        dt = None

        if not value:
            dt = datetime.datetime.now(self.timezone)

        elif isinstance(value, (int, float)):
            dt = datetime.datetime.fromtimestamp(value / 1000.0 if value > 1e12 else value, tz=self.timezone)

        elif isinstance(value, str):
            try: dt = datetime.datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=self.timezone)
            except:
                for fmt in (self.default_fmt, "%Y-%m-%d"):
                    try:
                        dt = datetime.datetime.strptime(value, fmt).replace(tzinfo=self.timezone)
                        break
                    except: pass

        elif isinstance(value, datetime.datetime): dt = value if value.tzinfo else value.replace(tzinfo=self.timezone)

        if not dt: return None

        parts = {
            "year"   : dt.year,
            "month"  : dt.month,
            "day"    : dt.day,
            "hour"   : dt.hour,
            "minute" : dt.minute,
            "second" : dt.second,
            "micro"  : dt.microsecond,
        }

        return parts.get(key) if key else parts

    def ensure_datetime ( self, value: Any = None ):

        p = self.extract(value) or self.extract()

        return datetime.datetime(
            p['year'], p['month'], p['day'],
            p['hour'], p['minute'], p['second'],
            tzinfo=self.timezone
        )

    def format_like ( self, original: Any, dt: datetime.datetime ):

        current = int(dt.timestamp() * 1000)

        if original is None: return current
        if isinstance(original, (int, float)): return current if original > 1e12 else int(dt.timestamp())

        if isinstance(original, str):
            if "T" in original or "Z" in original: return dt.isoformat(timespec='milliseconds') + "Z"
            if ":" in original: return dt.strftime(self.default_fmt)
            return dt.strftime("%Y-%m-%d")

        if isinstance(original, datetime.datetime): return dt
        return current

    def diff ( self, start: Any, end: Any = None, unit: str = None, absolute: bool = True ):

        s = self.ensure_datetime(start)
        e = self.ensure_datetime(end)

        if not s or not e: return None

        delta_ms = int((e - s).total_seconds() * 1000)
        ms = abs(delta_ms) if absolute else delta_ms

        if not unit:
            if ms < 1000: unit = 'ms'
            elif ms < 60000: unit = 's'
            elif ms < 3600000: unit = 'm'
            elif ms < 86400000: unit = 'h'
            else: unit = 'd'

        if unit == 's': return round(ms / 1000, 3)
        if unit == 'm': return round(ms / 60000, 3)
        if unit == 'h': return round(ms / 3600000, 3)
        if unit == 'd': return round(ms / 86400000, 3)

        return ms

    def since ( self, value: Any = None, unit: str = 's' ):

        return self.diff(value, self.now_dt(), unit=unit, absolute=False)

    def sleep ( self, seconds: float ):

        time.sleep(seconds)
        return True


    def add_seconds ( self, current = None, value: float = 0 ):

        new_dt = self.ensure_datetime(current) + datetime.timedelta(seconds=value)
        return self.format_like(current, new_dt)

    def add_minutes ( self, current = None, value: float = 0 ):

        new_dt = self.ensure_datetime(current) + datetime.timedelta(minutes=value)
        return self.format_like(current, new_dt)

    def add_hours ( self, current = None, value: float = 0 ):

        new_dt = self.ensure_datetime(current) + datetime.timedelta(hours=value)
        return self.format_like(current, new_dt)

    def add_days ( self, current = None, value: float = 0 ):

        new_dt = self.ensure_datetime(current) + datetime.timedelta(days=value)
        return self.format_like(current, new_dt)

    def add_months ( self, current = None, value: float = 0 ):

        dt = self.ensure_datetime(current)

        m = dt.month - 1 + int(value)
        y = dt.year + m // 12
        m = m % 12 + 1
        d = min(dt.day, calendar.monthrange(y, m)[1])

        new_dt = datetime.datetime(y, m, d, dt.hour, dt.minute, dt.second, dt.microsecond, tzinfo=self.timezone)
        return self.format_like(current, new_dt)

    def add_years ( self, current = None, value: float = 0 ):

        dt = self.ensure_datetime(current)
        y = dt.year + int(value)

        try: new_dt = datetime.datetime(y, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.microsecond, tzinfo=self.timezone)
        except ValueError:
            if dt.month == 2 and dt.day == 29:
                new_dt = datetime.datetime(y, 2, 28, dt.hour, dt.minute, dt.second, dt.microsecond, tzinfo=self.timezone)
            else: raise

        return self.format_like(current, new_dt)


    def start_of_day ( self, timestamp: int = None ):

        dt = datetime.datetime.fromtimestamp((timestamp or self.now()), tz=self.timezone)
        return int(datetime.datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=self.timezone).timestamp() * 1000)

    def end_of_day ( self, timestamp: int = None ):

        dt = datetime.datetime.fromtimestamp((timestamp or self.now()), tz=self.timezone)
        return int(datetime.datetime(dt.year, dt.month, dt.day, 23, 59, 59, 999000, tzinfo=self.timezone).timestamp() * 1000)

    def start_of_week ( self, timestamp: int = None ):

        dt = datetime.datetime.fromtimestamp((timestamp or self.now()), tz=self.timezone)
        start = dt - datetime.timedelta(days=dt.weekday())
        return int(datetime.datetime(start.year, start.month, start.day, 0, 0, 0, tzinfo=self.timezone).timestamp() * 1000)

    def end_of_week ( self, timestamp: int = None ):

        start = self.start_of_week(timestamp)

        end = datetime.datetime.fromtimestamp(start / 1000, tz=self.timezone) + \
            datetime.timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999000)

        return int(end.timestamp() * 1000)

    def start_of_month ( self, timestamp: int = None ):

        dt = datetime.datetime.fromtimestamp((timestamp or self.now()), tz=self.timezone)
        return int(datetime.datetime(dt.year, dt.month, 1, 0, 0, 0, tzinfo=self.timezone).timestamp() * 1000)

    def end_of_month ( self, timestamp: int = None ):

        dt = datetime.datetime.fromtimestamp((timestamp or self.now()), tz=self.timezone)
        days = calendar.monthrange(dt.year, dt.month)[1]
        return int(datetime.datetime(dt.year, dt.month, days, 23, 59, 59, 999000, tzinfo=self.timezone).timestamp() * 1000)

    def start_of_year ( self, timestamp: int = None ):

        dt = datetime.datetime.fromtimestamp((timestamp or self.now()), tz=self.timezone)
        return int(datetime.datetime(dt.year, 1, 1, 0, 0, 0, tzinfo=self.timezone).timestamp() * 1000)

    def end_of_year ( self, timestamp: int = None ):

        dt = datetime.datetime.fromtimestamp((timestamp or self.now()), tz=self.timezone)
        return int(datetime.datetime(dt.year, 12, 31, 23, 59, 59, 999000, tzinfo=self.timezone).timestamp() * 1000)

    def last_day_of_month ( self, value: Any = None ):

        dt = self.extract(value) or self.extract()
        return calendar.monthrange(dt['year'], dt['month'])[1]


    def from_str ( self, value: str ):

        return self.parser.parse(value)

    def to_timezone ( self, value: Any, tz: str ):

        dt = self.ensure_datetime(value)
        return dt.astimezone(zoneinfo.ZoneInfo(tz))

    def timestamp_to_hours ( self, timestamp: int ):

        return round((self.now_ms() - int(timestamp)) / 3_600_000, 3)

    def timestamp_to_datetime ( self, timestamp: int ):

        return datetime.datetime.fromtimestamp(int(timestamp) / 1000.0, tz=self.timezone)

    def hours_to_timestamp ( self, hours: float ):

        return int(self.now_ms() - (hours * 3_600_000))

    def datetime_to_timestamp ( self, dt: datetime.datetime ):

        return int(dt.timestamp() * 1000)

    def between ( self, value: Any, start: Any, end: Any ):

        v = self.ensure_datetime(value)
        s = self.ensure_datetime(start)
        e = self.ensure_datetime(end)

        return (s <= v <= e) if s <= e else (e <= v <= s)

    def human ( self, value: Any ):

        diff   = int((datetime.datetime.now(self.timezone) - self.ensure_datetime(value)).total_seconds())
        future = diff < 0
        delta  = abs(diff)

        if delta < 60: text = "just now"
        elif delta < 3600: text = f"{int(delta/60)} minute{'s' if delta>=120 else ''}"
        elif delta < 86400: text = f"{int(delta/3600)} hour{'s' if delta>=7200 else ''}"
        elif delta < 604800: text = f"{int(delta/86400)} day{'s' if delta>=172800 else ''}"
        elif delta < 2592000: text = f"{int(delta/604800)} week{'s' if delta>=1209600 else ''}"
        elif delta < 31536000: text = f"{int(delta/2592000)} month{'s' if delta>=5184000 else ''}"
        else: text = f"{int(delta/31536000)} year{'s' if delta>=63072000 else ''}"

        return f"in {text}" if future else f"{text} ago"
