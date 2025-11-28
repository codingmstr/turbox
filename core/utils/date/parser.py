from email.utils import parsedate_to_datetime
from typing import Any
import datetime, re, dateutil.parser, zoneinfo

class Parser:

    def __init__ ( self, timezone: str = "UTC", fmt: str = "%Y-%m-%d %H:%M:%S" ):

        self.timezone = zoneinfo.ZoneInfo(timezone)
        self.default_fmt = fmt
        self.set_context()

    def set_context ( self ):

        self.rel_keywords = {
            "now"        : 0,
            "yesterday"  : -86400,
            "tomorrow"   : 86400,
            "today"      : 0,
            "next week"  : 604800,
            "last week"  : -604800,
            "next month" : 2592000,
            "last month" : -2592000,
            "next year"  : 31536000,
            "last year"  : -31536000,
        }

        self.factors = {
            "second": 1, "seconds": 1,
            "minute": 60, "minutes": 60,
            "hour": 3600, "hours": 3600,
            "day": 86400, "days": 86400,
            "week": 604800, "weeks": 604800,
            "month": 2592000, "months": 2592000,
            "year": 31536000, "years": 31536000,
        }

        self.common_formats = (
            self.default_fmt,
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%Y",
            "%Y/%m/%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        )

        return self

    def match_type ( self, text: str ):

        if text is None: return None
        if isinstance(text, (int, float)): return int(text if text > 1e12 else text * 1000)
        if isinstance(text, datetime.datetime): return int(text.timestamp() * 1000)
        if not isinstance(text, str): return None

        text = text.strip().lower()
        if text.isdigit(): return int(text if len(text) > 10 else int(text) * 1000)

        return text

    def match_keywords ( self, text: str ):

        for key, offset in self.rel_keywords.items():
            if key in text:
                base = datetime.datetime.now(self.timezone)
                new_dt = base + datetime.timedelta(seconds=offset)
                return int(new_dt.timestamp() * 1000)

        return None

    def match_text ( self, text: str ):

        matcher = re.match(
            r"(in\s*)?(-?\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)(\s*ago)?",
            text
        )

        if not matcher: return None

        sign = -1 if matcher.group(4) or "ago" in text else 1
        amount = int(matcher.group(2)) * sign

        unit = matcher.group(3)
        base = datetime.datetime.now(self.timezone)

        seconds = amount * self.factors[unit]
        new_dt = base + datetime.timedelta(seconds=seconds)

        return int(new_dt.timestamp() * 1000)

    def match_multi ( self, text: str ):

        matcher = re.findall(
            r"(\d+)\s*(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)",
            text
        )

        if not matcher: return None
        total_seconds = 0

        for amount, unit in matcher: total_seconds += int(amount) * self.factors[unit]
        if "ago" in text: total_seconds *= -1

        base = datetime.datetime.now(self.timezone)
        new_dt = base + datetime.timedelta(seconds=total_seconds)

        return int(new_dt.timestamp() * 1000)

    def match_format ( self, text: str ):
        
        try:
            dt = datetime.datetime.fromisoformat(text.replace("z", "+00:00").replace("t", "T"))
            dt = dt.replace(tzinfo=self.timezone)
            return int(dt.timestamp() * 1000)

        except:
            for fmt in self.common_formats:
                try:
                    dt = datetime.datetime.strptime(text, fmt).replace(tzinfo=self.timezone)
                    return int(dt.timestamp() * 1000)
                except: continue

        try:
            dt = parsedate_to_datetime(text).astimezone(self.timezone)
            return int(dt.timestamp() * 1000)
        except: pass

        return None

    def match_zone ( self, text: str ):

        try: return int(parsedate_to_datetime(text).astimezone(self.timezone).timestamp() * 1000)
        except: pass

        try: return int(dateutil.parser.parse(text).astimezone(self.timezone).timestamp() * 1000)
        except: pass

        return None

    def parse ( self, text: Any ):

        text = self.match_type(text)
        if text is None or isinstance(text, int): return text

        matched = self.match_keywords(text)
        if matched: return matched

        matched = self.match_text(text)
        if matched: return matched

        matched = self.match_multi(text)
        if matched: return matched

        matched = self.match_format(text)
        if matched: return matched

        matched = self.match_zone(text)
        if matched: return matched
        
        return None
