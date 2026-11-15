"""검사 엔진 시나리오 테스트 – 실제 DUR 데이터로 확인
실행: python -m pytest tests  (GitHub에 올리면 Actions가 자동 실행)"""
from datetime import date

import mfds_api
from core import DurIndex, Med, detail_queries, pick_mfds_item, same_name, strip_brackets, Profile, analyze_all, in_class, norm_en, pair_checks, today_kst

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


# ── '내 약' 상세 정보 링크 ─────────────────────────────────────
def test_detail_queries():
    assert detail_queries("광동아스피린장용정100mg_(0.1g/1정)") == ["광동아스피린장용정100mg", "광동아스피린장용정"]
    assert detail_queries("리벨서스정(세마글루티드)_(3mg/1정)") == ["리벨서스정"]
    assert detail_queries("23가폐렴구균백신") == ["23가폐렴구균백신"]


def test_pick_mfds_item_for_my_meds(data):
    idx = DurIndex(data.drugs)
    kd = {"name": "광동아스피린장용정100mg", "item_seq": "201702015", "edi_codes": ["641806290"], "active": True}
    y2 = {"name": "와이투아스피린장용정100밀리그램(아스피린)", "item_seq": "202105531", "edi_codes": [], "active": False}
    ryb = {"name": "리벨서스정(세마글루티드)", "item_seq": "202201785", "edi_codes": [], "active": True}
    items = [kd, y2, ryb]
    assert pick_mfds_item("641806290", items, idx) is kd                 # DUR 약 → EDI 코드로
    assert pick_mfds_item("072400130", items, idx) is y2                 # DUR에만 남은 만료 약 → 만료 품목
    assert pick_mfds_item("654400610", items, idx) is ryb                # 용량별 DUR 약 → 묶음 허가
    assert pick_mfds_item("api-202105531", items, idx) is y2             # 식약처에서 찾은 약 → 품목기준코드
    assert pick_mfds_item("api-999", items, idx) is None
    old = dict(kd, item_seq="1", active=False)                          # 같은 제품에 살아 있는 허가가 있으면 그쪽
    assert pick_mfds_item("641806290", [old, kd], idx) is kd


def test_nested_brackets():
    """괄호 안에 괄호가 있는 이름 (실제: 스틴투엑스정, DUR 목록에도 146개)"""
    assert strip_brackets("스틴투엑스정(애엽95%에탄올연조엑스(20→1))") == "스틴투엑스정"
    assert detail_queries("스틴투엑스정(애엽95%에탄올연조엑스(20→1))") == ["스틴투엑스정"]
    assert same_name("넥사바정200밀리그램(소라페닙토실레이트(미분화))_(0.274g/1정)") == \
        same_name("넥사바정200밀리그램(소라페닙토실레이트)")
    assert strip_brackets("짝안맞음(괄호") == "짝안맞음괄호"


# ── 식약처 성분명의 제형 표현 (2026-11-15: 보령아스트릭스캡슐 'Aspirin Enteric Granules') ──
def test_form_words_stripped_from_ingredients(data):
    assert data.parse_ingredients("Aspirin Enteric Granules") == ["aspirin"]
    assert data.parse_ingredients("Aspirin Enteric Pellets") == ["aspirin"]
    assert data.parse_ingredients("Aspirin Lysine For Injection 90%") == ["aspirin"]
    assert data.parse_ingredients("Aspirin Enteric Pellets/Clopidogrel Bisulfate") == ["aspirin", "clopidogrel"]
    assert data.normalize("aspirin enteric granules") == "aspirin"      # 예전에 공동 캐시에 저장된 값도 다시 맞춰짐


def test_duplicate_found_across_mfds_and_dur_aspirin(data):
    """식약처에서 찾은 장용과립 아스피린 + DUR 목록의 아스피린 → 성분중복, 기피성분도 잡힘"""
    bor = Med(key="api-199001012", name="보령아스트릭스캡슐100밀리그람(아스피린)",
              extra_ingrs=frozenset(data.parse_ingredients("Aspirin Enteric Granules")))
    cho = data.med_from_row(data.drugs[data.drugs["제품코드"] == "670700650"].iloc[0])   # 초당아스피린장용정
    adult = Profile(birthdate=date(1990, 1, 1))
    assert has([bor, cho], data, "성분중복", adult)
    assert has([bor], data, "기피성분", Profile(birthdate=date(1990, 1, 1), avoid=["aspirin"]))


def test_form_words_stripped_before_mineral_check():
    """제형 표현이 붙은 무기질 성분도 무기질로 인식 (갑상선호르몬+칼슘 주의를 놓치지 않게)"""
    assert norm_en("calcium carbonate granules") == "calcium carbonate"
    assert in_class(norm_en("Calcium Carbonate Granules"), "CATION")


# ── 나이 경계일 (달력 기준, 화면 표시와 같아야 함) ─────────────────
def test_age_boundaries_calendar():
    from core import age_matches, is_elderly
    under2 = {"특정연령": "2", "특정연령단위": "세 (3)", "연령처리조건": "미만 (1)"}
    upto2 = {"특정연령": "2", "특정연령단위": "세 (3)", "연령처리조건": "이하 (2)"}
    under6m = {"특정연령": "6", "특정연령단위": "개월 (2)", "연령처리조건": "미만 (1)"}
    b = date(2024, 11, 15)
    assert age_matches(under2, b, date(2026, 11, 14))          # 생일 전날: 아직 2세 미만
    assert not age_matches(under2, b, date(2026, 11, 15))      # 2번째 생일 당일: 만 2세
    assert age_matches(upto2, b, date(2027, 11, 14))           # 2세 이하 = 만 3세 전까지
    assert not age_matches(upto2, b, date(2027, 11, 15))
    assert age_matches(under6m, date(2026, 2, 28), date(2026, 8, 27))
    assert not age_matches(under6m, date(2026, 2, 28), date(2026, 8, 28))
    assert not is_elderly(date(1961, 11, 16), date(2026, 11, 15))
    assert is_elderly(date(1961, 11, 15), date(2026, 11, 15))  # 65번째 생일 당일
    assert Profile(birthdate=date(1961, 11, 15)).age_text(date(2026, 11, 15)) == "만 65세"


def test_elderly_check_on_65th_birthday(data):
    m = find(data, "솔리페나신")
    prof = Profile(birthdate=date(1961, 11, 15))
    assert has([m], data, "노인주의", prof)
    assert not has([m], data, "노인주의", Profile(birthdate=date(1961, 11, 16)))
