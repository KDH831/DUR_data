"""앱 흐름 테스트 – 가짜 Supabase·식약처로 회원가입부터 탈퇴까지"""
import fake_supabase
from conftest import API_CALLS, FakeCookies


def btn(at, label):
    return next(b for b in at.button if b.label == label)


def ti(at, label=None, key=None):
    return next(t for t in at.text_input if (key and t.key == key) or (label and t.label.startswith(label)))


def ok(at):
    assert not at.exception, [e.value for e in at.exception]


def login(at, email, pw, remember=None):
    ti(at, "이메일").input(email)
    ti(at, "비밀번호").input(pw)
    if remember is not None:
        cb = next(c for c in at.checkbox if c.label == "로그인 상태 유지")
        cb.check() if remember else cb.uncheck()
    btn(at, "로그인").click().run()
    ok(at)


def make_profile(at, name, y, m, d):
    next(t for t in at.text_input if t.label == "이름(별칭)").input(name)
    at.selectbox[0].select(y)
    at.selectbox[1].select(m)
    at.selectbox[2].select(d)
    btn(at, "💾 저장").click().run()
    ok(at)


def search(at, kw):
    ti(at, "약 이름 또는").input(kw).run()
    ok(at)
    return next(s for s in at.selectbox if s.label.startswith("검색 결과"))


def test_login_remember_default_off(online):
    at = online()
    ok(at)
    assert next(c for c in at.checkbox if c.label == "로그인 상태 유지").value is False
    fake_supabase.USERS["a@x.com"] = "password1"
    login(at, "a@x.com", "password1")
    assert FakeCookies.store == {}                       # 기본값이면 쿠키 저장 안 함


def test_signup_isolation_search_and_delete(online):
    fake_supabase.USERS.update({"a@x.com": "password1", "b@x.com": "password2"})
    a = online()
    login(a, "a@x.com", "password1")
    make_profile(a, "어머니", 1950, 3, 1)

    # 검색: 허가가 끝난 약은 표시를 붙여 맨 뒤에 + DUR 결과 병합
    box = search(a, "아스피린")
    opts = box.options
    assert any("아스트릭스" in o for o in opts)
    ended = [i for i, o in enumerate(opts) if o.startswith(("⚠️", "⛔"))]
    assert ended and ended == list(range(len(opts) - len(ended), len(opts)))   # 모두 맨 뒤
    old_ = next(o for o in opts if "옛날아스피린" in o)
    assert old_.startswith("⛔ [허가 취소]")                                   # 취소는 ⛔
    y2 = next(o for o in opts if "와이투아스피린" in o)                        # DUR 목록에만 남은 만료 약
    assert y2.startswith("⚠️ [판매 중단·허가 만료]") and "_(0.1g/1정)" in y2   # 취하·만료는 ⚠️
    assert opts.index(old_) < opts.index(y2)                                   # 취소가 만료보다 먼저
    assert not opts[0].startswith(("⚠️", "⛔"))                               # 정상 약 선택 시 허가 경고 없음
    assert not any("판매 중단" in w.value or "허가" in w.value for w in [*a.warning, *a.error])

    btn(a, "➕ 내 약에 추가").click().run()
    ok(a)
    assert sum(m["user_id"] == "a@x.com" for m in fake_supabase.DB["meds"]) == 1

    # 허가가 끝난 약을 고르면 경고 + 상세 링크 (경고 후 추가는 가능)
    search(a, "옛날약")
    assert any("허가 취소" in e.value and "2019-01-01" in e.value and "itemSeq=4" in e.value for e in a.error)
    assert any(b_.label == "➕ 내 약에 추가" for b_ in a.button)

    # 용량별로 나뉜 약: 식약처 묶음 항목 없이 DUR 용량별 항목만 (같은 약 중복 표시 방지)
    opts = search(a, "리벨서스").options
    assert len(opts) == 3 and all("mg/1정" in o for o in opts), opts

    # DUR 밖 약 → 공동 DB 저장 (서버 권한으로만)
    search(a, "씬지로이드")
    btn(a, "➕ 내 약에 추가").click().run()
    ok(a)
    assert any(r["key"] == "api-3" for r in fake_supabase.DB["drug_cache"])

    # 다른 사용자: A 데이터 안 보임 + 같은 검색어는 API 재호출 없음
    b = online()
    login(b, "b@x.com", "password2")
    assert any(t.label == "이름(별칭)" for t in b.text_input)      # 프로필 없음 = A 데이터 안 보임
    make_profile(b, "나", 1990, 1, 1)
    calls = API_CALLS.count("아스피린")
    search(b, "아스피린")
    assert API_CALLS.count("아스피린") == calls

    # 탈퇴: 틀린 비밀번호 거부 → 맞으면 A 데이터만 삭제
    ti(a, "본인 확인을").input("wrong")
    next(c for c in a.checkbox if c.label.startswith("모든 데이터")).check()
    btn(a, "회원 탈퇴").click().run()
    assert "a@x.com" in fake_supabase.USERS
    ti(a, "본인 확인을").input("password1")
    btn(a, "회원 탈퇴").click().run()
    ok(a)
    assert "a@x.com" not in fake_supabase.USERS
    assert not any(r["user_id"] == "a@x.com" for t in ("profiles", "meds", "intake") for r in fake_supabase.DB[t])
    assert any(r["user_id"] == "b@x.com" for r in fake_supabase.DB["profiles"])


