"""
Handlekurv Optimizer – alt i én fil
Kjør med: streamlit run app.py
"""

import time
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
import pandas as pd
import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# KASSALAPP API-KLIENT
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


class KassalappClient:
    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._last_call = 0.0

    def _throttle(self):
        elapsed = time.time() - self._last_call
        if elapsed < 0.05:
            time.sleep(0.05 - elapsed)
        self._last_call = time.time()

    def _get(self, endpoint: str, params: dict = None) -> dict:
        self._throttle()
        resp = self.session.get(f"{BASE_URL}/{endpoint.lstrip('/')}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, payload: dict) -> dict:
        self._throttle()
        resp = self.session.post(f"{BASE_URL}/{endpoint.lstrip('/')}", json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def search_products(self, query: str, size: int = 20, unique: bool = True) -> list[dict]:
        data = self._get("/products", {"search": query, "size": size, "unique": str(unique).lower()})
        return data.get("data", [])

    def get_bulk_prices(self, eans: list[str], days: int = 30) -> list[dict]:
        results = []
        for i in range(0, len(eans), 100):
            batch = eans[i:i+100]
            try:
                data = self._post("/products/prices-bulk", {"eans": batch, "days": days, "aggregation": "min"})
                results.extend(data.get("data", []))
            except Exception as e:
                st.warning(f"Feil ved henting av priser: {e}")
        return results


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE (Supabase eller lokal JSON-fil)
# ══════════════════════════════════════════════════════════════════════════════

LOCAL_FILE = Path("handlekurver_local.json")


class Database:
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        self.use_supabase = bool(supabase_url and supabase_key)
        self._sb = None

        if self.use_supabase:
            try:
                from supabase import create_client
                self._sb = create_client(supabase_url, supabase_key)
            except Exception as e:
                st.warning(f"Supabase feilet ({e}), bruker lokal lagring.")
                self.use_supabase = False

        self._data = self._load_local()

    def _load_local(self) -> dict:
        if LOCAL_FILE.exists():
            try:
                return json.loads(LOCAL_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"handlekurver": []}

    def _save_local(self):
        LOCAL_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_handlekurv(self, name: str) -> dict:
        kurv = {"id": str(uuid.uuid4()), "name": name, "created_at": datetime.utcnow().isoformat(), "items": []}
        if self.use_supabase:
            try:
                self._sb.table("handlekurver").insert({"id": kurv["id"], "name": name, "created_at": kurv["created_at"]}).execute()
                return kurv
            except Exception as e:
                st.warning(f"Supabase feil: {e}")
        self._data["handlekurver"].append(kurv)
        self._save_local()
        return kurv

    def get_handlekurver(self) -> list[dict]:
        if self.use_supabase:
            try:
                kurver = self._sb.table("handlekurver").select("*").order("created_at", desc=True).execute().data or []
                items_all = self._sb.table("handlekurv_items").select("*").execute().data or []
                for k in kurver:
                    k["items"] = [i for i in items_all if i["kurv_id"] == k["id"]]
                return kurver
            except Exception as e:
                st.warning(f"Supabase feil: {e}")
        return self._data.get("handlekurver", [])

    def delete_handlekurv(self, kurv_id: str):
        if self.use_supabase:
            try:
                self._sb.table("handlekurv_items").delete().eq("kurv_id", kurv_id).execute()
                self._sb.table("handlekurver").delete().eq("id", kurv_id).execute()
                return
            except Exception as e:
                st.warning(f"Supabase feil: {e}")
        self._data["handlekurver"] = [k for k in self._data["handlekurver"] if k["id"] != kurv_id]
        self._save_local()

    def add_item(self, kurv_id: str, item: dict) -> dict:
        obj = {
            "id": str(uuid.uuid4()), "kurv_id": kurv_id,
            "name": item.get("name", ""), "ean": item.get("ean"),
            "brand": item.get("brand"), "image": item.get("image"),
            "quantity": item.get("quantity", 1), "added_at": datetime.utcnow().isoformat(),
        }
        if self.use_supabase:
            try:
                self._sb.table("handlekurv_items").insert(obj).execute()
                return obj
            except Exception as e:
                st.warning(f"Supabase feil: {e}")
        for k in self._data["handlekurver"]:
            if k["id"] == kurv_id:
                k.setdefault("items", []).append(obj)
                break
        self._save_local()
        return obj

    def update_quantity(self, item_id: str, quantity: int):
        if self.use_supabase:
            try:
                self._sb.table("handlekurv_items").update({"quantity": quantity}).eq("id", item_id).execute()
                return
            except Exception as e:
                st.warning(f"Supabase feil: {e}")
        for k in self._data["handlekurver"]:
            for i in k.get("items", []):
                if i["id"] == item_id:
                    i["quantity"] = quantity
        self._save_local()

    def remove_item(self, item_id: str):
        if self.use_supabase:
            try:
                self._sb.table("handlekurv_items").delete().eq("id", item_id).execute()
                return
            except Exception as e:
                st.warning(f"Supabase feil: {e}")
        for k in self._data["handlekurver"]:
            k["items"] = [i for i in k.get("items", []) if i["id"] != item_id]
        self._save_local()


# ══════════════════════════════════════════════════════════════════════════════
# PRISOPTIMALISERING
# ══════════════════════════════════════════════════════════════════════════════

class Optimizer:
    def __init__(self, bulk_prices: list[dict], basket_items: list[dict], preferred_stores: list[str]):
        self.basket_items = basket_items

        self._prices: dict[str, dict[str, float]] = {}
        for p in bulk_prices:
            ean = p.get("ean", "")
            self._prices[ean] = {
                s["store"]: float(s["current_price"])
                for s in p.get("stores", [])
                if s.get("current_price") is not None
            }

        all_stores = {s for prices in self._prices.values() for s in prices}
        preferred = set(preferred_stores) & all_stores
        self.active_stores = preferred if preferred else all_stores

    def _name(self, code: str) -> str:
        return STORE_NAMES.get(code, code)

    def rank_stores(self) -> list[tuple[str, dict]]:
        results = []
        for code in self.active_stores:
            total, found = 0.0, 0
            for item in self.basket_items:
                ean, qty = item.get("ean"), item.get("quantity", 1)
                if not ean:
                    continue
                price = self._prices.get(ean, {}).get(code)
                if price is not None:
                    total += price * qty
                    found += 1
            if found > 0:
                results.append((code, {"store_name": self._name(code), "total": round(total, 2), "found_items": found}))
        results.sort(key=lambda x: x[1]["total"])
        return results

    def optimize_split(self, max_stores: int = 3) -> list[dict]:
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
                "price": round(valid[best] * qty, 2), "all_prices": valid,
            })

        while len({a["store_code"] for a in assignments}) > max_stores:
            unique = {a["store_code"] for a in assignments}
            counts = {s: sum(1 for a in assignments if a["store_code"] == s) for s in unique}
            smallest = min(counts, key=counts.get)
            remaining = unique - {smallest}
            for a in assignments:
                if a["store_code"] == smallest:
                    candidates = {s: a["all_prices"].get(s) for s in remaining if a["all_prices"].get(s) is not None}
                    if candidates:
                        new = min(candidates, key=candidates.get)
                        a.update({"store_code": new, "store_name": self._name(new), "price": round(candidates[new] * a["quantity"], 2)})

        for a in assignments:
            a.pop("all_prices", None)
        return assignments

    def price_matrix(self) -> Optional[pd.DataFrame]:
        rows, index = [], []
        for item in self.basket_items:
            ean = item.get("ean")
            if not ean or not self._prices.get(ean):
                continue
            row = {self._name(c): self._prices[ean].get(c) for c in sorted(self.active_stores)}
            rows.append(row)
            index.append(item["name"][:40])
        return pd.DataFrame(rows, index=index) if rows else None


# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Handlekurv Optimizer", page_icon="🛒", layout="wide")

st.markdown("""
<style>
.savings { background:#28a745; color:white; padding:0.2rem 0.7rem; border-radius:20px; font-size:0.85rem; font-weight:600; }
</style>
""", unsafe_allow_html=True)

for k, v in {"client": None, "db": None, "search_results": [], "favoritter": ["REMA_1000", "KIWI", "SPAR_NO"]}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidepanel ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Innstillinger")
    api_key      = st.text_input("Kassalapp API-nøkkel", type="password")
    supabase_url = st.text_input("Supabase URL (valgfritt)", placeholder="https://xxx.supabase.co")
    supabase_key = st.text_input("Supabase Anon Key (valgfritt)", type="password")

    if st.button("💾 Koble til", use_container_width=True):
        if api_key:
            st.session_state.client = KassalappClient(api_key)
            st.session_state.db = Database(supabase_url or None, supabase_key or None)
            st.success("✅ Koblet til!")
        else:
            st.error("Fyll inn API-nøkkel!")

    st.divider()
    st.markdown("### 🏪 Butikker i nærheten")
    st.session_state.favoritter = st.multiselect(
        "Velg butikker du har tilgang til",
        options=list(STORE_NAMES.keys()),
        default=st.session_state.favoritter,
        format_func=lambda x: STORE_NAMES.get(x, x),
    )

