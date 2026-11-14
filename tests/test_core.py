"""검사 엔진 시나리오 테스트 – 실제 DUR 데이터로 확인
실행: python -m pytest tests  (GitHub에 올리면 Actions가 자동 실행)"""
from datetime import date

import mfds_api
from core import Med, Profile, analyze_all, in_class, norm_en, today_kst

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
