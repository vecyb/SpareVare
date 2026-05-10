"""
Kassalapp Proxy – kjør på Render.com (gratis)
Videresender forespørsler til Kassalapp API med riktig Bearer token.

Deploy på render.com:
1. Opprett ny "Web Service"
2. Koble til GitHub-repo med denne filen
3. Build command: pip install -r requirements_proxy.txt
4. Start command: uvicorn proxy:app --host 0.0.0.0 --port $PORT
"""

import os
import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

KASSALAPP_KEY = "XtpH4ZI1stdvqogYHzz5iyFoRKW89zGsTvMdtvvX"
KASSALAPP_BASE = "https://kassal.app/api/v1"

app = FastAPI(title="Kassalapp Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "Authorization": f"Bearer {KASSALAPP_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/products")
async def search_products(
    search: str = Query(...),
    size: int = Query(20),
    unique: str = Query("true"),
    sort: str = Query("name_asc"),
):
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{KASSALAPP_BASE}/products",
            headers=HEADERS,
            params={"search": search, "size": size, "unique": unique, "sort": sort},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@app.post("/products/prices-bulk")
async def bulk_prices(payload: dict):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{KASSALAPP_BASE}/products/prices-bulk",
            headers=HEADERS,
            json=payload,
        )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
