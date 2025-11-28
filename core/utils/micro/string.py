import re, unicodedata, random, string as strng, uuid, time, html, base64, hashlib, json

class String:

    def __init__ ( self ):
        pass

    def unique ( self, prefix: str = '', length: int = 0 ):

        ts   = format(int(time.time() * 1_000_000), 'x')
        rand = uuid.uuid4().hex
        nano = format(time.time_ns() % 1_000_000_000, 'x')
        mix  = ''.join(random.choices(strng.ascii_lowercase + strng.digits, k=6))

        uid = f"{prefix}{ts}{nano}{rand}{mix}"
        if length and length > 0: uid = uid[:length]

        return uid

    def snake ( self, value: str ):

        if not value: return ''

        value = re.sub(r'[\s\-]+', '_', value)
        value = re.sub(r'(?<!^)(?=[A-Z])', '_', value).lower()

        return re.sub(r'_+', '_', value).strip('_')

    def studly ( self, value: str ):

        if not value: return ''
        value = re.sub(r'[_\-\s]+', ' ', value)

        return ''.join(word.capitalize() for word in value.split())

    def camel ( self, value: str ):

        s = self.studly(value)
        return s[0].lower() + s[1:] if s else s

    def kebab ( self, value: str ):

        if not value: return ''

        value = re.sub(r'[\s_]+', '-', value)
        value = re.sub(r'(?<!^)(?=[A-Z])', '-', value).lower()

        return re.sub(r'-+', '-', value).strip('-')

    def title ( self, value: str ):

        if not value: return ''
        value = re.sub(r'[_\-\s]+', ' ', value)

        return value.title()

    def slug ( self, value: str, max_len: int = None ):

        if not value: return ''

        text = unicodedata.normalize('NFKD', value)
        text = text.encode('ascii', 'ignore').decode('ascii')
        text = re.sub(r'[^a-zA-Z0-9]+', '-', text)
        slug = re.sub(r'-+', '-', text).strip('-').lower()

        return slug[:max_len].rstrip('-') if max_len else slug

    def match_case ( self, value: str, new: str ):

        if value.islower(): return new.lower()
        if value.isupper(): return new.upper()
        if value[0].isupper(): return new.capitalize()

        return new

    def plural ( self, value: str ):

        word  = str(value).strip()
        lower = word.lower()

        if not word: return ''
        if word.endswith('s') and not word.endswith('ss'): return word

        irregulars = {
            'person': 'people', 'man': 'men', 'woman': 'women', 'child': 'children', 'tooth': 'teeth',
            'foot': 'feet', 'mouse': 'mice', 'goose': 'geese', 'ox': 'oxen', 'cactus': 'cacti',
            'focus':'foci', 'nucleus': 'nuclei', 'fungus': 'fungi', 'thesis': 'theses', 'crisis': 'crises',
            'analysis': 'analyses', 'axis': 'axes', 'criterion': 'criteria', 'phenomenon': 'phenomena',
        }

        if lower in irregulars: return self.match_case(word, irregulars[lower])
        if re.search(r'[^aeiou]y$', word, re.I): return self.match_case(word, word[:-1] + 'ies')
        if re.search(r'(fe|f)$', word, re.I): return self.match_case(word, re.sub(r'(fe|f)$', 'ves', word, flags=re.I))
        if re.search(r'[^aeiou]o$', word, re.I) and not re.search(r'(photo|piano|halo)$', lower): return self.match_case(word, word + 'es')
        if re.search(r'(s|sh|ch|x|z)$', word, re.I): return self.match_case(word, word + 'es')

        return self.match_case(word, word + 's')

    def singular ( self, value: str ):

        word  = str(value).strip()
        lower = word.lower()

        if not word: return ''

        irregulars = {
            'people': 'person', 'men': 'man', 'women': 'woman', 'children': 'child', 'teeth': 'tooth', 'feet': 'foot',
            'mice': 'mouse', 'geese': 'goose', 'oxen': 'ox', 'cacti': 'cactus', 'foci': 'focus', 'nuclei': 'nucleus',
            'fungi': 'fungus', 'theses': 'thesis', 'crises': 'crisis', 'analyses': 'analysis', 'axes': 'axis',
            'criteria': 'criterion', 'phenomena': 'phenomenon',
        }

        if lower in irregulars: return self.match_case(word, irregulars[lower])
        if re.search(r'ies$', word, re.I) and not re.search(r'(eies|aies)$', word, re.I): return self.match_case(word, word[:-3] + 'y')
        if re.search(r'(kn|w|l)ives$', word, re.I): return self.match_case(word, re.sub(r'ves$', 'fe', word, flags=re.I))
        if re.search(r'ves$', word, re.I): return self.match_case(word, re.sub(r'ves$', 'f', word, flags=re.I))
        if re.search(r'([^aeiou])oes$', word, re.I): return self.match_case(word, word[:-2])
        if re.search(r'(s|sh|ch|x|z)es$', word, re.I): return self.match_case(word, word[:-2])
        if re.search(r's$', word, re.I) and not re.search(r'ss$', word, re.I): return self.match_case(word, word[:-1])

        return word

    def join ( self, *parts: str, separator: str = '.' ):

        cleaned = [str(p).strip(separator) for p in parts if p not in (None, '', separator)]
        return separator.join(cleaned).replace(f"{separator}{separator}", separator)

    def random ( self, length: int = 8, digits: bool = True, letters: bool = True ):

        chars = ''
        
        if digits: chars += strng.digits
        if letters: chars += strng.ascii_letters

        return ''.join(random.choice(chars) for _ in range(length)) if chars else ''

    def public ( self, value: str ):

        if not value: return ''
        return self.slug(value).replace('-', '_')

    def trim ( self, value: str, char: str = ' ' ):

        return value.strip(char)

    def remove ( self, value: str, char: str = ' ', regex: bool = False ):

        pattern = char if regex else re.escape(char)
        return re.sub(rf'{pattern}+', '', value)

    def match ( self, value: str, pattern: str ):

        return re.match(pattern, value)

    def fullmatch ( self, value: str, pattern: str ):

        return re.fullmatch(pattern, value)

    def search ( self, value: str, pattern: str ):

        return re.search(pattern, value)

    def find ( self, value: str, pattern: str ):

        return re.findall(pattern, value)

    def sub ( self, value: str, pattern: str, repl: str, count: int = 0 ):

        return re.sub(pattern, repl, value, count=count)

    def split ( self, value: str, pattern: str = '\s+', maxsplit: int = 0 ):

        return re.split(pattern, value, maxsplit=maxsplit)

    def has ( self, value: str, pattern: str ):

        return bool(re.search(pattern, value))

    def collapse ( self, value: str ):

        return re.sub(r'\s+', ' ', value).strip()

    def count ( self, value: str, pattern: str ):

        return len(re.findall(pattern, value))

    def escape ( self, value: str ):

        return re.escape(value)

    def truncate ( self, value: str, length: int, end: str = '...' ):

        if not value or len(value) <= length: return value
        return value[:max(0, length - len(end))] + end

    def limit_words ( self, value: str, count: int, end: str = '...' ):

        if not value: return ''

        words = re.split(r'\s+', value.strip())
        if len(words) <= count: return value

        return ' '.join(words[:count]) + end

    def replace ( self, value: str, old: str, new: str, count: int = -1 ):
        
        if not value: return ''
        return value.replace(old, new, count)

    def replace_case_insensitive ( self, value: str, old: str, new: str ):

        if not value: return ''

        pattern = re.compile(re.escape(old), re.I)
        return pattern.sub(lambda m: self.match_case(m.group(), new), value)

    def replace_all_insensitive ( self, value: str, pattern: str, repl: str ):

        return re.sub(pattern, repl, value, flags=re.I)

    def random_slug ( self, length: int = 8 ):

        return self.slug(self.random(length))

    def extract_numbers ( self, value: str ):

        return re.findall(r'\d+(?:\.\d+)?', value)

    def is_email ( self, value: str ):

        return bool(re.fullmatch(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$', value))

    def is_url ( self, value: str ):

        return bool(re.fullmatch(r'^(https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/[^\s]*)?$', value))

    def is_phone ( self, value: str ):

        return bool(re.fullmatch(r'^(?:\+|00)?\d{1,4}?[\s\-\.]?\(?\d{1,4}?\)?(?:[\s\-\.]?\d{1,4}){1,6}$', value.strip()))

    def mask ( self, value: str, start: int = 0, end: int = 0, mask_char: str = '*' ):

        if not value: return ''

        s, e = max(0, start), len(value) - max(0, end)
        s, e = min(s, len(value)), max(s, e)

        return value[:s] + (mask_char * (e - s)) + value[e:]

    def strip_html ( self, value: str ):

        if not value: return ''
        return re.sub(r'<[^>]+>', '', html.unescape(value)).strip()

    def normalize_space ( self, value: str ):

        if not value: return ''
        return re.sub(r'\s+', ' ', value.strip())

    def word_count ( self, value: str ):

        return len(re.findall(r'\b\w+\b', value)) if value else 0

    def char_count ( self, value: str ):

        return len(re.sub(r'\s', '', value)) if value else 0

    def contains_any ( self, value: str, *words ):

        if not value or not words: return False

        v = value.lower()
        return any(str(w).lower() in v for w in words if w)

    def contains_all ( self, value: str, *words ):

        if not value or not words: return False

        v = value.lower()
        return all(w.lower() in v for w in words if w)

    def pad_left ( self, value: str, width: int, char: str = ' ' ):

        return str(value).rjust(width, char)

    def pad_right ( self, value: str, width: int, char: str = ' ' ):

        return str(value).ljust(width, char)

    def to_base64 ( self, value: str ):

        if not value: return ''
        return base64.b64encode(value.encode()).decode()

    def from_base64 ( self, value: str ):

        if not value: return ''

        try: return base64.b64decode(value.encode()).decode()
        except: return ''

    def hash ( self, value: str, algorithm: str = 'sha256' ):

        if not value: return ''

        h = hashlib.new(algorithm)
        h.update(value.encode('utf-8'))

        return h.hexdigest()

    def to_ascii ( self, value: str ):

        if not value: return ''
        return unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')

    def sanitize_sql ( self, value: str ):

        if not value: return ''

        clean = re.sub(r'(--|;|/\*.*?\*/)', '', value)
        return re.sub(r"(['\"])\1+", r'\1', clean).strip()

    def equals_ignore_case ( self, a: str, b: str ):

        return str(a).lower() == str(b).lower()

    def strip_ansi ( self, value: str ):

        return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', value)

    def reverse ( self, value: str ):

        return str(value)[::-1]

    def to_bytes ( self, value: str ):
        
        if value is None: return b''
        if isinstance(value, bytes): return value

        return str(value).encode('utf-8', 'ignore')

    def from_bytes ( self, value: bytes ):

        if value is None: return ''
        if isinstance(value, str): return value

        try: return value.decode('utf-8', 'ignore')
        except: return str(value)

    def between ( self, value: str, start: str, end: str ):

        if not all([value, start, end]): return ''

        pattern = re.escape(start) + r'(.*?)' + re.escape(end)
        match = re.search(pattern, value, re.S)

        return match.group(1).strip() if match else ''

    def strip_symbols ( self, value: str ):

        if not value: return ''
        return re.sub(r'[^a-zA-Z0-9\s]', '', value)

    def humanize_number ( self, value: float ):

        try: num = float(value)
        except: return str(value)

        units = ['', 'K', 'M', 'B', 'T']
        k = 1000.0
        magnitude = 0

        while abs(num) >= k and magnitude < len(units) - 1:
            num /= k
            magnitude += 1

        num = round(num, 1)
        return f"{num:g}{units[magnitude]}"

    def is_json ( self, value: str ):

        if not value: return False

        try:
            json.loads(value)
            return True
        except: return False

    def title_case_safe ( self, value: str ):

        if not value: return ''

        def preserve( word: str ):

            if word.isupper() and len(word) <= 4: return word
            return word.capitalize()

        words = re.split(r'[\s_\-]+', value.strip())
        return ' '.join(preserve(w) for w in words if w)
