"""검사 엔진 시나리오 테스트 – 실제 DUR 데이터로 확인
실행: python -m pytest tests  (GitHub에 올리면 Actions가 자동 실행)"""
from datetime import date

import mfds_api
from core import DurIndex, Med, Profile, analyze_all, in_class, norm_en, pair_checks, today_kst

ELDER = Profile(birthdate=date(1950, 3, 1))
TODAY = date(2026, 11, 15)


def find(data, name):
    rows = data.search(name)
    assert not rows.empty, f"DUR 목록에서 '{name}'을(를) 찾지 못함"
    return data.med_from_row(rows.iloc[0])


def kinds(meds, data, prof=ELDER):
    return {(f["종류"], tuple(sorted(f["성분"]))) for f in analyze_all(meds, prof, data, TODAY)}


def has(meds, data, kind, prof=ELDER):
    return any(f["종류"] == kind for f in analyze_all(meds, prof, data, TODAY))


# ── 성분명 정규화 ───────────────────────────────────────────
def test_normalize_salts_and_variants(data):
    assert norm_en("rosuvastatin calcium (as rosuvastatin)") == "rosuvastatin"
    assert norm_en("acetaminophen(encapsulated)") == "acetaminophen"
    assert norm_en("naproxen sodium") == "naproxen"
    assert norm_en("esomeprazole magnesium trihydrate") == "esomeprazole"
    assert norm_en("calcium carbonate") == "calcium carbonate"          # 무기질은 그대로
    assert norm_en("potassium chloride") == "potassium chloride"
    assert norm_en("sodium valproate") == norm_en("valproic acid")      # 같은 성분 다른 표기
    assert data.normalize("에스오메프라졸마그네슘삼수화물") == "esomeprazole"
    assert data.normalize("탄산칼슘") == "calcium carbonate"
    assert data.parse_ingredients("아세트아미노펜/이소프로필안티피린/카페인무수물") == \
        ["acetaminophen", "caffeine", "isopropylantipyrine"]


def test_class_false_positives_fixed():
    assert not in_class(norm_en("calcium pantothenate"), "CATION")        # 비타민 B5
    assert not in_class(norm_en("potassium guaiacolsulfonate"), "K_SUPP")  # 기침 시럽 성분
    assert in_class("potassium chloride", "K_SUPP")
    assert in_class("calcium carbonate", "CATION")


# ── 약 2개 검사 ─────────────────────────────────────────────
def test_duplicate_ingredient_across_combo(data):
    assert ("성분중복", ("acetaminophen",)) in kinds([find(data, "타이레놀8시간"), find(data, "울트라셋")], data)


def test_dur_contraindication_by_code(data):
    assert has([find(data, "조코정"), find(data, "클래리시드")], data, "병용금기")


def test_contraindication_by_name_for_non_dur_drug(data):
    itra = Med(key="api-x", name="진균제", extra_ingrs=frozenset([data.normalize("이트라코나졸")]))
    assert has([itra, find(data, "조코정")], data, "병용금기")


def test_caution_interactions(data):
    k = kinds([find(data, "쿠파린정5"), find(data, "아스피린프로텍트"), find(data, "부루펜정200")], data)
    assert ("상호작용주의", ("aspirin", "warfarin")) in k
    assert ("상호작용주의", ("ibuprofen", "warfarin")) in k
    thyroid = Med(key="a", name="갑상선약", extra_ingrs=frozenset(["levothyroxine"]))
    calcium = Med(key="b", name="칼슘", extra_ingrs=frozenset(["calcium carbonate"]))
    assert has([thyroid, calcium], data, "상호작용주의")


def test_combo_code_false_positive_removed(data):
    """텔미사르탄 단일제 + 사이클로스포린은 금기 아님 (복합제 코드의 대표 성분 표기 때문에 생기던 오탐)"""
    assert not has([find(data, "네오텔미정40"), find(data, "사이크린연질캡슐100")], data, "병용금기")


def test_combo_culprit_kept(data):
    """로수바스타틴 복합제 + 사이클로스포린은 금기 유지"""
    assert has([find(data, "로수바미브정10/2.5"), find(data, "사이크린연질캡슐100")], data, "병용금기")


# ── 프로필 기반 검사 ─────────────────────────────────────────
def test_infant_age_in_months(data):
    cream = find(data, "가두벌크림")                       # 30개월 이하 금기
    assert has([cream], data, "연령금기", Profile(birthdate=date(2025, 1, 1)))      # 22개월
    assert not has([cream], data, "연령금기", Profile(birthdate=date(2022, 1, 1)))  # 4세


def test_pregnancy_grades_and_avoid(data):
    p = Profile(birthdate=date(1995, 1, 1), pregnant=True, crush=True, avoid=["class:NSAID"])
    found = {f["종류"] for f in analyze_all([find(data, "부루펜정200"), find(data, "타이레놀8시간")], p, data, TODAY)}
    assert "기피성분" in found
    assert "분할주의" in found                            # 서방정


def test_profile_age_text():
    assert Profile(birthdate=date(2026, 6, 10)).age_text(TODAY) == "5개월"
    assert Profile(birthdate=date(1950, 3, 1)).age_text(TODAY) == "만 76세"


