from fastapi import Request
from fastapi.responses import JSONResponse
from core.support.agent.client.bigo import Bigo
from core.support.agent.otp.quackr import Quackr
from core.support.utils import date

class OrderController:

    def index ( self, request: Request ):

        return JSONResponse({'success': True})

    def get_code ( self, bigo: Bigo, credientials: dict, bigo_id: str, order_id: str ):

        counter = 0
        verify_code = None

        while counter < 5 and not verify_code:
            bigo.send_sms(bigo_id, order_id)
            verify_code = Quackr().credentials(credientials.get('quackr-api')).set_params(credientials.get('quaker-phone'), 'BIGO').update_state(date.hours_to_timestamp(0.01)).wait_code()
            counter += 1

        return verify_code

    def store ( self, request: Request ):

        credientials = {
            'country'      : 'Jordan',
            'phone'        : '787115274',
            'password'     : 'm3290900a',
            'recharge_pwd' : '123456',
            'quackr-api'   : 'ebHN8LLaeQTsvFJxKLO96Bc47ZR2',
            'quaker-phone' : '+447380216305',
        }

        params = dict(request.query_params)

        if not params.get('bigo_id'): return JSONResponse({'success': False, 'message': 'bigo_id field required'})
        if not params.get('diamond_count'): return JSONResponse({'success': False, 'message': 'diamond_count field required'})

        bigo_id, diamond_count = str(params.get('bigo_id')), int(params.get('diamond_count'))
        bigo = Bigo().credentials(credientials.get('country'), credientials.get('phone'), credientials.get('password'))

        order = bigo.new_order(bigo_id, diamond_count)
        if not order.get('data'): return JSONResponse({'success': False, 'order': order})

        order_id = dict(order.get('data')).get('order_id')
        pwd_status = bigo.password_status()

        if dict(pwd_status.get('data')).get('is_open_pwd') and dict(pwd_status.get('data')).get('is_can_use'):
            order = bigo.confirm_order(bigo_id, order_id, pwd=credientials.get('recharge_pwd'))
        else:
            verify_code = self.get_code(bigo, credientials, bigo_id, order_id)
            order = bigo.confirm_order(bigo_id, order_id, verify_code=verify_code)

        print('using password : ', 'Yes' if dict(pwd_status.get('data')).get('is_open_pwd') and dict(pwd_status.get('data')).get('is_can_use') else 'No')
        return JSONResponse({'success': True, 'order': order}) 

    def show ( self, request: Request, id: int ):

        return f'show {id}'

    def update ( self, request: Request, id: int ):

        return f'update {id}'

    def destroy ( self, request: Request, id: int ):

        return f'delete {id}'