# ── Hovedinnhold ───────────────────────────────────────────────────────────────
st.markdown("# 🛒 Handlekurv Optimizer")
st.caption("Finn billigste butikk – eller kombiner flere for å spare mest mulig")

tab1, tab2, tab3 = st.tabs(["🔍 Søk etter varer", "🧺 Mine handlekurver", "📊 Prisanalyse"])

# ── TAB 1: Søk ────────────────────────────────────────────────────────────────
with tab1:
    c1, c2 = st.columns([4, 1])
    with c1:
        query = st.text_input("Søk", placeholder="f.eks. melk, havregryn, Grandiosa...", label_visibility="collapsed")
    with c2:
        do_search = st.button("🔍 Søk", use_container_width=True)

    if do_search:
        if not st.session_state.client:
            st.error("Koble til API-nøkkel i sidepanelet først.")
        elif not query:
            st.warning("Skriv inn et søkeord.")
        else:
            with st.spinner("Søker..."):
                st.session_state.search_results = st.session_state.client.search_products(query)

    if st.session_state.search_results:
        db: Database = st.session_state.db
        kurver = db.get_handlekurver() if db else []
        kurv_map = {k["name"]: k["id"] for k in kurver}

        valgt_kurv = st.selectbox(
            "Legg til i handlekurv:",
            options=list(kurv_map.keys()) if kurv_map else ["(Opprett handlekurv i Tab 2 først)"],
        )

        st.markdown(f"**{len(st.session_state.search_results)} resultater:**")
        for p in st.session_state.search_results:
            c1, c2, c3 = st.columns([4, 1.5, 0.8])
            with c1:
                st.markdown(f"**{p['name']}**")
                st.caption(f"{p.get('brand', '')}  ·  {p.get('store', {}).get('name', '')}")
            with c2:
                pris = p.get("current_price")
                st.metric("", f"{pris:.2f} kr" if pris else "–")
            with c3:
                if st.button("➕", key=f"add_{p['id']}"):
                    kid = kurv_map.get(valgt_kurv)
                    if kid and db:
                        db.add_item(kid, {"name": p["name"], "ean": p.get("ean"), "brand": p.get("brand"), "image": p.get("image")})
                        st.success("Lagt til!", icon="✅")
                    else:
                        st.warning("Opprett en handlekurv i Tab 2 først.")
            st.divider()

# ── TAB 2: Handlekurver ───────────────────────────────────────────────────────
with tab2:
    db: Database = st.session_state.db
    if not db:
        st.info("Koble til i sidepanelet for å bruke handlekurver.")
    else:
        c1, c2 = st.columns([3, 1])
        with c1:
            ny_navn = st.text_input("Navn på ny handlekurv", placeholder="f.eks. Ukeshandel")
        with c2:
            st.write("")
            if st.button("➕ Opprett", use_container_width=True):
                if ny_navn:
                    db.create_handlekurv(ny_navn)
                    st.rerun()

        st.divider()
        for kurv in db.get_handlekurver():
            with st.expander(f"🧺 {kurv['name']} — {len(kurv.get('items', []))} varer", expanded=True):
                items = kurv.get("items", [])
                if not items:
                    st.caption("Ingen varer ennå. Søk i Tab 1.")
                for item in items:
                    c1, c2, c3 = st.columns([4, 1, 0.5])
                    with c1:
                        st.markdown(f"**{item['name']}**")
                        st.caption(item.get("brand") or "")
                    with c2:
                        ny_ant = st.number_input("", min_value=1, value=item.get("quantity", 1),
                                                  key=f"qty_{item['id']}", label_visibility="collapsed")
                        if ny_ant != item.get("quantity", 1):
                            db.update_quantity(item["id"], ny_ant)
                    with c3:
                        if st.button("🗑", key=f"del_{item['id']}"):
                            db.remove_item(item["id"])
                            st.rerun()
                if items:
                    st.divider()
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("📊 Analyser", key=f"an_{kurv['id']}", use_container_width=True):
                            st.session_state["analyser_kurv_id"] = kurv["id"]
                    with c2:
                        if st.button("🗑 Slett kurv", key=f"dk_{kurv['id']}", use_container_width=True):
                            db.delete_handlekurv(kurv["id"])
                            st.rerun()

