import os
import random

import httpx
from fastapi import FastAPI

app = FastAPI(title="frontend-api")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend-api:8001")


@app.get("/order")
async def get_order():
    """Places a fake order, calling backend-api for stock info."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{BACKEND_URL}/inventory")
        inventory = resp.json()

    return {
        "order_id": random.randint(1000, 9999),
        "inventory": inventory,
        "backend_status": resp.status_code,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
