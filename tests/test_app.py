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

    # 검색: 취소 품목 제외 + DUR 결과 병합
    opts = search(a, "아스피린").options
    assert not any("옛날아스피린" in o for o in opts)
    assert any("아스트릭스" in o for o in opts)
    btn(a, "➕ 내 약에 추가").click().run()
    ok(a)
    assert sum(m["user_id"] == "a@x.com" for m in fake_supabase.DB["meds"]) == 1

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