# ── TAB 3: Prisanalyse ────────────────────────────────────────────────────────
with tab3:
    db: Database = st.session_state.db
    client: KassalappClient = st.session_state.client

    if not client:
        st.info("Koble til API-nøkkel i sidepanelet.")
    elif not db:
        st.info("Koble til i sidepanelet.")
    else:
        kurver = db.get_handlekurver()
        if not kurver:
            st.info("Opprett en handlekurv med varer i Tab 2 først.")
        else:
            valgt = st.selectbox("Velg handlekurv", kurver, format_func=lambda k: k["name"])

            c1, c2 = st.columns(2)
            with c1:
                enkel    = st.checkbox("🏪 Beste enkeltbutikk", value=True)
                kombiner = st.checkbox("🔀 Optimaliser på tvers av butikker", value=True)
            with c2:
                maks = st.slider("Maks antall butikker", 2, 5, 3, disabled=not kombiner)

            if st.button("🚀 Kjør prisanalyse", type="primary", use_container_width=True):
                items = valgt.get("items", [])
                eans  = [i["ean"] for i in items if i.get("ean")]

                if not eans:
                    st.warning("Ingen varer med EAN-koder. Søk etter produkter via søkefeltet for å sikre EAN-koder.")
                else:
                    with st.spinner("Henter priser fra Kassalapp..."):
                        priser = client.get_bulk_prices(eans)

                    if not priser:
                        st.error("Klarte ikke hente priser. Sjekk API-nøkkelen.")
                    else:
                        opt     = Optimizer(priser, items, st.session_state.favoritter)
                        ranking = opt.rank_stores()
                        st.markdown("---")

                        if enkel and ranking:
                            st.markdown("### 🏪 Beste enkeltbutikk")
                            medals = ["🥇", "🥈", "🥉", "4.", "5."]
                            for i, (code, info) in enumerate(ranking[:5]):
                                c1, c2, c3 = st.columns([2, 1.5, 2])
                                with c1:
                                    st.markdown(f"**{medals[i]} {info['store_name']}**")
                                    st.caption(f"{info['found_items']} av {len(eans)} varer funnet")
                                with c2:
                                    st.metric("Total", f"{info['total']:.2f} kr")
                                with c3:
                                    if i == 0:
                                        st.markdown('<span class="savings">Billigst ✓</span>', unsafe_allow_html=True)
                                    else:
                                        st.caption(f"+{info['total'] - ranking[0][1]['total']:.2f} kr dyrere")
                                st.divider()

                        if kombiner:
                            st.markdown(f"### 🔀 Optimal fordeling (maks {maks} butikker)")
                            resultat = opt.optimize_split(max_stores=maks)

                            if resultat:
                                total_opt = sum(r["price"] for r in resultat)
                                st.metric("Optimal totalpris", f"{total_opt:.2f} kr")

                                if ranking:
                                    besparelse = ranking[0][1]["total"] - total_opt
                                    if besparelse > 0:
                                        st.success(f"💰 Du sparer **{besparelse:.2f} kr** mot beste enkeltbutikk!")

                                grupper: dict = {}
                                for r in resultat:
                                    grupper.setdefault(r["store_name"], []).append(r)

                                for butikk, varer in grupper.items():
                                    sub = sum(v["price"] for v in varer)
                                    with st.expander(f"🏪 **{butikk}** — {sub:.2f} kr ({len(varer)} varer)"):
                                        st.dataframe(
                                            pd.DataFrame([{"Produkt": v["name"], "Antall": v["quantity"], "Pris": f"{v['price']:.2f} kr"} for v in varer]),
                                            hide_index=True, use_container_width=True,
                                        )

                        st.markdown("### 📋 Prismatrise (grønn = billigst per vare)")
                        matrise = opt.price_matrix()
                        if matrise is not None:
                            st.dataframe(
                                matrise.style.highlight_min(axis=1, color="#d4edda"),
                                use_container_width=True,
                            )