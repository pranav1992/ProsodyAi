from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_client_ip(request: Request) -> str:
    # Trust X-Forwarded-For only because the backend port is loopback-only
    # (see docker-compose.yml) -- nginx is the sole path in, and it always
    # sets this header from the real socket peer, so it can't be spoofed
    # by a client talking directly to the backend.
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip)