def test_today_kst_type():
    assert isinstance(today_kst(), date)


# ── 식약처 응답 처리 ─────────────────────────────────────────
def test_cancelled_products_filtered():
    assert mfds_api.is_active({"ITEM_NAME": "a"})
    assert mfds_api.is_active({"CANCEL_NAME": "정상"})
    assert not mfds_api.is_active({"CANCEL_NAME": "취소", "CANCEL_DATE": "20190101"})
    assert not mfds_api.is_active({"CANCEL_DATE": "20200101"})


# ── 식약처 품목 → DUR 연결 (2026-11-15 실제 응답 기준) ─────────────
def test_edi_code_parsed():
    assert mfds_api.edi_codes({"EDI_CODE": "641806290"}) == ["641806290"]
    assert mfds_api.edi_codes({"EDI_CODE": "641806290,641806291"}) == ["641806290", "641806291"]
    assert mfds_api.edi_codes({"EDI_CODE": None}) == []


def test_link_by_edi_even_if_name_differs(data):
    idx = DurIndex(data.drugs)
    # 이름 표기가 달라도 EDI 코드로 연결
    assert idx.match({"name": "광동아스피린장용정100밀리그램", "edi_codes": ["641806290"]}) == ["641806290"]
    # 실제 응답(이름도 같음)
    assert idx.match({"name": "광동아스피린장용정100mg", "edi_codes": ["641806290"]}) == ["641806290"]


def test_multi_strength_item_links_to_all_strengths(data):
    """리벨서스: 식약처는 허가 1건(EDI_CODE null), DUR은 3·7·14mg 3개 → 용량별 DUR 항목 3개로 연결"""
    idx = DurIndex(data.drugs)
    codes = idx.match({"name": "리벨서스정(세마글루티드)", "edi_codes": []})
    assert sorted(codes) == ["654400610", "654400620", "654400630"]


def test_multi_package_combo_keeps_code_contraindication(data):
    """그린콜샷에스시럽(포장별 성분코드 2개): DUR 항목으로 연결돼야 라사길린 병용금기(코드 기준)를 잡음"""
    idx = DurIndex(data.drugs)
    codes = idx.match({"name": "그린콜샷에스시럽", "edi_codes": []})
    assert len(codes) == 2
    rasa = find(data, "라사길린")
    for c in codes:
        assert any(f["종류"] == "병용금기" for f in pair_checks(data.med_from_row(data.drugs[data.drugs["제품코드"] == c].iloc[0]), rasa, data))


def test_unknown_item_stays_api(data):
    assert DurIndex(data.drugs).match({"name": "씬지로이드정0.1밀리그램", "edi_codes": []}) == []


def test_permit_status_info():
    assert mfds_api.status_info({"active": True}) is None
    tag, level, msg, date, url = mfds_api.status_info(
        {"active": False, "cancel_name": "유효기간만료", "cancel_date": "20260723", "item_seq": "202105531"})
    assert level == "warning" and "만료" in tag and date == "2026-07-23" and url.endswith("itemSeq=202105531")
    assert mfds_api.status_info({"active": False, "cancel_name": "취하", "cancel_date": "20240104"})[1] == "warning"
    assert mfds_api.status_info({"active": False, "cancel_name": "취소", "cancel_date": ""})[1] == "error"
    tag, level, *_ = mfds_api.status_info({"active": False, "cancel_name": "새상태", "cancel_date": None})
    assert "새상태" in tag and level == "warning"                      # 모르는 값도 안내


def test_search_returns_ended_items_only_when_asked(monkeypatch):
    import io, json
    item = {"ITEM_NAME": "옛약", "ITEM_SEQ": "9", "ITEM_INGR_NAME": "Aspirin", "CANCEL_NAME": "취하", "CANCEL_DATE": "20240104"}

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setenv("MFDS_API_KEY", "test")
    monkeypatch.setattr(mfds_api.urllib.request, "urlopen", lambda *a, **k: R(json.dumps({"body": {"items": [item]}}).encode()))
    assert mfds_api.search("옛약") == []
    r = mfds_api.search("옛약", include_inactive=True)[0]
    assert r["active"] is False and r["cancel_name"] == "취하" and r["cancel_date"] == "20240104"


def test_item_name_whitespace_cleaned(monkeypatch):
    """실제 응답에 줄바꿈이 섞인 제품명이 있음 (2026-11-15 라니티딘 조회)"""
    import io, json
    items = [{"ITEM_NAME": "휴란정150mg\n\n(라니티딘염산염)", "ITEM_SEQ": "1", "ITEM_INGR_NAME": "Ranitidine Hydrochloride"},
             {"ITEM_NAME": "라니돈정75밀리그램(라니티딘염산염)\r\n", "ITEM_SEQ": "2", "ITEM_INGR_NAME": "Ranitidine Hydrochloride"}]

    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setenv("MFDS_API_KEY", "test")
    monkeypatch.setattr(mfds_api.urllib.request, "urlopen", lambda *a, **k: R(json.dumps({"body": {"items": items}}).encode()))
    assert [r["name"] for r in mfds_api.search("라니")] == ["휴란정150mg (라니티딘염산염)", "라니돈정75밀리그램(라니티딘염산염)"]
