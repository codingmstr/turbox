from core.support.utils import env

config = {
    'name'        : env('APP_NAME', 'Python Web'),
    'description' : env('APP_DESCRIPTION', env('APP_NAME', 'Python Web')),
    'version'     : env('APP_VERSION', '1.0.0'),
    'local'       : env('APP_LOCAL', 'en'),
    'env'         : env('APP_ENV', 'local'),
    'debug'       : env('APP_DEBUG', True),
    'host'        : env('APP_HOST', '127.0.0.1'),
    'port'        : env('APP_PORT', 8000),
}