def test_password_reset_code_and_link(online):
    fake_supabase.USERS["a@x.com"] = "oldpass12"
    at = online()
    ti(at, key="fp_email").input("a@x.com")
    btn(at, "재설정 메일 보내기").click().run()
    assert fake_supabase.OUTBOX == ["a@x.com"]
    ti(at, key="fp_code").input("1234 5678")            # 8자리, 띄어쓰기 섞여도 됨
    btn(at, "코드 확인").click().run()
    ok(at)
    assert at.title[0].value.startswith("🔑")
    ti(at, "새 비밀번호 (").input("newpass12")
    ti(at, "새 비밀번호 확인").input("newpass12")
    btn(at, "변경하기").click().run()
    ok(at)
    assert fake_supabase.USERS["a@x.com"] == "newpass12"

    good = online({"type": "recovery", "token_hash": "GOOD"})
    assert good.title[0].value.startswith("🔑")
    bad = online({"type": "recovery", "token_hash": "BAD"})
    assert any("만료" in e.value for e in bad.error)


def _my_meds_setup(online, email):
    fake_supabase.USERS[email] = "password3"
    at = online()
    login(at, email, "password3")
    make_profile(at, "아버지", 1955, 5, 5)
    for kw in ("아스피린", "옛날약"):
        search(at, kw)
        btn(at, "➕ 내 약에 추가").click().run()
        ok(at)
    next(t for t in at.text_input if t.key == "note_name").input("오메가3")
    next(b for b in at.button if b.key == "note_btn").click().run()
    ok(at)
    return at


def line(at, name):
    return next(m.value for m in at.markdown if f"**{name}**" in m.value)


def test_my_med_detail_link(online):
    """'내 약' 이름 옆 ⓘ = 의약품안전나라 상세 링크, 허가가 끝난 약은 이름 아래 표시, 영양제는 링크 없음"""
    at = _my_meds_setup(online, "c@x.com")
    ok_line = line(at, "아스피린장용정100밀리그램")
    assert "[ⓘ](https://nedrug.mfds.go.kr/pbp/CCBBB01/getItemDetail?itemSeq=1 " in ok_line
    assert "⚠️" not in ok_line                                               # 정상 약
    old = line(at, "옛날약정(옛성분(20→1))")                                  # 괄호가 겹친 이름
    assert "itemSeq=4 " in old and ":red[⛔ 허가 취소 (2019-01-01)" in old and "의사나 약사" in old
    assert "⛔" in old.split("**")[0] and "✅" not in old                     # 취소 약 배지에 ⛔ (안전성 주의)
    assert not line(at, "아스피린장용정100밀리그램").startswith("⚠️")             # 정상 약엔 ⚠️ 없음
    assert "ⓘ" not in line(at, "오메가3")                                      # 영양제는 링크 없음
    assert not any(b.label == "ℹ️" for b in at.button)                         # 따로 누르는 버튼 없음


