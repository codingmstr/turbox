from ..login.bigo import Bigo as BigoLogin
import requests

TOKENS = {
    '787115274': 'BAAAAGBhXTC22FZu5VH5ZxiBbqskYMXY2scC2lGb0thT9Pbpt8Rw8kgQwrQZw5sbv1y5VAXp1j0kVCwjHEu996E7LEO4RhT07LZH6XjG',
}

class Bigo:

    def __init__ ( self ):

        self.phone    = None
        self.country  = None
        self.password = None
        self.token    = None

    def credentials ( self, country: str, phone: str, password: str ):

        self.phone    = phone
        self.country  = country
        self.password = password
        self.token    = TOKENS.get(phone)

        return self

    def login ( self ):

        print('[BIGO] -> login ...')
        self.token = TOKENS[self.phone] = BigoLogin().credentials(self.phone, self.country, self.password).get_token()
        print(self.token)

        return self

    def post ( self, path: str, data: dict = None ):

        res = requests.post(
            f"https://d3kckleqjlcua1.cloudfront.net/bigo_act_agent_api/{path.lstrip('/')}",
            headers={
                "accept": "application/json, text/plain, */*",
                "content-type": "application/json",
                "origin": "https://www.bigo.tv",
                "referer": "https://www.bigo.tv/static-fed/reseller/index.html?source=quickly_pay",
                "x-auth-token": self.token,
            },
            json={
                'appOs': 1,
                'isAgent': 1,
                'platform': 1,
                'reqFromSource': 4,
                'whiteType': 0,
                **(data or {}),
            }
        )

        try:

            response = res.json()
            if response.get('message') == 'unLogin': return self.login().post(path, data)
            return response

        except: return None

    def logout ( self ):

        return self.post("official/agent/logout")

    def orders ( self, page: int = 1, size: int = 20 ):
       
        data = { "page": page, "size": size }
        return self.post("official/order/list", data)

    def order_detail ( self, order_id: str ):
       
        data = { "orderId": order_id }
        return self.post("official/order/detail", data)

    def balance ( self ):
       
        return self.post("official/agent/balance")

    def profile ( self ):
       
        return self.post("official/agent/index")

    def packages ( self ):
        
        return self.post("official/package/list")

    def get_user ( self, bigo_id: str, type: str = "recharge" ):
       
        data = { "bigo_id": bigo_id, "type": type }
        return self.post("official/guest/getNameByBigoId", data)

    def password_status ( self ):
       
        return self.post("password/getPwdStatus")

    def send_sms ( self, agent_id: str, order_id: str ):
        
        return self.post("password/sendSMS", {'agent_id': agent_id, 'order_id': order_id})

    def new_order ( self, bigo_id: str, diamond_count: int, type: int = 0 ):

        data = {"bigoId": bigo_id, "diamondCount": diamond_count, "amount": int(diamond_count * .02 * 100), "type": type}
        return self.post("official/order/addAgentOrder", data)

    def confirm_order ( self, agent_id: int, order_id: str, verify_code: str = None, pwd: str = None, type: int = 2 ):
       
        data = {"agent_id": agent_id, "order_id": order_id, "verify_code": verify_code, 'pwd': pwd, "type": type}
        return self.post("official/order/recharge", data)
