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


def is_active(it):
    """허가가 살아 있는 품목인지. 취소·취하 품목은 CANCEL_DATE/CANCEL_NAME에 값이 있음
    (필드가 아예 없으면 정상으로 봄 → python test_api.py 로 실제 필드 확인 권장)"""
    status = str(it.get("CANCEL_NAME") or "").strip()
    cdate = str(it.get("CANCEL_DATE") or "").strip()
    return not cdate and status in ("", "정상")


def search(name, rows=20, timeout=10, include_inactive=False):
    """반환: [{'name', 'item_seq', 'ingredients_raw', 'company', 'active'}]. 키가 없으면 [], 통신 실패 시 예외
    기본값은 허가 취소·취하 품목을 빼고 돌려줌"""
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
        active = is_active(it)
        if nm and raw and (active or include_inactive):
            out.append({"name": nm, "item_seq": str(it.get("ITEM_SEQ") or it.get("PRDLST_STDR_CODE") or ""),
                        "ingredients_raw": raw, "company": it.get("ENTP_NAME") or "", "active": active})
    return out
