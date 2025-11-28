from core.routing import route


with route.namespace('app.controllers').version(1).name('api'):

    with route.controller('order').prefix('orders').name('orders'):

        route.get('', 'store').name('store')
        route.post('', 'store').name('store')

        with route.prefix('{id}'):

            route.get('', 'show').name('show')
            route.put('', 'update').name('update')
            route.delete('', 'destroy').name('destroy')
