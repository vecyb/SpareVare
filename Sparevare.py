"""
Handlekurv Optimizer
Kjør med: streamlit run app.py
"""

import time
import json
import uuid
from datetime import datetime
from typing import Optional

import requests
import pandas as pd
import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# KONFIGURASJON – hardkodet
# ══════════════════════════════════════════════════════════════════════════════

KASSALAPP_API_KEY = "XtpH4ZI1stdvqogYHzz5iyFoRKW89zGsTvMdtvvX"
SUPABASE_URL      = "https://liptedpuxhifwqkiglpn.supabase.co"
SUPABASE_KEY      = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxpcHRlZHB1eGhpZndxa2lnbHBuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgxNjUxNzMsImV4cCI6MjA5Mzc0MTE3M30.tRQgdqF0DAJRcrcNifRGgMo4gRwmVNdIiUdvBYETDgg"

# ══════════════════════════════════════════════════════════════════════════════
# KASSALAPP API
# ══════════════════════════════════════════════════════════════════════════════

BASE_URL = "https://kassal.app/api/v1"

STORE_NAMES = {
    "REMA_1000":  "REMA 1000",
    "KIWI":       "KIWI",
    "SPAR_NO":    "SPAR",
    "MENY_NO":    "Meny",
    "BUNNPRIS":   "Bunnpris",
    "COOP_EXTRA": "Coop Extra",
    "COOP_OBS":   "Obs",
    "COOP_MEGA":  "Coop Mega",
    "COOP_PRIX":  "Coop Prix",
    "JOKER_NO":   "Joker",
    "ODA_NO":     "Oda",
}

STORE_EMOJI = {
    "REMA_1000":  "🔴",
    "KIWI":       "🟡",
    "SPAR_NO":    "🟢",
    "MENY_NO":    "🔵",
    "BUNNPRIS":   "🟠",
    "COOP_EXTRA": "🟣",
    "COOP_OBS":   "⚫",
    "COOP_MEGA":  "🟤",
    "COOP_PRIX":  "🔴",
    "JOKER_NO":   "🃏",
    "ODA_NO":     "📦",
}


class KassalappClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._last_call = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)
        self._last_call = time.time()

    def _get(self, endpoint: str, params: dict = None) -> dict:
        self._throttle()
        try:
            resp = self.session.get(
                f"{BASE_URL}/{endpoint.lstrip('/')}",
                params=params,
                timeout=15,
            )
            if resp.status_code == 401:
                st.error("API-nøkkel ugyldig (401). Kontakt admin.")
                return {}
            if resp.status_code == 429:
                st.warning("For mange forespørsler – vent litt og prøv igjen.")
                return {}
            if resp.status_code == 422:
                st.warning("Ugyldig søk. Prøv et annet søkeord.")
                return {}
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            st.error("Tidsavbrudd – Kassalapp svarte ikke. Prøv igjen.")
            return {}
        except requests.exceptions.ConnectionError:
            st.error("Nettverksfeil – sjekk internettforbindelsen.")
            return {}
        except Exception as e:
            st.error(f"Uventet feil: {type(e).__name__}")
            return {}

    def _post(self, endpoint: str, payload: dict) -> dict:
        self._throttle()
        try:
            resp = self.session.post(
                f"{BASE_URL}/{endpoint.lstrip('/')}",
                json=payload,
                timeout=20,
            )
            if resp.status_code == 401:
                st.error("API-nøkkel ugyldig (401). Kontakt admin.")
                return {}
            if resp.status_code == 429:
                st.warning("For mange forespørsler – vent litt og prøv igjen.")
                return {}
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            st.error("Tidsavbrudd ved henting av priser.")
            return {}
        except Exception as e:
            st.error(f"Uventet feil: {type(e).__name__}")
            return {}

    def search_products(self, query: str, size: int = 20) -> list[dict]:
        if not query or not query.strip():
            return []
        data = self._get("/products", {
            "search": query.strip(),
            "size": size,
            "unique": "true",
            "sort": "name_asc",
        })
        return data.get("data", []) if data else []

    def get_bulk_prices(self, eans: list[str]) -> list[dict]:
        results = []
        for i in range(0, len(eans), 100):
            batch = eans[i:i+100]
            data = self._post("/products/prices-bulk", {
                "eans": batch,
                "days": 7,
                "aggregation": "min",
            })
            if data:
                results.extend(data.get("data", []))
        return results


