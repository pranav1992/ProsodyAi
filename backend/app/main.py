import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth import hash_password
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.logging_config import configure_logging
from app.models import User
from app.rate_limit import limiter
from app.routes import auth, batches

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="AutoAce Voice Tone & Noise Dashboard API")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # A handler registered via @app.exception_handler(Exception) runs in
    # Starlette's outermost ServerErrorMiddleware, *outside* CORSMiddleware,
    # so its response never gets CORS headers applied -- the browser then
    # reports a CORS error and masks the real 500. Catching here instead,
    # inside CORSMiddleware, keeps the response on the normal response path.
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.exception("%s %s failed after %dms", request.method, request.url.path, elapsed_ms)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info("%s %s %d %dms", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(batches.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == settings.admin_email).first():
            db.add(User(email=settings.admin_email, hashed_password=hash_password(settings.admin_password)))
            db.commit()
    finally:
        db.close()


@app.get("/health")
@limiter.limit("10/minute")
def health(request: Request):
    return {"status": "ok"}
