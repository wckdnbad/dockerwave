from dotenv import load_dotenv
from os import environ
import redis

load_dotenv()

class ApplicationConfig:
    SECRET_KEY = environ.get("SECRET_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = environ.get("FLASK_ENV") != "production"
    SQLALCHEMY_DATABASE_URI = environ.get("DATABASE_URL") or r"sqlite:///./db.sqlite"
    SESSION_TYPE = "redis"
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_REDIS = redis.from_url("redis://127.0.0.1:6379")
    SESSION_COOKIE_SAMESITE = environ.get("FLASK_ENV") == "production" and 'None' or 'Lax'
    SESSION_COOKIE_SECURE = environ.get("FLASK_ENV") == "production"