# ══════════════════════════════════════════════════════════════════════════════
# SUPABASE DATABASE
# ══════════════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self):
        self._sb = None
        try:
            from supabase import create_client
            self._sb = create_client(SUPABASE_URL, SUPABASE_KEY)
        except Exception as e:
            st.warning(f"Database ikke tilgjengelig: {e}")

    def _ok(self) -> bool:
        return self._sb is not None

    def create_handlekurv(self, name: str) -> Optional[dict]:
        if not self._ok():
            return None
        try:
            row = {"id": str(uuid.uuid4()), "name": name, "created_at": datetime.utcnow().isoformat()}
            self._sb.table("handlekurver").insert(row).execute()
            row["items"] = []
            return row
        except Exception as e:
            st.error(f"Kunne ikke opprette handlekurv: {e}")
            return None

    def get_handlekurver(self) -> list[dict]:
        if not self._ok():
            return []
        try:
            kurver = self._sb.table("handlekurver").select("*").order("created_at", desc=False).execute().data or []
            items  = self._sb.table("handlekurv_items").select("*").execute().data or []
            for k in kurver:
                k["items"] = sorted(
                    [i for i in items if i["kurv_id"] == k["id"]],
                    key=lambda x: x.get("added_at", ""),
                )
            return kurver
        except Exception as e:
            st.error(f"Kunne ikke hente handlekurver: {e}")
            return []

    def delete_handlekurv(self, kurv_id: str):
        if not self._ok():
            return
        try:
            self._sb.table("handlekurv_items").delete().eq("kurv_id", kurv_id).execute()
            self._sb.table("handlekurver").delete().eq("id", kurv_id).execute()
        except Exception as e:
            st.error(f"Feil ved sletting: {e}")

    def add_item(self, kurv_id: str, name: str, ean: Optional[str], brand: Optional[str]) -> Optional[dict]:
        if not self._ok():
            return None
        try:
            row = {
                "id": str(uuid.uuid4()), "kurv_id": kurv_id,
                "name": name, "ean": ean, "brand": brand,
                "quantity": 1, "added_at": datetime.utcnow().isoformat(),
            }
            self._sb.table("handlekurv_items").insert(row).execute()
            return row
        except Exception as e:
            st.error(f"Feil ved å legge til vare: {e}")
            return None

    def update_quantity(self, item_id: str, quantity: int):
        if not self._ok():
            return
        try:
            self._sb.table("handlekurv_items").update({"quantity": quantity}).eq("id", item_id).execute()
        except Exception:
            pass

    def remove_item(self, item_id: str):
        if not self._ok():
            return
        try:
            self._sb.table("handlekurv_items").delete().eq("id", item_id).execute()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# PRISOPTIMALISERING
# ══════════════════════════════════════════════════════════════════════════════

