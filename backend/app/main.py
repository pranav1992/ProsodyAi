import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.auth import hash_password
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import User
from app.rate_limit import limiter
from app.routes import auth, batches

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")
settings = get_settings()

app = FastAPI(title="AutoAce Voice Tone & Noise Dashboard API")


@app.middleware("http")
async def catch_unhandled_exceptions(request: Request, call_next):
    # A handler registered via @app.exception_handler(Exception) runs in
    # Starlette's outermost ServerErrorMiddleware, *outside* CORSMiddleware,
    # so its response never gets CORS headers applied -- the browser then
    # reports a CORS error and masks the real 500. Catching here instead,
    # inside CORSMiddleware, keeps the response on the normal response path.
    try:
        return await call_next(request)
    except Exception:
        logger.exception("unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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
