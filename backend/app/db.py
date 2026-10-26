from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models
    from .security import hash_password

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)

    # Crea el administrador inicial si no existe ninguno
    s = get_settings()
    with SessionLocal() as db:
        if db.scalar(select(models.Usuario).limit(1)) is None:
            db.add(models.Usuario(nombre=s.admin_nombre, email=s.admin_email.lower(),
                                  password_hash=hash_password(s.admin_password)))
            db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