class Optimizer:
    def __init__(self, bulk_prices: list[dict], basket_items: list[dict], preferred: list[str]):
        self.basket_items = basket_items
        self._prices: dict[str, dict[str, float]] = {}

        for p in bulk_prices:
            ean = p.get("ean", "")
            self._prices[ean] = {
                s["store"]: float(s["current_price"])
                for s in p.get("stores", [])
                if s.get("current_price") is not None and s.get("store")
            }

        all_stores = {s for prices in self._prices.values() for s in prices}
        preferred_set = set(preferred) & all_stores
        self.active_stores = preferred_set if preferred_set else all_stores

    def _name(self, code: str) -> str:
        return STORE_NAMES.get(code, code)

    def _emoji(self, code: str) -> str:
        return STORE_EMOJI.get(code, "🏪")

    def rank_stores(self) -> list[dict]:
        results = []
        for code in self.active_stores:
            total, found, missing = 0.0, 0, []
            for item in self.basket_items:
                ean, qty = item.get("ean"), item.get("quantity", 1)
                if not ean:
                    continue
                price = self._prices.get(ean, {}).get(code)
                if price is not None:
                    total += price * qty
                    found += 1
                else:
                    missing.append(item["name"])
            if found > 0:
                results.append({
                    "code": code,
                    "name": self._name(code),
                    "emoji": self._emoji(code),
                    "total": round(total, 2),
                    "found": found,
                    "missing": missing,
                })
        results.sort(key=lambda x: x["total"])
        return results

    def optimize_split(self, max_stores: int) -> list[dict]:
        assignments = []
        for item in self.basket_items:
            ean, qty = item.get("ean"), item.get("quantity", 1)
            if not ean:
                continue
            valid = {c: self._prices.get(ean, {}).get(c) for c in self.active_stores}
            valid = {k: v for k, v in valid.items() if v is not None}
            if not valid:
                continue
            best = min(valid, key=valid.get)
            assignments.append({
                "ean": ean, "name": item["name"], "quantity": qty,
                "store_code": best, "store_name": self._name(best),
                "store_emoji": self._emoji(best),
                "price": round(valid[best] * qty, 2),
                "_all": valid,
            })

        while len({a["store_code"] for a in assignments}) > max_stores:
            unique = {a["store_code"] for a in assignments}
            counts = {s: sum(1 for a in assignments if a["store_code"] == s) for s in unique}
            smallest = min(counts, key=counts.get)
            remaining = unique - {smallest}
            for a in assignments:
                if a["store_code"] == smallest:
                    cands = {s: a["_all"][s] for s in remaining if s in a["_all"]}
                    if cands:
                        new = min(cands, key=cands.get)
                        a.update({"store_code": new, "store_name": self._name(new),
                                  "store_emoji": self._emoji(new),
                                  "price": round(cands[new] * a["quantity"], 2)})
            if not remaining:
                break

        for a in assignments:
            a.pop("_all", None)
        return assignments

    def price_matrix(self) -> Optional[pd.DataFrame]:
        rows, idx = [], []
        for item in self.basket_items:
            ean = item.get("ean")
            if not ean or not self._prices.get(ean):
                continue
            row = {}
            for code in sorted(self.active_stores):
                p = self._prices[ean].get(code)
                row[self._name(code)] = round(p, 2) if p else None
            rows.append(row)
            idx.append(item["name"][:35])
        return pd.DataFrame(rows, index=idx) if rows else None


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT APP
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Handlekurv Optimizer",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 2rem; padding-bottom: 3rem; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: #0f0f13;
    border-right: 1px solid #1e1e2e;
}
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
[data-testid="stSidebar"] .stMarkdown h2 {
    font-family: 'Syne', sans-serif;
    font-size: 1rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #888 !important;
    margin-bottom: 1rem;
}

