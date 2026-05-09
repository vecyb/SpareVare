"""
Handlekurv Optimizer
Kjør med: streamlit run app.py
"""

import time
import uuid
from datetime import datetime
from typing import Optional

import requests
import pandas as pd
import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# KONFIGURASJON
# ══════════════════════════════════════════════════════════════════════════════

KASSALAPP_API_KEY = "XtpH4ZI1stdvqogYHzz5iyFoRKW89zGsTvMdtvvX"
SUPABASE_URL      = "https://liptedpuxhifwqkiglpn.supabase.co"
SUPABASE_KEY      = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6"
    "ImxpcHRlZHB1eGhpZndxa2lnbHBuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgxNjUxNzMs"
    "ImV4cCI6MjA5Mzc0MTE3M30.tRQgdqF0DAJRcrcNifRGgMo4gRwmVNdIiUdvBYETDgg"
)

# ══════════════════════════════════════════════════════════════════════════════
# BUTIKK-METADATA
# ══════════════════════════════════════════════════════════════════════════════

STORES = {
    "REMA_1000":  {"name": "REMA 1000",  "emoji": "🔴"},
    "KIWI":       {"name": "KIWI",        "emoji": "🟡"},
    "SPAR_NO":    {"name": "SPAR",        "emoji": "🟢"},
    "MENY_NO":    {"name": "Meny",        "emoji": "🔵"},
    "BUNNPRIS":   {"name": "Bunnpris",    "emoji": "🟠"},
    "COOP_EXTRA": {"name": "Coop Extra",  "emoji": "🟣"},
    "COOP_OBS":   {"name": "Obs",         "emoji": "⚫"},
    "COOP_MEGA":  {"name": "Coop Mega",   "emoji": "🟤"},
    "COOP_PRIX":  {"name": "Coop Prix",   "emoji": "🔴"},
    "JOKER_NO":   {"name": "Joker",       "emoji": "🃏"},
    "ODA_NO":     {"name": "Oda",         "emoji": "📦"},
}

def sname(code): return STORES.get(code, {}).get("name", code)
def semoji(code): return STORES.get(code, {}).get("emoji", "🏪")

# ══════════════════════════════════════════════════════════════════════════════
# KASSALAPP API
# ══════════════════════════════════════════════════════════════════════════════

BASE_URL = "https://kassal.app/api/v1"

