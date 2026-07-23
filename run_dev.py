"""Local dev entrypoint: forces TEST_MODE on (real API integration lands in
a later ticket) and runs the FastAPI app with uvicorn.
"""

import os

os.environ.setdefault("TEST_MODE", "true")

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