/* App background */
.stApp { background: #0a0a0f; }

/* Main heading */
.app-title {
    font-family: 'Syne', sans-serif;
    font-size: 2.8rem;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.02em;
    line-height: 1;
    margin-bottom: 0.2rem;
}
.app-sub {
    font-size: 1rem;
    color: #666;
    margin-bottom: 2.5rem;
    font-weight: 300;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 1px solid #1e1e2e;
    gap: 0;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Syne', sans-serif;
    font-size: 0.85rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    color: #555 !important;
    padding: 0.75rem 1.5rem;
    border-bottom: 2px solid transparent;
    background: transparent;
}
.stTabs [aria-selected="true"] {
    color: #fff !important;
    border-bottom: 2px solid #7c5cfc;
    background: transparent;
}

/* Input fields */
.stTextInput input, .stNumberInput input {
    background: #13131a !important;
    border: 1px solid #2a2a3a !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-family: 'DM Sans', sans-serif !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: #7c5cfc !important;
    box-shadow: 0 0 0 2px rgba(124,92,252,0.2) !important;
}

/* Buttons */
.stButton button {
    background: #7c5cfc !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.05em !important;
    padding: 0.6rem 1.2rem !important;
    transition: all 0.2s ease !important;
}
.stButton button:hover {
    background: #6a4ae8 !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 20px rgba(124,92,252,0.4) !important;
}
.stButton button[kind="secondary"] {
    background: #1e1e2e !important;
    color: #888 !important;
}
.stButton button[kind="secondary"]:hover {
    background: #2a2a3a !important;
    color: #fff !important;
}

/* Cards */
.card {
    background: #13131a;
    border: 1px solid #1e1e2e;
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
    transition: border-color 0.2s;
}
.card:hover { border-color: #2a2a3a; }
.card-best {
    border-color: #7c5cfc;
    background: linear-gradient(135deg, #13131a 0%, #1a1428 100%);
}

/* Badges */
.badge-best {
    background: #7c5cfc;
    color: #fff;
    padding: 0.2rem 0.8rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 700;
    font-family: 'Syne', sans-serif;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
.badge-saving {
    background: #1a3a2a;
    color: #4ade80;
    border: 1px solid #4ade80;
    padding: 0.2rem 0.8rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 700;
    font-family: 'Syne', sans-serif;
}

/* Product row */
.product-row {
    background: #13131a;
    border: 1px solid #1e1e2e;
    border-radius: 10px;
    padding: 0.7rem 1rem;
    margin-bottom: 0.5rem;
}

/* Store tag */
.store-tag {
    display: inline-block;
    background: #1e1e2e;
    border-radius: 6px;
    padding: 0.15rem 0.5rem;
    font-size: 0.75rem;
    color: #888;
    font-family: 'Syne', sans-serif;
}

/* Savings box */
.savings-box {
    background: linear-gradient(135deg, #0d2818, #0a1f12);
    border: 1px solid #2d6a4a;
    border-radius: 14px;
    padding: 1.2rem 1.6rem;
    margin: 1rem 0;
}
.savings-amount {
    font-family: 'Syne', sans-serif;
    font-size: 2.2rem;
    font-weight: 800;
    color: #4ade80;
}

/* Multiselect */
[data-baseweb="tag"] {
    background: #7c5cfc !important;
    border-radius: 6px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #1e1e2e;
}

/* Expander */
.streamlit-expanderHeader {
    background: #13131a !important;
    border: 1px solid #1e1e2e !important;
    border-radius: 10px !important;
    color: #fff !important;
    font-family: 'DM Sans', sans-serif !important;
}

/* Divider */
hr { border-color: #1e1e2e !important; }

/* Text colors */
p, label, .stMarkdown { color: #c0c0c0; }
h1, h2, h3 { color: #fff; font-family: 'Syne', sans-serif; }

/* Success / info / warning */
.stSuccess { background: #0d2818 !important; border-color: #4ade80 !important; }
.stInfo    { background: #0d1a2e !important; border-color: #60a5fa !important; }

/* Number input buttons */
.stNumberInput button {
    background: #1e1e2e !important;
    padding: 0.2rem 0.4rem !important;
    min-height: unset !important;
}
</style>
""", unsafe_allow_html=True)

# ── Session state init ─────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    return KassalappClient(KASSALAPP_API_KEY)

@st.cache_resource
def get_db():
    return Database()

client = get_client()
db     = get_db()

for k, v in {
    "search_results": [],
    "favoritter": ["REMA_1000", "KIWI", "SPAR_NO", "BUNNPRIS"],
    "last_query": "",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar: kun butikkvalg ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🏪 Mine butikker")
    st.caption("Velg butikkene du har i nærheten")

    st.session_state.favoritter = st.multiselect(
        "Butikker",
        options=list(STORE_NAMES.keys()),
        default=st.session_state.favoritter,
        format_func=lambda x: f"{STORE_EMOJI.get(x, '')} {STORE_NAMES.get(x, x)}",
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("Priser fra Kassalapp · Oppdateres daglig")

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown('<p class="app-title">🛒 Handlekurv</p>', unsafe_allow_html=True)
st.markdown('<p class="app-sub">Finn billigste butikk – eller kombiner flere og spar mer</p>', unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["SØK ETTER VARER", "MINE HANDLEKURVER", "PRISANALYSE"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – SØK
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("### Søk etter varer")

    c1, c2 = st.columns([5, 1])
    with c1:
        query = st.text_input(
            "søk",
            placeholder="Skriv et produktnavn, f.eks. melk, havregryn, ost ...",
            label_visibility="collapsed",
            key="search_input",
        )
    with c2:
        do_search = st.button("Søk →", use_container_width=True)

    # Søk ved enter eller knapp
    if (do_search or (query and query != st.session_state.last_query)) and query.strip():
        st.session_state.last_query = query
        with st.spinner("Søker..."):
            st.session_state.search_results = client.search_products(query)

    results = st.session_state.search_results
    if results:
        # Velg hvilken kurv
        kurver = db.get_handlekurver()
        kurv_map = {k["name"]: k["id"] for k in kurver}

        if kurv_map:
            valgt_kurv = st.selectbox(
                "Legg til i",
                options=list(kurv_map.keys()),
                format_func=lambda x: f"🧺 {x}",
            )
        else:
            st.info("💡 Opprett en handlekurv i **Mine handlekurver** for å legge til varer")
            valgt_kurv = None

        st.markdown(f"<p style='color:#666;font-size:0.85rem;margin:1rem 0 0.5rem'>{len(results)} resultater for «{st.session_state.last_query}»</p>", unsafe_allow_html=True)

        for p in results:
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 0.7])
                with c1:
                    name = p.get("name", "Ukjent")
                    brand = p.get("brand") or ""
                    store = p.get("store", {}).get("name", "") if isinstance(p.get("store"), dict) else ""
                    st.markdown(f"**{name}**")
                    tags = " ".join(f'<span class="store-tag">{t}</span>' for t in [brand, store] if t)
                    if tags:
                        st.markdown(tags, unsafe_allow_html=True)
                with c2:
                    pris = p.get("current_price")
                    if pris:
                        st.markdown(f"<p style='font-family:Syne;font-weight:700;font-size:1.1rem;color:#fff;margin:0.4rem 0 0'>{pris:.2f} kr</p>", unsafe_allow_html=True)
                    else:
                        st.markdown("<p style='color:#555;margin:0.4rem 0 0'>–</p>", unsafe_allow_html=True)
                with c3:
                    ean = p.get("ean") or ""
                    if ean:
                        st.markdown(f"<p style='color:#444;font-size:0.75rem;margin:0.5rem 0 0'>EAN {ean}</p>", unsafe_allow_html=True)
                with c4:
                    if st.button("＋", key=f"add_{p.get('id', uuid.uuid4())}"):
                        if valgt_kurv and kurv_map.get(valgt_kurv):
                            db.add_item(
                                kurv_map[valgt_kurv],
                                p.get("name", ""),
                                p.get("ean"),
                                p.get("brand"),
                            )
                            st.toast(f"✅ {p.get('name', '')} lagt til!", icon="✅")
                        else:
                            st.warning("Velg en handlekurv først")
                st.divider()

    elif st.session_state.last_query and not results:
        st.markdown("<p style='color:#555;text-align:center;padding:2rem'>Ingen resultater. Prøv et annet søkeord.</p>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – HANDLEKURVER
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("### Mine handlekurver")

    c1, c2 = st.columns([4, 1])
    with c1:
        ny_navn = st.text_input(
            "ny kurv",
            placeholder="Gi handlekurven et navn, f.eks. Ukeshandel ...",
            label_visibility="collapsed",
            key="ny_kurv_input",
        )
    with c2:
        if st.button("Opprett →", use_container_width=True):
            if ny_navn.strip():
                db.create_handlekurv(ny_navn.strip())
                st.rerun()
            else:
                st.warning("Skriv inn et navn")

    st.markdown("<br>", unsafe_allow_html=True)

    kurver = db.get_handlekurver()
    if not kurver:
        st.markdown("""
        <div style="text-align:center;padding:3rem;color:#444">
            <p style="font-size:3rem;margin:0">🧺</p>
            <p style="font-family:Syne;font-size:1.1rem;color:#666;margin:0.5rem 0">Ingen handlekurver ennå</p>
            <p style="font-size:0.85rem">Opprett en ovenfor og søk etter varer i Søk-fanen</p>
        </div>
        """, unsafe_allow_html=True)

    for kurv in kurver:
        items = kurv.get("items", [])
        antall = len(items)

        with st.expander(f"🧺  {kurv['name']}  ·  {antall} {'vare' if antall == 1 else 'varer'}", expanded=True):
            if not items:
                st.markdown("<p style='color:#444;font-size:0.9rem'>Ingen varer. Søk etter produkter i Søk-fanen.</p>", unsafe_allow_html=True)
            else:
                for item in items:
                    c1, c2, c3 = st.columns([4, 1.2, 0.6])
                    with c1:
                        brand = item.get("brand") or ""
                        st.markdown(f"**{item['name']}**")
                        if brand:
                            st.markdown(f"<span class='store-tag'>{brand}</span>", unsafe_allow_html=True)
                    with c2:
                        ny_ant = st.number_input(
                            "ant",
                            min_value=1,
                            max_value=99,
                            value=int(item.get("quantity", 1)),
                            key=f"qty_{item['id']}",
                            label_visibility="collapsed",
                        )
                        if ny_ant != item.get("quantity", 1):
                            db.update_quantity(item["id"], ny_ant)
                    with c3:
                        if st.button("✕", key=f"del_{item['id']}"):
                            db.remove_item(item["id"])
                            st.rerun()

            st.markdown("<br>", unsafe_allow_html=True)
            ca, cb = st.columns([1, 1])
            with ca:
                if st.button("📊  Analyser priser", key=f"an_{kurv['id']}", use_container_width=True):
                    st.session_state["analyser_id"] = kurv["id"]
                    st.toast("Åpne Prisanalyse-fanen →")
            with cb:
                if st.button("Slett kurv", key=f"dk_{kurv['id']}", use_container_width=True):
                    db.delete_handlekurv(kurv["id"])
                    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – PRISANALYSE
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### Prisanalyse")

    kurver = db.get_handlekurver()
    if not kurver:
        st.markdown("""
        <div style="text-align:center;padding:3rem;color:#444">
            <p style="font-size:3rem;margin:0">📊</p>
            <p style="font-family:Syne;font-size:1.1rem;color:#666;margin:0.5rem 0">Ingen handlekurver å analysere</p>
            <p style="font-size:0.85rem">Opprett en handlekurv og legg til varer først</p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # Forhåndsvelg kurv om klikket fra tab2
    default_idx = 0
    if "analyser_id" in st.session_state:
        ids = [k["id"] for k in kurver]
        if st.session_state["analyser_id"] in ids:
            default_idx = ids.index(st.session_state["analyser_id"])

    valgt = st.selectbox(
        "Velg handlekurv",
        options=kurver,
        index=default_idx,
        format_func=lambda k: f"🧺 {k['name']} ({len(k.get('items',[]))} varer)",
    )

    c1, c2 = st.columns([2, 2])
    with c1:
        kombiner = st.toggle("Kombiner flere butikker", value=True)
    with c2:
        if kombiner:
            maks = st.select_slider("Maks antall butikker", options=[2, 3, 4, 5], value=3)
        else:
            maks = 1

    if st.button("🚀  Kjør prisanalyse", type="primary", use_container_width=True):
        items = valgt.get("items", [])
        eans  = [i["ean"] for i in items if i.get("ean")]

        if not items:
            st.warning("Handlekurven er tom.")
        elif not eans:
            st.warning("Ingen av varene har EAN-koder. Søk etter produkter via Søk-fanen.")
        elif not st.session_state.favoritter:
            st.warning("Velg minst én butikk i sidepanelet.")
        else:
            with st.spinner(f"Henter priser for {len(eans)} varer..."):
                priser = client.get_bulk_prices(eans)

            if not priser:
                st.error("Klarte ikke hente priser. Prøv igjen.")
            else:
                opt     = Optimizer(priser, items, st.session_state.favoritter)
                ranking = opt.rank_stores()

                if not ranking:
                    st.warning("Ingen prisdata funnet for valgte butikker og varer.")
                    st.stop()

                st.markdown("---")

                # ── Beste enkeltbutikk ─────────────────────────────────────
                st.markdown("#### 🏪 Beste enkeltbutikk")
                medals = ["🥇", "🥈", "🥉", "4.", "5."]

                for i, r in enumerate(ranking[:5]):
                    is_best = i == 0
                    card_class = "card card-best" if is_best else "card"
                    c1, c2, c3 = st.columns([3, 1.5, 2])
                    with c1:
                        st.markdown(f"**{medals[i]} {r['emoji']} {r['name']}**")
                        funnet = r['found']
                        totalt = len(eans)
                        farge  = "#4ade80" if funnet == totalt else "#f59e0b"
                        st.markdown(f"<p style='font-size:0.8rem;color:{farge};margin:0'>{funnet}/{totalt} varer funnet</p>", unsafe_allow_html=True)
                    with c2:
                        st.markdown(f"<p style='font-family:Syne;font-weight:700;font-size:1.3rem;color:#fff;margin:0.3rem 0'>{r['total']:.2f} kr</p>", unsafe_allow_html=True)
                    with c3:
                        if is_best:
                            st.markdown('<span class="badge-best">Billigst</span>', unsafe_allow_html=True)
                        else:
                            diff = r["total"] - ranking[0]["total"]
                            st.markdown(f"<p style='color:#ef4444;font-size:0.9rem;margin:0.3rem 0'>+{diff:.2f} kr</p>", unsafe_allow_html=True)
                    st.divider()

                # ── Kombinert optimalisering ───────────────────────────────
                if kombiner and maks > 1:
                    st.markdown(f"#### 🔀 Optimal fordeling på {maks} butikker")
                    resultat  = opt.optimize_split(max_stores=maks)

                    if resultat:
                        total_opt  = sum(r["price"] for r in resultat)
                        besparelse = ranking[0]["total"] - total_opt

                        if besparelse > 0.5:
                            st.markdown(f"""
                            <div class="savings-box">
                                <p style="color:#4ade80;font-size:0.8rem;font-family:Syne;letter-spacing:0.1em;text-transform:uppercase;margin:0">Du sparer</p>
                                <p class="savings-amount">{besparelse:.2f} kr</p>
                                <p style="color:#666;font-size:0.85rem;margin:0">mot å handle alt på {ranking[0]['name']}</p>
                            </div>
                            """, unsafe_allow_html=True)
                        else:
                            st.info(f"Å kombinere butikker gir minimal besparelse ({besparelse:.2f} kr). Det er enklest å handle alt på **{ranking[0]['name']}**.")

                        # Gruppe per butikk
                        grupper: dict = {}
                        for r in resultat:
                            grupper.setdefault(r["store_code"], []).append(r)

                        col_list = st.columns(min(len(grupper), 3))
                        for idx, (code, varer) in enumerate(grupper.items()):
                            sub = sum(v["price"] for v in varer)
                            col = col_list[idx % len(col_list)]
                            with col:
                                st.markdown(f"""
                                <div class="card">
                                    <p style="font-family:Syne;font-weight:700;font-size:1rem;color:#fff;margin:0 0 0.5rem">
                                        {STORE_EMOJI.get(code,'')} {STORE_NAMES.get(code, code)}
                                    </p>
                                    <p style="font-family:Syne;font-size:1.4rem;font-weight:800;color:#7c5cfc;margin:0 0 0.8rem">{sub:.2f} kr</p>
                                """, unsafe_allow_html=True)
                                for v in varer:
                                    st.markdown(f"<p style='font-size:0.85rem;color:#aaa;margin:0.2rem 0'>· {v['name']} × {v['quantity']} — {v['price']:.2f} kr</p>", unsafe_allow_html=True)
                                st.markdown("</div>", unsafe_allow_html=True)

                # ── Prismatrise ────────────────────────────────────────────
                st.markdown("#### 📋 Prismatrise")
                st.caption("Grønn = billigst per vare")
                matrise = opt.price_matrix()
                if matrise is not None:
                    st.dataframe(
                        matrise.style
                            .highlight_min(axis=1, color="#1a3a2a")
                            .format(lambda x: f"{x:.2f} kr" if x else "–"),
                        use_container_width=True,
                        height=min(400, 40 + 35 * len(matrise)),
                    )
                else:
                    st.caption("Ingen prisdata tilgjengelig for prismatrise.")
