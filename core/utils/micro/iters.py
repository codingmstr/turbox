from typing import Any, Union, Iterable, Callable
import re, json, ast, math, functools, itertools

class Iters:

    def generate ( self, n: int, kind: str = 'list', keys: Any = None, value: Any = None ):

        kind = kind.lower()
        if n <= 0: return [] if kind in ('list', 'tuple', 'set') else {}

        base = range(n)

        if value is not None: data = [value(i) if callable(value) else value for i in base]
        else: data = list(base)

        if kind == 'list': return data
        if kind == 'tuple': return tuple(data)
        if kind == 'set': return set(data)

        if kind == 'dict':

            if isinstance(keys, (list, tuple)): return dict(zip(keys, data))
            if keys is not None: return dict(zip([keys(i) if callable(keys) else keys for i in base], data))

            return {i: data[i] for i in base}

        return data

    def parse ( self, value: Any = None ):

        if value is None: return []
        if isinstance(value, (list, dict)):  return value
        if isinstance(value, (tuple, set)):   return list(value)

        if isinstance(value, str):

            value = value.strip()
            if not value: return []

            try:
                val = json.loads(value)
                if isinstance(val, (list, dict)): return val
            except: pass

            try:
                val = ast.literal_eval(value)
                if isinstance(val, (list, dict)): return val
            except: pass

            value = re.sub(r',\s*([\]\}])', r'\1', value)
            value = re.sub(r'\[(.*?)\]', lambda m: '[' + ','.join(filter(None, [x.strip() for x in m.group(1).split(',')])) + ']', value, flags=re.S)

            try:
                val = json.loads(value)
                if isinstance(val, (list, dict)): return val
            except: pass

            splitter = ',' if ',' in value else (';' if ';' in value else '|')
            return [s for s in (x.strip() for x in value.split(splitter)) if s]

        return [value]

    def cast ( self, value: Any ):

        raw = self.flatten(self.parse(value))
        if not raw: return []

        int_re    = re.compile(r'^[+-]?\d+$')
        float_re  = re.compile(r'^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?$')

        result = []

        for s in (str(x).strip() for x in raw):

            sl = s.lower()

            if int_re.fullmatch(s): result.append(int(s))
            elif float_re.fullmatch(s): result.append(float(s))
            elif sl in ('true', 'false'): result.append(sl == 'true')
            elif sl in ('null', 'none'): result.append(None)
            else: result.append(s)

        return result

    def resolve_key ( self, key: Any, param: Any = None, ignore_case: bool = True ):

        try:

            if callable(key): return key(param)

            if isinstance(param, tuple) and len(param) == 2:
                k, v = param
                target = v if key in (None, 'value', 'v') else k if key in ('key', 'k') else v
                return target.lower() if ignore_case and isinstance(target, str) else target

            if isinstance(key, str):
                val = param

                for part in key.split('.'):

                    if isinstance(val, dict) and part in val: val = val[part]
                    elif hasattr(val, part): val = getattr(val, part)
                    elif isinstance(val, (list, tuple)) and part.isdigit() and int(part) < len(val): val = val[int(part)]
                    else: return None

                return val.lower() if ignore_case and isinstance(val, str) else val

            return param

        except: param

    def sort ( self, items: Iterable, key: Any = None, reverse: bool = False, ignore_case: bool = True ):

        data = list(items.items()) if isinstance(items, dict) else list(items)

        if key:
            if isinstance(key, (list, tuple)): resolver = lambda x: tuple(self.resolve_key(k, x, ignore_case) for k in key)
            else: resolver = lambda x: self.resolve_key(key, x, ignore_case)

            try: return sorted(data, key=resolver, reverse=reverse)
            except: return sorted(data, key=lambda x: str(resolver(x)), reverse=reverse)

        else:
            types = {type(x).__name__ for x in items}

            if len(types) == 1 and list(types)[0] in ('int', 'float', 'str'): return sorted(items, reverse=reverse)
            else: return sorted(items, key=lambda x: str(x), reverse=reverse)

    def flatten ( self, items: Iterable, deep: bool = True ):

        if isinstance(items, dict): items = items.values()
        result = []

        for a in items:

            if isinstance(a, dict):
                vals = a.values()

                if deep: result.extend(self.flatten(vals))
                else: result.extend(vals)

            elif isinstance(a, (list, tuple, set)):
                if deep: result.extend(self.flatten(a))
                else: result.extend(a)

            else: result.append(a)

        return result

    def flatten_dict ( self, data: dict, sep: str = '.' ):

        result = {}

        def recurse ( d, prefix='' ):
            
            for k, v in d.items():
                path = f"{prefix}{sep}{k}" if prefix else k

                if isinstance(v, dict): recurse(v, path)
                else: result[path] = v

        recurse(data)
        return result

    def merge ( self, *args: Iterable, deep: bool = True ):

        if not args: return None
        base = args[0]

        for other in args[1:]:

            if isinstance(base, dict) and isinstance(other, dict):

                for k, v in other.items():

                    if k in base:

                        if deep and isinstance(base[k], dict) and isinstance(v, dict): base[k] = self.merge(base[k], v, deep=True)
                        elif deep and isinstance(base[k], list) and isinstance(v, list): base[k] = base[k] + v
                        elif deep and isinstance(base[k], set) and isinstance(v, set): base[k] = base[k].union(v)
                        elif deep and isinstance(base[k], tuple) and isinstance(v, tuple): base[k] = base[k] + v
                        else: base[k] = v

                    else: base[k] = v

            elif isinstance(base, list) and isinstance(other, list): base.extend(other)
            elif isinstance(base, set) and isinstance(other, set): base.update(other)
            elif isinstance(base, tuple) and isinstance(other, tuple): base = base + other

            else:
                if isinstance(base, (list, set, tuple)): base = list(base) + list(self.ensure(other))
                elif isinstance(base, dict) and not isinstance(other, dict): base[str(len(base))] = other
                else: base = [base, other]

        return base

    def unique ( self, items: Iterable ):

        seen, result = set(), []

        for x in self.flatten(items):

            if isinstance(x, (list, dict, set, tuple)): continue

            if x not in seen:
                seen.add(x)
                result.append(x)

        return result

    def chunk ( self, items: Iterable, size: int, stream: bool = True ):

        if isinstance(items, dict): items = list(items.values())
        if isinstance(items, set): items = list(items)

        if size <= 0: return [] if not stream else iter(())
        if not stream: return [items[i:i + size] for i in range(0, len(items), size)]

        it = iter(items)

        while True:
            batch = list(itertools.islice(it, size))
            if not batch: break
            yield batch

    def map ( self, items: Iterable, fn: Callable = None ):

        fn = fn or (lambda x: x)

        if isinstance(items, dict):
            result = {}

            for key, value in items.items():
                try: result[key] = fn(value)
                except: pass

        else:
            result = []

            for x in items:
                try: result.append(fn(x))
                except: pass

        return result

    def filter ( self, items: Iterable, fn: Callable = None ):

        fn = fn or (lambda x: x)

        if isinstance(items, dict):
            result = {}

            for key, value in items.items():
                try:
                    if fn(value): result[key] = value
                except: pass

        else:
            result = []

            for x in items:
                try: result.append(x) if fn(x) else None
                except: pass

        return result

    def reduce ( self, items: Iterable, fn: Callable, initial: Any = None ):

        if not items: return initial
        return functools.reduce(fn, items, initial) if initial is not None else functools.reduce(fn, items)

    def group ( self, items: Iterable, key: Callable ):

        result = {}

        for x in items:
            k = key(x)
            result.setdefault(k, []).append(x)

        return result

    def diff ( self, a: Iterable, b: Iterable ):

        b_flat = set(self.flatten(b))
        return [x for x in self.flatten(a) if x not in b_flat]

    def intersect ( self, a: Iterable, b: Iterable ):

        b_flat = set(self.flatten(b))
        return [x for x in self.flatten(a) if x in b_flat]

    def zip ( self, *args: Iterable ):

        return list(map(list, zip(*args)))

    def combine ( self, keys: Iterable, values: Iterable, fill: bool = False ):

        keys, values = list(keys), list(values)
        if fill and len(values) < len(keys): values += [None] * (len(keys) - len(values))
    
        return dict(zip(keys, values))

    def pluck ( self, items: Iterable, key: Union[str, int] ):

        result = []

        for val in items:

            for part in str(key).split('.'):
          
                if isinstance(val, dict) and part in val: val = val[part]
                elif isinstance(val, (list, tuple)) and part.isdigit() and int(part) < len(val): val = val[int(part)]
                else:
                    val = None
                    break

            if val is not None: result.append(val)

        return result

    def sum ( self, items: Iterable ):

        if not items: return 0

        listed  = items.values() if isinstance(items, dict) else items
        numbers = [x for x in self.flatten(listed) if isinstance(x, (int, float))]
        
        return math.fsum(numbers)

    def avg ( self, items: Iterable ):

        if not items: return 0

        listed  = items.values() if isinstance(items, dict) else items
        numbers = [x for x in self.flatten(listed) if isinstance(x, (int, float))]

        return math.fsum(numbers) / len(numbers)

    def min ( self, items: Iterable ):

        if not items: return None

        listed  = items.values() if isinstance(items, dict) else items
        numbers = [x for x in self.flatten(listed) if isinstance(x, (int, float))]

        return min(numbers)

    def max ( self, items: Iterable ):

        if not items: return None

        listed  = items.values() if isinstance(items, dict) else items
        numbers = [x for x in self.flatten(listed) if isinstance(x, (int, float))]

        return max(numbers)

    def first ( self, items: Iterable ):

        if not items: return None

        if isinstance(items, dict): return next(iter(items.values()), None)
        if isinstance(items, set):  return next(iter(items), None)

        return items[0] if isinstance(items, (list, tuple)) and items else None

    def last ( self, items: Iterable ):

        if not items: return None

        if isinstance(items, dict):
            try: return next(reversed(list(items.values())))
            except: return None

        if isinstance(items, set):
            lst = list(items)
            return lst[-1] if lst else None

        return items[-1] if isinstance(items, (list, tuple)) and items else None
    
    def get ( self, data: Iterable, key: Any, default: Any = None ):

        if isinstance(data, dict): return data.get(key, default)
        if isinstance(data, (list, tuple)) and isinstance(key, int) and len(data) > key: return data[key]

        return default

    def set ( self, data: Iterable, key: Any, value: Any ):

        if isinstance(data, dict): data[key] = value
        elif isinstance(data, set): data.add(value)

        elif isinstance(data, list) and isinstance(key, int):
            while len(data) <= key: data.append(None)
            data[key] = value

        elif isinstance(data, tuple) and isinstance(key, int):
            listed = list(data)
            while len(listed) <= key: listed.append(None)
            listed[key] = value
            data = tuple(listed)

        return data

    def has ( self, data: Iterable, key: Any ):

        if isinstance(data, dict): return key in data
        if isinstance(data, set): return key in data
        if isinstance(data, (list, tuple)) and isinstance(key, int): return len(data) > key

        return False

    def to_list ( self, value: Any ):
        
        items = self.parse(value)
        return list(items.values()) if isinstance(items, dict) else list(items)
   
    def to_tuple ( self, value: Any ):
        
        items = self.parse(value)
        return tuple(items.values()) if isinstance(items, dict) else tuple(items)

    def to_set ( self, value: Any ):
        
        items = self.parse(value)
        return set(items.values()) if isinstance(items, dict) else set(items)

    def to_dict ( self, value: Any ):

        items = self.parse(value)
        return items if isinstance(items, dict) else dict.fromkeys(items)

    def ensure ( self, value: Any, kind: str = 'list' ):

        if kind == 'list': return self.to_list(value)
        if kind == 'tuple': return self.to_tuple(value)
        if kind == 'set': return self.to_set(value)
        if kind == 'dict': return self.to_dict(value)

        return [value] if value else []

    def paginate ( self, items: Iterable, page: int, per_page: int ):

        if not items: return []

        start = max((page - 1) * per_page, 0)
        end   = start + per_page

        if isinstance(items, dict): items = list(items.values())
        return items[start:end]

    def windowed ( self, items: Iterable, size: int, step: int = 1 ):

        if size <= 0: return []

        if isinstance(items, dict): items = list(items.values())
        if isinstance(items, set): items = list(items)

        result = []
        for i in range(0, len(items) - size + 1, step): result.append(items[i:i + size])

        return result

    def compare ( self, a: Any, b: Any, deep: bool = True ):

        if a == b: return True
        if type(a) != type(b): return False

        if isinstance(a, dict):

            if set(a.keys()) != set(b.keys()): return False
            return all(self.compare(a[k], b[k], deep) for k in a)

        if isinstance(a, (list, tuple, set)):
            
            if len(a) != len(b): return False
            if deep: return all(self.compare(x, y, deep) for x, y in zip(a, b))
            
            return list(a) == list(b)

        return False

    def clone ( self, value: Any ):

        return json.loads(json.dumps(value))
