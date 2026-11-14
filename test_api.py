"""API 연결 확인용: python tools/test_api.py 게보린정
응답 원문 일부와 성분 필드를 보여줍니다. 성분이 비어 있으면 mfds_api.py의 URL/INGR_FIELDS를 고치세요."""
import json, os, sys, tomllib, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mfds_api

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sec = os.path.join(base, ".streamlit", "secrets.toml")
if not os.environ.get("MFDS_API_KEY") and os.path.exists(sec):
    os.environ["MFDS_API_KEY"] = tomllib.load(open(sec, "rb")).get("MFDS_API_KEY", "")
name = sys.argv[1] if len(sys.argv) > 1 else "게보린정"
q = {"serviceKey": mfds_api.get_key(), "type": "json", "numOfRows": 3, "pageNo": 1, "item_name": name}
raw = urllib.request.urlopen(mfds_api.URL + "?" + urllib.parse.urlencode(q), timeout=15).read().decode()
print("── 응답 원문(앞부분) ──\n", raw[:1500])
try:
    items = mfds_api._items(json.loads(raw))
    print("\n── 첫 항목의 필드 ──\n", list(items[0].keys()) if items else "항목 없음")
    print("\n── 파싱 결과 ──\n", mfds_api.search(name, rows=3))
except Exception as e:
    print("JSON 파싱 실패:", e)
