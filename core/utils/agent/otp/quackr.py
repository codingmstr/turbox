from core.support.utils import Api, date
import re

class Quackr:

    def __init__ ( self ):

        self.used_codes = []
        self.timestamp  = date.hours_to_timestamp(1)

        self.client = Api()
        self.client.set_options(base_url='https://api.quackr.io')

    def credentials ( self, api_key: str ):

        self.client.set_headers(**{'x-api-key': api_key})
        return self
    
    def set_params ( self, phone: str, sender: str = None ):

        params = {'phoneNumber': phone}
        if sender: params["sender"] = sender.upper()

        self.client.set_params(**params)
        return self

    def update_state ( self, timestamp: int, code: str = None, sender: str = None ):

        self.timestamp  = timestamp
        if code: self.used_codes = [*self.used_codes, str(code)][-10:]
        return self

    def extract_code ( self, text: str ):

        t = re.compile(r"\b\d{4,6}\b").search(text or "")
        return t.group(0) if t else None

    def normalize ( self, message: dict ):

        return {
            'code'        : str(message.get('code', '')) or self.extract_code(str(message.get('message', ''))),
            'received_at' : int(message.get('received_at', 0)) or int(message.get('received', 0)),
            'sender'      : str(message.get('sender', '')),
        }

    def recently_codes ( self ):

        data  = self.client.get('receive-sms').json.get('data')
        msgs  = list(data.get("messages") or []) if isinstance(data, dict) else []
        codes = []

        for msg in msgs:
            
            resolved = self.normalize(msg)

            if not resolved['code'] or not resolved['received_at']: continue
            if resolved['received_at'] < self.timestamp or resolved['code'] in self.used_codes: continue

            codes.append(resolved)

        return sorted(codes, key=lambda x: x['received_at'], reverse=True)

    def use_code ( self, message: dict ):

        data = self.normalize(message)

        code, received_at, sender = data.get('code'), data.get('received_at'), data.get('sender')
        if not code or not received_at: return None

        self.update_state(received_at, code, sender)
        return code

    def wait_code ( self, timeout: int = 60 ):

        start = date.now()
        interval = 0.5

        while date.diff(start, unit='s') < timeout:

            codes = self.recently_codes()
            if codes and codes[-1]: return self.use_code(codes[-1])

            date.sleep(interval)
            # interval = min(interval * 1.2, 5)

        return None
