"""Isolated integration-test import target; never used by production."""
import os

from interview_forge.api.app import app


@app.middleware("http")
async def identify_test_worker(request, call_next):
    response = await call_next(request)
    response.headers["X-Test-Worker"] = str(os.getpid())
    return response