def test_my_med_detail_when_mfds_down(online, monkeypatch):
    """식약처가 멈추면: 앱은 정상, 식약처에서 찾은 약은 품목기준코드로 링크 유지, 5분간 재조회 안 함"""
    import mfds_api
    from conftest import API_CALLS
    at = _my_meds_setup(online, "d@x.com")
    import streamlit as st
    st.cache_data.clear()                                                     # 하루 공유 저장 비우고

    def down(*a, **k):
        API_CALLS.append("DOWN")
        raise OSError("timeout")
    monkeypatch.setattr(mfds_api.urllib.request, "urlopen", down)
    at.run()
    ok(at)
    assert "itemSeq=1 " in line(at, "아스피린장용정100밀리그램")              # api-1 → 코드로 바로 링크
    n = API_CALLS.count("DOWN")
    assert n == 1                                                            # 첫 실패 뒤 나머지 약은 건너뜀
    at.run()
    ok(at)
    assert API_CALLS.count("DOWN") == n                                      # 다시 그려도 재조회 안 함


def test_permit_ended_display(online):
    """취소: 안전성 확인 '주의'에 설명과 함께 + 배지 ⛔ / 취하·만료: '내 약'엔 회색 안내만, 검색에선 노란 경고"""
    fake_supabase.USERS["e@x.com"] = "password5"
    at = online()
    login(at, "e@x.com", "password5")
    make_profile(at, "나", 1990, 1, 1)                                         # 젊은 성인: 다른 주의 없음
    search(at, "만료약")
    assert any("허가 만료" in w.value and "2023-11-20" in w.value for w in at.warning)  # 검색: 노란 경고
    assert not any("허가 만료" in e.value for e in [*at.info, *at.error])
    btn(at, "➕ 내 약에 추가").click().run()
    ok(at)
    search(at, "옛날약")
    btn(at, "➕ 내 약에 추가").click().run()
    ok(at)

    exp = line(at, "만료약캡슐(만료성분)")
    assert exp.startswith("✅ **") and ":gray[판매 중단 · 허가 만료 (2023-11-20)]" in exp
    assert "⚠️" not in exp and "⛔" not in exp
    old = line(at, "옛날약정(옛성분(20→1))")
    assert old.startswith("⛔") and ":red[⛔ 허가 취소 (2019-01-01)" in old

    # 안전성 확인 탭: 취소만 '허가취소' 주의로, 설명·행동 요령·링크와 함께
    assert any(m.value.startswith("### ⛔ 허가취소 (1건)") for m in at.markdown)
    assert any("허가취소란?" in c.value and "행정처분" in c.value for c in at.caption)
    box = next(w.value for w in at.warning if "옛날약정" in w.value)
    assert "2019-01-01에 식약처가 이 약의 품목허가를 취소했어요" in box
    assert "itemSeq=4" in box and "의사나 약사와 상의" in box
    assert not any("만료약캡슐" in w.value for w in [*at.warning, *at.error])  # 만료 약은 안전성 탭에 없음
    assert any(m.label == "🟡 주의" and m.value == "1건" for m in at.metric)


def test_med_visible_and_deletable_without_service_key(online):
    """서버 키가 없어 공동 캐시에 못 넣어도 약이 목록에 보이고 지울 수 있어야 함"""
    import streamlit as st
    st.cache_resource.clear()            # 앞 테스트에서 저장된 admin_client(서버 키 있음)를 지움
    try:
        _no_service_key_flow(online)
    finally:
        st.cache_resource.clear()        # 뒤 테스트에 '서버 키 없음' 상태가 남지 않게


def _no_service_key_flow(online):
    fake_supabase.USERS["a@x.com"] = "password1"
    at = online()
    del at.secrets["SUPABASE_SERVICE_KEY"]
    at.run()
    login(at, "a@x.com", "password1")
    make_profile(at, "나", 1980, 1, 1)
    search(at, "만료약")
    btn(at, "➕ 내 약에 추가").click().run()
    ok(at)
    assert any("먹는 약 (1개)" in s.value for s in at.subheader)
    assert any("만료약캡슐" in m.value for m in at.markdown)
    del_btn = next(b for b in at.button if b.label == "삭제" and b.key and b.key.startswith("del_"))
    del_btn.click().run()
    ok(at)
    assert any("먹는 약 (0개)" in s.value for s in at.subheader)
    assert fake_supabase.DB["meds"] == []