class KassalappClient:
    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._last = 0.0

    def _wait(self):
        d = time.time() - self._last
        if d < 0.12:
            time.sleep(0.12 - d)
        self._last = time.time()

    def _get(self, path: str, params: dict) -> Optional[dict]:
        self._wait()
        try:
            r = self.session.get(f"{BASE_URL}{path}", params=params, timeout=15)
            if r.status_code in (200, 201):
                return r.json()
            # Logg til konsoll, ikke til bruker
            print(f"[Kassalapp] {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            print(f"[Kassalapp] Feil: {e}")
            return None

    def _post(self, path: str, payload: dict) -> Optional[dict]:
        self._wait()
        try:
            r = self.session.post(f"{BASE_URL}{path}", json=payload, timeout=20)
            if r.status_code in (200, 201):
                return r.json()
            print(f"[Kassalapp POST] {r.status_code}: {r.text[:200]}")
            return None
        except Exception as e:
            print(f"[Kassalapp POST] Feil: {e}")
            return None

    def search(self, query: str, size: int = 25) -> list[dict]:
        q = query.strip()
        if not q:
            return []
        data = self._get("/products", {
            "search": q,
            "size": size,
            "unique": "true",
            "sort": "name_asc",
        })
        return data.get("data", []) if data else []

    def bulk_prices(self, eans: list[str]) -> list[dict]:
        out = []
        for i in range(0, len(eans), 100):
            data = self._post("/products/prices-bulk", {
                "eans": eans[i:i+100],
                "days": 7,
                "aggregation": "min",
            })
            if data:
                out.extend(data.get("data", []))
        return out

# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self):
        self._sb = None
        self._ok = False
        try:
            from supabase import create_client
            self._sb = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Test tilkobling
            self._sb.table("handlekurver").select("id").limit(1).execute()
            self._ok = True
        except Exception as e:
            print(f"[DB] Tilkobling feilet: {e}")
            self._ok = False

    @property
    def connected(self):
        return self._ok

    def _run(self, fn):
        """Kjør en Supabase-operasjon og returner data eller None stille."""
        try:
            return fn()
        except Exception as e:
            print(f"[DB] Feil: {e}")
            return None

    def create_kurv(self, name: str) -> Optional[dict]:
        if not self._ok:
            return None
        row = {"id": str(uuid.uuid4()), "name": name, "created_at": datetime.utcnow().isoformat()}
        self._run(lambda: self._sb.table("handlekurver").insert(row).execute())
        row["items"] = []
        return row

    def get_kurver(self) -> list[dict]:
        if not self._ok:
            return []
        res = self._run(lambda: self._sb.table("handlekurver").select("*").order("created_at").execute())
        kurver = res.data if res else []
        res2 = self._run(lambda: self._sb.table("handlekurv_items").select("*").order("added_at").execute())
        items = res2.data if res2 else []
        for k in kurver:
            k["items"] = [i for i in items if i["kurv_id"] == k["id"]]
        return kurver

    def delete_kurv(self, kid: str):
        if not self._ok:
            return
        self._run(lambda: self._sb.table("handlekurv_items").delete().eq("kurv_id", kid).execute())
        self._run(lambda: self._sb.table("handlekurver").delete().eq("id", kid).execute())

    def add_item(self, kid: str, name: str, ean: Optional[str], brand: Optional[str]) -> Optional[dict]:
        if not self._ok:
            return None
        row = {
            "id": str(uuid.uuid4()), "kurv_id": kid,
            "name": name, "ean": ean, "brand": brand or "",
            "quantity": 1, "added_at": datetime.utcnow().isoformat(),
        }
        self._run(lambda: self._sb.table("handlekurv_items").insert(row).execute())
        return row

    def set_qty(self, iid: str, qty: int):
        if not self._ok:
            return
        self._run(lambda: self._sb.table("handlekurv_items").update({"quantity": qty}).eq("id", iid).execute())

    def del_item(self, iid: str):
        if not self._ok:
            return
        self._run(lambda: self._sb.table("handlekurv_items").delete().eq("id", iid).execute())

# ══════════════════════════════════════════════════════════════════════════════
# OPTIMALISERING
# ══════════════════════════════════════════════════════════════════════════════

class Optimizer:
    def __init__(self, bulk: list[dict], items: list[dict], preferred: list[str]):
        self.items = items
        # ean → store_code → pris
        self._p: dict[str, dict[str, float]] = {}
        for p in bulk:
            ean = p.get("ean", "")
            self._p[ean] = {
                s["store"]: float(s["current_price"])
                for s in p.get("stores", [])
                if s.get("current_price") is not None and s.get("store")
            }
        all_s = {s for d in self._p.values() for s in d}
        pref  = set(preferred) & all_s
        self.active = pref if pref else all_s

    def rank(self) -> list[dict]:
        out = []
        for code in self.active:
            tot, found = 0.0, 0
            for i in self.items:
                ean, qty = i.get("ean"), i.get("quantity", 1)
                if not ean:
                    continue
                p = self._p.get(ean, {}).get(code)
                if p is not None:
                    tot += p * qty
                    found += 1
            if found:
                out.append({"code": code, "name": sname(code), "emoji": semoji(code),
                            "total": round(tot, 2), "found": found})
        out.sort(key=lambda x: x["total"])
        return out

    def split(self, max_stores: int) -> list[dict]:
        asgn = []
        for i in self.items:
            ean, qty = i.get("ean"), i.get("quantity", 1)
            if not ean:
                continue
            valid = {c: self._p.get(ean, {}).get(c) for c in self.active}
            valid = {k: v for k, v in valid.items() if v is not None}
            if not valid:
                continue
            best = min(valid, key=valid.get)
            asgn.append({"ean": ean, "name": i["name"], "qty": qty,
                         "code": best, "price": round(valid[best] * qty, 2), "_v": valid})

        while len({a["code"] for a in asgn}) > max_stores:
            unique = {a["code"] for a in asgn}
            counts = {s: sum(1 for a in asgn if a["code"] == s) for s in unique}
            smallest = min(counts, key=counts.get)
            rest = unique - {smallest}
            if not rest:
                break
            for a in asgn:
                if a["code"] == smallest:
                    cands = {s: a["_v"][s] for s in rest if s in a["_v"]}
                    if cands:
                        new = min(cands, key=cands.get)
                        a["code"]  = new
                        a["price"] = round(cands[new] * a["qty"], 2)

        for a in asgn:
            a.pop("_v", None)
        return asgn

    def matrix(self) -> Optional[pd.DataFrame]:
        rows, idx = [], []
        for i in self.items:
            ean = i.get("ean")
            if not ean or not self._p.get(ean):
                continue
            rows.append({sname(c): self._p[ean].get(c) for c in sorted(self.active)})
            idx.append(i["name"][:35])
        return pd.DataFrame(rows, index=idx) if rows else None

# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT APP
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Handlekurv", page_icon="🛒", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;1,9..40,300&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.8rem; max-width: 1100px; }
.stApp { background: #080810; }

/* Sidebar */
[data-testid="stSidebar"] { background: #0d0d18; border-right: 1px solid #1a1a2e; }
[data-testid="stSidebar"] * { color: #ccc !important; }
[data-testid="stSidebar"] h3 { font-family:'Syne',sans-serif; font-size:0.75rem; letter-spacing:0.15em; text-transform:uppercase; color:#555 !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background:transparent; gap:0; border-bottom:1px solid #1a1a2e; }
.stTabs [data-baseweb="tab"] { font-family:'Syne',sans-serif; font-size:0.78rem; font-weight:600; letter-spacing:0.08em; color:#444 !important; padding:0.7rem 1.4rem; background:transparent; border-bottom:2px solid transparent; }
.stTabs [aria-selected="true"] { color:#fff !important; border-bottom:2px solid #6c63ff; }
.stTabs [data-baseweb="tab-panel"] { padding-top:1.5rem; }

/* Inputs */
.stTextInput input { background:#0f0f1a !important; border:1px solid #22223a !important; border-radius:10px !important; color:#fff !important; font-size:1rem !important; padding:0.6rem 1rem !important; }
.stTextInput input:focus { border-color:#6c63ff !important; box-shadow:0 0 0 3px rgba(108,99,255,0.15) !important; }
.stNumberInput input { background:#0f0f1a !important; border:1px solid #22223a !important; border-radius:8px !important; color:#fff !important; }

/* Buttons */
.stButton > button {
    font-family:'Syne',sans-serif !important; font-weight:700 !important;
    font-size:0.82rem !important; letter-spacing:0.06em !important;
    border-radius:10px !important; border:none !important;
    padding:0.55rem 1.1rem !important;
    background:#6c63ff !important; color:#fff !important;
    transition:all 0.15s ease !important;
}
.stButton > button:hover { background:#5a52e0 !important; transform:translateY(-1px); box-shadow:0 6px 20px rgba(108,99,255,0.35) !important; }
.stButton > button[kind="secondary"] { background:#1a1a2e !important; color:#888 !important; }
.stButton > button[kind="secondary"]:hover { background:#22223a !important; color:#ccc !important; transform:none; box-shadow:none !important; }

/* Cards */
.card { background:#0f0f1a; border:1px solid #1a1a2e; border-radius:12px; padding:1rem 1.2rem; margin-bottom:0.6rem; }
.card-best { background:linear-gradient(135deg,#0f0f1a,#16123a); border-color:#6c63ff; }

/* Merker */
.tag { display:inline-block; background:#1a1a2e; border-radius:5px; padding:0.1rem 0.5rem; font-size:0.72rem; color:#666; }
.badge-best { background:#6c63ff; color:#fff; padding:0.2rem 0.7rem; border-radius:20px; font-size:0.72rem; font-family:'Syne',sans-serif; font-weight:700; letter-spacing:0.05em; }
.savings-box { background:linear-gradient(135deg,#091a12,#0b1f14); border:1px solid #1e4d33; border-radius:14px; padding:1.2rem 1.6rem; margin:1rem 0; }
.savings-num { font-family:'Syne',sans-serif; font-size:2.4rem; font-weight:800; color:#4ade80; line-height:1; }

/* Dividers */
hr { border-color:#1a1a2e !important; margin:0.8rem 0 !important; }

/* Text */
p, label { color:#bbb; }
h1,h2,h3,h4 { color:#fff; font-family:'Syne',sans-serif; }

/* Multiselect tags */
[data-baseweb="tag"] { background:#6c63ff !important; }
[data-baseweb="tag"] span { color:#fff !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border-radius:12px; overflow:hidden; border:1px solid #1a1a2e; }

/* Expander */
details summary { background:#0f0f1a !important; border:1px solid #1a1a2e !important; border-radius:10px !important; color:#ccc !important; padding:0.7rem 1rem !important; font-family:'DM Sans',sans-serif; }
details[open] summary { border-radius:10px 10px 0 0 !important; }
details > div { background:#0a0a14 !important; border:1px solid #1a1a2e !important; border-top:none !important; border-radius:0 0 10px 10px !important; padding:1rem !important; }

/* Select box */
[data-baseweb="select"] > div { background:#0f0f1a !important; border-color:#22223a !important; border-radius:10px !important; }
[data-baseweb="select"] * { color:#ccc !important; }

/* Toggle */
.stToggle label { color:#ccc !important; }

/* Success toasts */
.stToast { background:#0f1a14 !important; border:1px solid #2d6a4a !important; }
</style>
""", unsafe_allow_html=True)

# ── Initialiser ressurser ──────────────────────────────────────────────────────
@st.cache_resource
def init():
    return KassalappClient(KASSALAPP_API_KEY), Database()

client, db = init()

for k, v in {
    "favoritter": ["REMA_1000", "KIWI", "SPAR_NO", "BUNNPRIS"],
    "search_results": [],
    "last_q": "",
    "søk_aktiv": False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Vis DB-status øverst om ikke tilkoblet ─────────────────────────────────────
if not db.connected:
    st.error("⚠️ Databasen er ikke satt opp ennå. Kjør SQL-skjemaet i Supabase SQL Editor.")
    with st.expander("Vis SQL som må kjøres"):
        st.code("""
CREATE TABLE IF NOT EXISTS handlekurver (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS handlekurv_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kurv_id UUID NOT NULL REFERENCES handlekurver(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    ean TEXT,
    brand TEXT,
    quantity INTEGER DEFAULT 1,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE handlekurver DISABLE ROW LEVEL SECURITY;
ALTER TABLE handlekurv_items DISABLE ROW LEVEL SECURITY;
        """, language="sql")

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🏪 Mine butikker")
    st.caption("Velg butikkene du har i nærheten. Brukes til å filtrere prisanalysen.")
    st.session_state.favoritter = st.multiselect(
        "butikker",
        options=list(STORES.keys()),
        default=st.session_state.favoritter,
        format_func=lambda x: f"{STORES[x]['emoji']} {STORES[x]['name']}",
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("📡 Priser fra Kassalapp · Oppdateres daglig")

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<p style="font-family:Syne;font-size:2.6rem;font-weight:800;color:#fff;letter-spacing:-0.02em;margin:0;line-height:1">
  🛒 Handlekurv Optimizer
</p>
<p style="color:#555;font-size:0.95rem;margin:0.3rem 0 2rem;font-weight:300">
  Finn billigste butikk — eller kombiner flere og spar mer
</p>
""", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["SØK ETTER VARER", "MINE HANDLEKURVER", "PRISANALYSE"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – SØK
# ══════════════════════════════════════════════════════════════════════════════
with tab1:

    c1, c2 = st.columns([5, 1])
    with c1:
        query = st.text_input(
            "søk",
            placeholder="Skriv produktnavn, f.eks.  melk  ·  havregryn  ·  ost ...",
            label_visibility="collapsed",
        )
    with c2:
        søk_klikk = st.button("Søk →", use_container_width=True)

    # Utfør søk
    if søk_klikk and query.strip():
        st.session_state.last_q = query.strip()
        with st.spinner("Søker..."):
            res = client.search(query.strip())
        if res is None or len(res) == 0:
            st.session_state.search_results = []
            st.warning("Ingen resultater. Prøv et annet søkeord.")
        else:
            st.session_state.search_results = res

    results = st.session_state.search_results

    if results:
        # Velg kurv
        kurver   = db.get_kurver()
        kurv_map = {k["name"]: k["id"] for k in kurver}

        if kurv_map:
            col_k, _ = st.columns([3, 3])
            with col_k:
                valgt_kurv = st.selectbox(
                    "Legg til i handlekurv:",
                    options=list(kurv_map.keys()),
                    format_func=lambda x: f"🧺  {x}",
                )
        else:
            st.info("💡 Opprett en handlekurv i **Mine handlekurver**-fanen for å legge til varer")
            valgt_kurv = None

        st.markdown(
            f"<p style='color:#444;font-size:0.82rem;margin:1rem 0 0.5rem'>"
            f"{len(results)} resultater for «{st.session_state.last_q}»</p>",
            unsafe_allow_html=True,
        )

        for p in results:
            name  = p.get("name", "")
            brand = p.get("brand") or ""
            ean   = p.get("ean") or ""
            pris  = p.get("current_price")
            store_info = p.get("store") or {}
            store_name = store_info.get("name", "") if isinstance(store_info, dict) else ""

            c1, c2, c3 = st.columns([4, 1.5, 0.8])
            with c1:
                tags = "  ".join(
                    f'<span class="tag">{t}</span>'
                    for t in [brand, store_name] if t
                )
                st.markdown(f"**{name}**", unsafe_allow_html=False)
                if tags:
                    st.markdown(tags, unsafe_allow_html=True)
                if ean:
                    st.markdown(f"<span style='color:#333;font-size:0.72rem'>EAN {ean}</span>", unsafe_allow_html=True)
            with c2:
                if pris:
                    st.markdown(
                        f"<p style='font-family:Syne;font-weight:700;font-size:1.15rem;"
                        f"color:#fff;margin:0.35rem 0 0'>{pris:.2f} kr</p>",
                        unsafe_allow_html=True,
                    )
            with c3:
                if st.button("＋", key=f"add_{p.get('id', uuid.uuid4())}"):
                    if valgt_kurv and kurv_map.get(valgt_kurv):
                        db.add_item(kurv_map[valgt_kurv], name, ean or None, brand or None)
                        st.toast(f"✅  {name} lagt til i «{valgt_kurv}»")
                    else:
                        st.warning("Velg eller opprett en handlekurv først.")
            st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – HANDLEKURVER
# ══════════════════════════════════════════════════════════════════════════════
with tab2:

    c1, c2 = st.columns([4, 1])
    with c1:
        ny = st.text_input(
            "ny",
            placeholder="Navn på ny handlekurv, f.eks.  Ukeshandel  ·  Middag fredag ...",
            label_visibility="collapsed",
            key="ny_kurv",
        )
    with c2:
        if st.button("Opprett →", use_container_width=True, key="btn_opprett"):
            if ny.strip():
                if db.connected:
                    db.create_kurv(ny.strip())
                    st.rerun()
                else:
                    st.error("Databasen er ikke tilkoblet.")
            else:
                st.warning("Skriv inn et navn.")

    kurver = db.get_kurver()

    if not kurver:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:#333">
          <p style="font-size:3.5rem;margin:0">🧺</p>
          <p style="font-family:Syne;font-size:1.05rem;color:#555;margin:0.5rem 0">Ingen handlekurver ennå</p>
          <p style="font-size:0.85rem;color:#333">Opprett din første handlekurv ovenfor</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        for kurv in kurver:
            items  = kurv.get("items", [])
            antall = len(items)
            label  = f"🧺  {kurv['name']}  ·  {antall} {'vare' if antall == 1 else 'varer'}"

            with st.expander(label, expanded=True):
                if not items:
                    st.markdown("<p style='color:#333;font-size:0.88rem'>Ingen varer. Søk etter produkter i Søk-fanen.</p>", unsafe_allow_html=True)

                for item in items:
                    c1, c2, c3 = st.columns([4, 1.2, 0.7])
                    with c1:
                        st.markdown(f"**{item['name']}**")
                        if item.get("brand"):
                            st.markdown(f"<span class='tag'>{item['brand']}</span>", unsafe_allow_html=True)
                    with c2:
                        ny_ant = st.number_input(
                            "ant",
                            min_value=1, max_value=99,
                            value=int(item.get("quantity", 1)),
                            key=f"qty_{item['id']}",
                            label_visibility="collapsed",
                        )
                        if ny_ant != item.get("quantity", 1):
                            db.set_qty(item["id"], ny_ant)
                    with c3:
                        if st.button("✕", key=f"del_{item['id']}"):
                            db.del_item(item["id"])
                            st.rerun()

                if items:
                    st.markdown("<br>", unsafe_allow_html=True)

                ca, cb = st.columns([1, 1])
                with ca:
                    if st.button("📊  Analyser priser", key=f"an_{kurv['id']}", use_container_width=True):
                        st.session_state["analyse_kid"] = kurv["id"]
                        st.toast("Åpne Prisanalyse-fanen →")
                with cb:
                    if st.button("Slett kurv", key=f"dk_{kurv['id']}", use_container_width=True):
                        db.delete_kurv(kurv["id"])
                        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – PRISANALYSE
# ══════════════════════════════════════════════════════════════════════════════
with tab3:

    kurver = db.get_kurver()

    if not kurver:
        st.markdown("""
        <div style="text-align:center;padding:4rem 0;color:#333">
          <p style="font-size:3.5rem;margin:0">📊</p>
          <p style="font-family:Syne;font-size:1.05rem;color:#555;margin:0.5rem 0">Ingen handlekurver å analysere</p>
          <p style="font-size:0.85rem;color:#333">Opprett en handlekurv og legg til varer først</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Forhåndsvelg kurv fra knapp i tab2
        default_idx = 0
        if "analyse_kid" in st.session_state:
            ids = [k["id"] for k in kurver]
            if st.session_state["analyse_kid"] in ids:
                default_idx = ids.index(st.session_state["analyse_kid"])

        valgt = st.selectbox(
            "Handlekurv",
            options=kurver,
            index=default_idx,
            format_func=lambda k: f"🧺  {k['name']}  ({len(k.get('items', []))} varer)",
        )

        c1, c2 = st.columns([2, 2])
        with c1:
            kombiner = st.toggle("Kombiner flere butikker", value=True)
        with c2:
            maks = st.select_slider(
                "Maks butikker",
                options=[2, 3, 4, 5],
                value=3,
                disabled=not kombiner,
            ) if kombiner else 1

        klar = st.button("🚀  Analyser priser", type="primary", use_container_width=True)

        if klar:
            items = valgt.get("items", [])
            eans  = [i["ean"] for i in items if i.get("ean")]

            if not items:
                st.warning("Handlekurven er tom.")
            elif not eans:
                st.warning("Ingen varer med EAN-koder. Søk etter produkter i Søk-fanen — disse har EAN-koder.")
            elif not st.session_state.favoritter:
                st.warning("Velg minst én butikk i sidepanelet til venstre.")
            else:
                with st.spinner(f"Henter priser for {len(eans)} varer..."):
                    bulk = client.bulk_prices(eans)

                if not bulk:
                    st.error("Klarte ikke hente priser fra Kassalapp. Sjekk at API-nøkkelen tillater dette domenet.")
                else:
                    opt     = Optimizer(bulk, items, st.session_state.favoritter)
                    ranking = opt.rank()

                    if not ranking:
                        st.warning("Ingen prisdata funnet for dine valgte butikker.")
                    else:
                        st.markdown("---")
                        st.markdown("#### 🏪 Beste enkeltbutikk")

                        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
                        for i, r in enumerate(ranking[:5]):
                            c1, c2, c3 = st.columns([3, 1.5, 2])
                            with c1:
                                st.markdown(f"**{medals[i]}  {r['emoji']} {r['name']}**")
                                farge = "#4ade80" if r["found"] == len(eans) else "#f59e0b"
                                st.markdown(
                                    f"<p style='font-size:0.78rem;color:{farge};margin:0'>"
                                    f"{r['found']}/{len(eans)} varer funnet</p>",
                                    unsafe_allow_html=True,
                                )
                            with c2:
                                st.markdown(
                                    f"<p style='font-family:Syne;font-weight:700;font-size:1.3rem;"
                                    f"color:#fff;margin:0.25rem 0'>{r['total']:.2f} kr</p>",
                                    unsafe_allow_html=True,
                                )
                            with c3:
                                if i == 0:
                                    st.markdown('<span class="badge-best">✓ Billigst</span>', unsafe_allow_html=True)
                                else:
                                    diff = r["total"] - ranking[0]["total"]
                                    st.markdown(
                                        f"<p style='color:#ef4444;font-size:0.88rem;margin:0.25rem 0'>+{diff:.2f} kr</p>",
                                        unsafe_allow_html=True,
                                    )
                            st.divider()

                        # ── Kombinert ──────────────────────────────────────
                        if kombiner and maks > 1:
                            st.markdown(f"#### 🔀 Optimal fordeling ({maks} butikker)")
                            resultat  = opt.split(max_stores=maks)
                            total_opt = sum(r["price"] for r in resultat)
                            bespar    = ranking[0]["total"] - total_opt

                            if bespar > 0.5:
                                st.markdown(f"""
                                <div class="savings-box">
                                  <p style="color:#4ade80;font-size:0.72rem;font-family:Syne;letter-spacing:0.12em;text-transform:uppercase;margin:0 0 0.3rem">Du sparer</p>
                                  <p class="savings-num">{bespar:.2f} kr</p>
                                  <p style="color:#555;font-size:0.82rem;margin:0.3rem 0 0">mot å handle alt på {ranking[0]['name']}</p>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                st.info(f"Minimal besparelse ({bespar:.2f} kr). Det er enklest å handle alt på **{ranking[0]['name']}**.")

                            # Grupper per butikk
                            grupper: dict = {}
                            for r in resultat:
                                grupper.setdefault(r["code"], []).append(r)

                            cols = st.columns(min(len(grupper), 3))
                            for ix, (code, varer) in enumerate(grupper.items()):
                                sub = sum(v["price"] for v in varer)
                                with cols[ix % len(cols)]:
                                    st.markdown(f"""
                                    <div class="card">
                                      <p style="font-family:Syne;font-weight:700;font-size:0.95rem;color:#fff;margin:0 0 0.4rem">
                                        {semoji(code)} {sname(code)}
                                      </p>
                                      <p style="font-family:Syne;font-size:1.5rem;font-weight:800;color:#6c63ff;margin:0 0 0.7rem">{sub:.2f} kr</p>
                                    """, unsafe_allow_html=True)
                                    for v in varer:
                                        st.markdown(
                                            f"<p style='font-size:0.82rem;color:#888;margin:0.15rem 0'>"
                                            f"· {v['name']} × {v['qty']} — {v['price']:.2f} kr</p>",
                                            unsafe_allow_html=True,
                                        )
                                    st.markdown("</div>", unsafe_allow_html=True)

                        # ── Matrise ────────────────────────────────────────
                        st.markdown("#### 📋 Prismatrise")
                        st.caption("Grønn = billigst per vare")
                        mat = opt.matrix()
                        if mat is not None and not mat.empty:
                            st.dataframe(
                                mat.style
                                   .highlight_min(axis=1, color="#1a3a2a")
                                   .format(lambda x: f"{x:.2f} kr" if x else "–"),
                                use_container_width=True,
                                height=min(450, 45 + 36 * len(mat)),
                            )
