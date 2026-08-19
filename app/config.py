import os


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _load_dotenv(path: str = ".env") -> None:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())
    except FileNotFoundError:
        pass


_load_dotenv()

OZEKI_BASE_URL   = _get("OZEKI_BASE_URL",   "http://127.0.0.1:9508")
OZEKI_USERNAME   = _get("OZEKI_USERNAME",   "admin")
OZEKI_PASSWORD   = _get("OZEKI_PASSWORD",   "")
OZEKI_WEBHOOK_URL = _get("OZEKI_WEBHOOK_URL", "http://localhost:5000/webhook/inbound")

OPENVOX_BASE_URL = _get("OPENVOX_BASE_URL", "http://192.168.150.20")
OPENVOX_USERNAME = _get("OPENVOX_USERNAME", "smsuser")
OPENVOX_PASSWORD = _get("OPENVOX_PASSWORD", "")

DB_HOST     = _get("DB_HOST",     "127.0.0.1")
DB_PORT     = int(_get("DB_PORT", "3306"))
DB_USER     = _get("DB_USER",     "ozeki_app")
DB_PASSWORD = _get("DB_PASSWORD", "changeme")
DB_NAME     = _get("DB_NAME",     "ozeki_app")

APP_PORT = int(_get("APP_PORT", "5000"))
