"""
식약처 '의약품 제품 허가정보' API (공공데이터포털 데이터 15095677)
  - 약 이름(item_name)으로 조회 → 제품명, 품목기준코드, 주성분
  - 인증키: 환경변수 MFDS_API_KEY → .streamlit/secrets.toml → Streamlit Cloud Secrets 순서로 찾음
  - 서비스 버전·응답 필드명이 바뀌면 아래 URL / INGR_FIELDS만 고치면 됨
    (확인: python test_api.py 게보린정)
"""
import json
import os
import urllib.parse
import urllib.request

URL = os.environ.get("MFDS_API_URL",
                     "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService08/getDrugPrdtPrmsnInq08")
INGR_FIELDS = ["ITEM_INGR_NAME", "MAIN_ITEM_INGR", "MAIN_INGR_ENG", "MATERIAL_NAME", "INGR_NAME"]


def get_key():
    key = os.environ.get("MFDS_API_KEY", "")
    if not key:
        sec = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
        if os.path.exists(sec):
            import tomllib
            with open(sec, "rb") as f:
                key = tomllib.load(f).get("MFDS_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("MFDS_API_KEY", "")
        except Exception:
            pass
    return key


def _items(data):
    body = data.get("body") or data.get("response", {}).get("body", {})
    items = body.get("items") or []
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return [i.get("item", i) if isinstance(i, dict) else i for i in items]


def search(name, rows=20, timeout=10):
    """반환: [{'name', 'item_seq', 'ingredients_raw'}]. 키가 없으면 [], 통신 실패 시 예외"""
    key = get_key()
    if not key:
        return []
    q = {"serviceKey": key, "type": "json", "numOfRows": rows, "pageNo": 1, "item_name": name}
    with urllib.request.urlopen(URL + "?" + urllib.parse.urlencode(q), timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    out = []
    for it in _items(data):
        raw = next((it[f] for f in INGR_FIELDS if it.get(f)), "")
        nm = it.get("ITEM_NAME") or it.get("item_name")
        if nm and raw:
            out.append({"name": nm, "item_seq": str(it.get("ITEM_SEQ") or it.get("PRDLST_STDR_CODE") or ""),
                        "ingredients_raw": raw})
    return out
