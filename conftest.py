import io
import json
import os
import sys
import types
import urllib.parse

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_supabase  # noqa: E402


@pytest.fixture(scope="session")
def data():
    from core import DURData
    return DURData()


# ── 가짜 식약처 API 응답 ───────────────────────────────────────
FAKE_MFDS = {
    "아스피린": [
        {"ITEM_NAME": "아스피린장용정100밀리그램", "ITEM_SEQ": "1", "ITEM_INGR_NAME": "Aspirin", "ENTP_NAME": "A제약"},
        {"ITEM_NAME": "옛날아스피린정", "ITEM_SEQ": "2", "ITEM_INGR_NAME": "Aspirin", "ENTP_NAME": "B제약",
         "CANCEL_NAME": "취소", "CANCEL_DATE": "20190101"}],
    "씬지로이드": [
        {"ITEM_NAME": "씬지로이드정0.1밀리그램", "ITEM_SEQ": "3", "ITEM_INGR_NAME": "레보티록신나트륨수화물", "ENTP_NAME": "부광약품"}],
}
API_CALLS = []


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _fake_urlopen(url, timeout=10):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["item_name"][0]
    API_CALLS.append(q)
    items = [v for k, lst in FAKE_MFDS.items() if k in q for v in lst]
    return _Resp(json.dumps({"body": {"items": items}}).encode())


class FakeCookies:
    store = {}

    def __init__(self, key=None):
        pass

    def get(self, k):
        return FakeCookies.store.get(k)

    def set(self, k, v, **kw):
        FakeCookies.store[k] = v

    def delete(self, k, key=None):
        FakeCookies.store.pop(k, None)


@pytest.fixture
def online(monkeypatch):
    """가짜 Supabase·식약처·쿠키로 웹 모드 앱을 띄우는 함수 반환"""
    import streamlit as st
    import supabase
    import mfds_api
    from streamlit.testing.v1 import AppTest
    fake_supabase.reset()
    FakeCookies.store.clear()
    API_CALLS.clear()
    st.cache_data.clear()
    monkeypatch.setattr(supabase, "create_client", fake_supabase.create_client)
    monkeypatch.setattr(mfds_api.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setenv("MFDS_API_KEY", "test")
    monkeypatch.setitem(sys.modules, "extra_streamlit_components", types.SimpleNamespace(CookieManager=FakeCookies))

    def make(query=None):
        at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=180)
        at.secrets["SUPABASE_URL"] = "https://x.supabase.co"
        at.secrets["SUPABASE_ANON_KEY"] = "ANON"
        at.secrets["SUPABASE_SERVICE_KEY"] = "SERVICE"
        for k, v in (query or {}).items():
            at.query_params[k] = v
        return at.run()
    return make
