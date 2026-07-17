from fastapi import Request


def get_coordinator(request: Request):
    return request.app.state.coordinator


def get_db():
    """Database dependency template. Existing helpers open short-lived connections."""
    from database import connect

    with connect() as connection:
        yield connection
