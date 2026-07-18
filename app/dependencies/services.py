from fastapi import Request

from app.db.session import SessionLocal


def get_coordinator(request: Request):
    return request.app.state.coordinator


def get_db():
    with SessionLocal() as session:
        yield session
