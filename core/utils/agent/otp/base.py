import requests, time, re

class Base:

    def __init__ ( self ):

        self.base_url   = ''
        self.headers    = {}
        self.query      = {}
        self.used_codes = []
        self.timestamp  = int((time.time() - 3600) * 1000)

    def credentials ( self, **kwargs ):

        self.headers = kwargs
        return self

    def params ( self, **kwargs ):

        self.query = kwargs
        return self

    def resolve_code ( self, message: dict ):

        return {
            'code'        : str(message.get('code', '')) or self.extract_code(str(message.get('message', ''))),
            'received_at' : int(message.get('received_at', 0)) or int(message.get('received', 0)),
            'sender'      : str(message.get('sender', '')),
        }

    def resolve_codes ( self ):

        return []

    def request ( self, method: str, endpoint: str ):

        url = self.base_url.rstrip("/") + "/" + endpoint.lstrip("/")
        method = method.upper().strip()

        for _ in range(3):

            try:

                if method == "POST": res = requests.post(url, json=self.query, headers=self.headers, timeout=10)
                elif method == "PUT": res = requests.put(url, json=self.query, headers=self.headers, timeout=10)
                elif method == "DELETE": res = requests.delete(url, headers=self.headers, params=self.query, timeout=10)
                else: res = requests.get(url, params=self.query, headers=self.headers, timeout=10)

                res.raise_for_status()
                return res.json()

            except: time.sleep(0.5)

        return {}

    def update_state ( self, timestamp: int, code: str = None, sender: str = None ):

        self.timestamp  = timestamp
        if code: self.used_codes = [*self.used_codes, str(code)][-10:]
        return self

    def extract_code ( self, text: str ):

        t = re.compile(r"\b\d{4,6}\b").search(text or "")
        return t.group(0) if t else None

    def use_code ( self, message: dict ):

        data = self.resolve_code(message)

        code, received_at, sender = data.get('code'), data.get('received_at'), data.get('sender')
        if not code or not received_at: return None

        self.update_state(received_at, code, sender)
        return code

    def wait_latest_code ( self, timeout: int = 60 ):

        start_at = time.time()
        interval = 0.5

        while time.time() - start_at < timeout:

            codes = self.resolve_codes()
            if codes and codes[-1]: return self.use_code(codes[-1])

            time.sleep(interval)
            interval = min(interval * 1.2, 5)

        return None

# use core/support/api
