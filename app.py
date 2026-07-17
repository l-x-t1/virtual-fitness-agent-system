"""Compatibility launcher. Prefer: uvicorn app.main:app --port 8765"""
import uvicorn


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8765)
