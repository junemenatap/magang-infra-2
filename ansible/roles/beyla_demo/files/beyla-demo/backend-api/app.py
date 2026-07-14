import random
import time

from fastapi import FastAPI, Response

app = FastAPI(title="backend-api")

ITEMS = ["barang misterius", "Legend Classic 3-in-1 instant coffee", "Monitor dari PT Clarus Innovace"]


@app.get("/inventory")
async def get_inventory(response: Response):
    """Returns fake stock data with variable latency and occasional 500s,
    so the Beyla/Grafana dashboard has something interesting to show."""
    delay = random.lognormvariate(-2, 1.5)
    time.sleep(delay)

    if random.random() < 0.02:
        response.status_code = 500
        return {"error": "inventory service unavailable"}

    return {"item": random.choice(ITEMS), "stock": random.randint(0, 100)}


@app.get("/health")
async def health():
    return {"status": "ok"}
