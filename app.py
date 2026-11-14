from datetime import date, timedelta

import pandas as pd
import streamlit as st

import mfds_api
from core import (DURData, Med, Profile, analyze_all, med_from_cache, norm_drug_name, note_med,
                  pair_checks, short_name, single_checks)
from rules import CLASSES
from store import LocalStore, SupabaseStore

st.set_page_config(page_title="내 약 지킴이", page_icon="💊", layout="centered")


# ─────────────────────────────────────────
# 1. 데이터·저장소 (처음 한 번만 준비)
# ─────────────────────────────────────────
@st.cache_resource(show_spinner="약 데이터를 불러오는 중...")
def load_data():
    return DURData()


def secret(name):
    try:
        return st.secrets.get(name, "")
    except Exception:
        return ""


SB_URL, SB_ANON, SB_SERVICE = secret("SUPABASE_URL"), secret("SUPABASE_ANON_KEY"), secret("SUPABASE_SERVICE_KEY")
ONLINE = bool(SB_URL and SB_ANON)       # Supabase 설정이 있으면 웹(계정) 모드, 없으면 내 컴퓨터 모드


@st.cache_resource
def local_store():
    return LocalStore()


@st.cache_resource
def admin_client():
    if not SB_SERVICE:
        return None
    from supabase import create_client
    return create_client(SB_URL, SB_SERVICE)


def login_gate():
    """로그인 전이면 로그인/회원가입 화면을 보여주고 멈춤"""
    if st.session_state.get("sb_email"):
        return
    from supabase import create_client
    st.title("💊 내 약 지킴이")
    st.write("내 약과 가족의 약을 계정에 안전하게 저장해요. 다른 사람은 내 정보를 볼 수 없어요.")
    t_in, t_up = st.tabs(["로그인", "회원가입"])
    with t_in, st.form("login"):
        email = st.text_input("이메일")
        pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인", type="primary"):
            client = create_client(SB_URL, SB_ANON)
            try:
                res = client.auth.sign_in_with_password({"email": email.strip(), "password": pw})
                st.session_state.sb, st.session_state.sb_email = client, res.user.email
                st.rerun()
            except Exception as e:
                st.error("로그인하지 못했어요. 이메일·비밀번호를 확인하거나, 가입 확인 메일의 링크를 "
                         f"먼저 눌러 주세요. ({e})")
    with t_up, st.form("signup"):
        email = st.text_input("이메일", key="su_email")
        pw = st.text_input("비밀번호 (8자 이상)", type="password", key="su_pw")
        pw2 = st.text_input("비밀번호 확인", type="password", key="su_pw2")
        agree = st.checkbox("복용약·생년월일·임신 여부 등 건강 관련 정보를 서비스 이용을 위해 저장하는 데 동의합니다.")
        if st.form_submit_button("가입하기", type="primary"):
            if len(pw) < 8 or pw != pw2:
                st.error("비밀번호는 8자 이상이고, 두 번 똑같이 입력해야 해요.")
            elif not agree:
                st.error("정보 저장에 동의해야 가입할 수 있어요.")
            else:
                client = create_client(SB_URL, SB_ANON)
                try:
                    res = client.auth.sign_up({"email": email.strip(), "password": pw})
                    if res.session:
                        st.session_state.sb, st.session_state.sb_email = client, res.user.email
                        st.rerun()
                    st.success("가입 확인 메일을 보냈어요. 메일의 링크를 누른 뒤 로그인해 주세요.")
                except Exception as e:
                    st.error(f"가입하지 못했어요. ({e})")
    st.stop()


data = load_data()
if ONLINE:
    login_gate()
    store = SupabaseStore(st.session_state.sb, admin_client())
else:
    store = local_store()
API_ON = bool(mfds_api.get_key())
TIMES = ["아침", "점심", "저녁", "자기 전"]

# 경고 종류별 아이콘, 등급, 설명, 행동 요령
INFO = {
    "기피성분": {
        "icon": "🚫", "level": "금기",
        "what": "프로필에 '먹기 힘든(피해야 할) 성분'으로 등록해 둔 성분이 들어 있는 약이에요.",
        "todo": "복용 전에 의사나 약사에게 이 성분을 피해야 한다고 알리고 대체약이 있는지 물어보세요."},
    "병용금기": {
        "icon": "🔴", "level": "금기",
        "what": "두 약을 함께 복용하면 약의 효과가 지나치게 강해지거나 약해지고, "
                "심각한 부작용이 생길 수 있어 식품의약품안전처가 함께 사용하지 않도록 지정한 조합이에요.",
        "todo": "임의로 약을 끊지 말고, 처방한 의사나 약사에게 두 약을 모두 복용 중이라는 사실을 꼭 알리세요."},
    "연령금기": {
        "icon": "🎂", "level": "금기",
        "what": "특정 나이대에서는 안전성이 확인되지 않았거나 위험할 수 있어 사용하지 않도록 지정된 약이에요.",
        "todo": "나이에 맞는 약인지 처방한 의사나 약사에게 확인하세요."},
    "임부금기": {
        "icon": "🤰", "level": "금기",
        "what": "임신 중 복용하면 태아에게 해로울 수 있어 사용을 피하도록 지정된 약이에요(1등급).",
        "todo": "임신 중이거나 임신 가능성이 있다면 복용 전에 반드시 의사와 상의하세요."},
    "상호작용주의": {
        "icon": "🟠", "level": "주의",
        "what": "함께 먹는 것이 금지된 조합은 아니지만, 함께 먹으면 부작용이 커지거나 약효가 달라질 수 있어 "
                "흔히 주의하는 조합이에요.",
        "todo": "처방대로 복용하되, 두 약을 함께 먹고 있다는 걸 의사·약사에게 알려 주세요."},
    "성분중복": {
        "icon": "🔁", "level": "주의",
        "what": "서로 다른 이름의 약에 같은 성분이 들어 있어요. 함께 먹으면 그 성분을 "
                "생각보다 많이 먹게 되어 과다 복용이 될 수 있어요.",
        "todo": "두 약을 모두 먹어야 하는지 약사에게 확인하세요."},
    "효능군중복": {
        "icon": "🧩", "level": "주의",
        "what": "성분은 다르지만 효과가 비슷한 약이 겹쳐 있어요. 효과보다 부작용이 먼저 커질 수 있어요.",
        "todo": "같은 목적의 약을 두 군데서 받은 건 아닌지 약사에게 확인하세요."},
    "임부주의": {
        "icon": "🤱", "level": "주의",
        "what": "임신 중 안전성이 충분히 확인되지 않았거나, 꼭 필요할 때만 쓰도록 권장되는 약이에요(2등급 등).",
        "todo": "임신 중이라면 계속 복용해도 되는지 의사와 상의하세요."},
    "노인주의": {
        "icon": "🟡", "level": "주의",
        "what": "65세 이상 어르신은 간·신장 기능 등이 약해져 이 약의 부작용이 더 쉽게 나타날 수 있어 "
                "신중하게 사용해야 하는 약이에요. 먹으면 안 된다는 뜻은 아니에요.",
        "todo": "처방대로 복용하되, 평소와 다른 증상이 생기면 바로 의사·약사와 상의하세요."},
    "분할주의": {
        "icon": "✂️", "level": "주의",
        "what": "프로필에 '알약을 쪼개거나 갈아서 먹는다'고 등록했는데, 서방형·장용성 같은 특수 제형으로 보이는 약이에요.",
        "todo": "쪼개거나 갈아도 되는 약인지 약사에게 확인하고, 안 되면 다른 제형이 있는지 물어보세요."},
}
ORDER = list(INFO)


# ─────────────────────────────────────────
# 2. 프로필
# ─────────────────────────────────────────
def avoid_label(x):
    return f"[약효군] {CLASSES[x[6:]][0]}" if x.startswith("class:") else data.label(x)


AVOID_OPTIONS = [f"class:{k}" for k, v in CLASSES.items() if v[2] or k in ("K_SUPP", "QUINOLONE", "TETRA")] \
    + data.vocab


def profile_form(p=None, key="new"):
    """프로필 입력 폼. 저장하면 id 반환"""
    p = p or {}
    with st.form(f"profile_{key}"):
        name = st.text_input("이름(별칭)", value=p.get("name", ""), placeholder="예: 나, 어머니")
        bd = date.fromisoformat(p["birthdate"]) if p.get("birthdate") else None
        birth = st.date_input("생년월일", value=bd, min_value=date(1900, 1, 1), max_value=date.today(),
                              format="YYYY-MM-DD", help="영유아는 개월 수까지 정확히 계산돼요.")
        preg = st.checkbox("임신 중이거나 임신 가능성이 있음", value=bool(p.get("pregnant")))
        crush = st.checkbox("알약을 쪼개거나 갈아서 먹음 (삼키기 어려움)", value=bool(p.get("crush")))
        cur = [a for a in p.get("avoid", []) if a in AVOID_OPTIONS]
        extra_cur = [a for a in p.get("avoid", []) if a not in AVOID_OPTIONS]
        avoid = st.multiselect("먹기 힘든 성분·약효군 (알레르기, 부작용 경험 등)", AVOID_OPTIONS,
                               default=cur, format_func=avoid_label,
                               placeholder="한글이나 영문으로 검색 (예: 아스피린, 소염진통제)")
        extra = st.text_input("목록에 없는 성분 직접 입력 (쉼표로 구분)", value=", ".join(extra_cur))
        memo = st.text_area("메모", value=p.get("memo", ""), placeholder="예: 페니실린 알레르기, 신장 기능 저하")
        if st.form_submit_button("💾 저장", type="primary"):
            if not name.strip():
                st.error("이름을 입력해 주세요.")
                return None
            if not birth:
                st.error("생년월일을 입력해 주세요. 연령·노인 주의 확인에 필요해요.")
                return None
            typed = [data.normalize(x) for x in extra.split(",") if x.strip()]
            return store.save_profile(p.get("id"), name.strip(), birth, preg, crush,
                                      list(dict.fromkeys(avoid + typed)), memo)
    return None


profiles = store.profiles()
if not profiles:
    st.title("💊 내 약 지킴이")
    st.write("먼저 약을 먹는 사람의 프로필을 만들어 주세요. 가족 프로필도 여러 개 만들 수 있어요.")
    if (pid := profile_form()) is not None:
        st.session_state.pid = pid
        st.rerun()
    st.stop()

ids = [p["id"] for p in profiles]
if st.session_state.get("pid") not in ids:
    st.session_state.pid = ids[0]
names = {p["id"]: p["name"] for p in profiles}

with st.sidebar:
    st.header("👤 프로필")
    pid = st.selectbox("누구의 약인가요?", ids, index=ids.index(st.session_state.pid),
                       format_func=lambda i: names[i])
    st.session_state.pid = pid
    prow = next(p for p in profiles if p["id"] == pid)
    prof = Profile(name=prow["name"],
                   birthdate=date.fromisoformat(prow["birthdate"]) if prow["birthdate"] else None,
                   pregnant=bool(prow["pregnant"]), crush=bool(prow["crush"]), avoid=list(prow["avoid"]))
    st.write(f"**{prof.age_text()}**" + (" · 임신 중" if prof.pregnant else ""))
    if prof.avoid:
        st.caption("피할 성분: " + ", ".join(avoid_label(a) for a in prof.avoid))
    st.caption("프로필 수정·추가는 '👤 프로필' 탭에서 할 수 있어요.")
    if ONLINE:
        st.caption(f"로그인: {st.session_state.sb_email}")
        if st.button("로그아웃"):
            try:
                st.session_state.sb.auth.sign_out()
            except Exception:
                pass
            for k in list(st.session_state):
                del st.session_state[k]
            st.rerun()
    st.divider()
    st.markdown("**아이콘 안내**")
    for k, v in INFO.items():
        st.caption(f"{v['icon']} {k} ({v['level']})")
    st.divider()
    st.caption("⚠️ 이 서비스는 참고용입니다. 약의 복용·중단·변경은 "
               "반드시 의사 또는 약사와 상담하세요.")
    st.caption("데이터 출처: 식품의약품안전처 의약품안전사용서비스(DUR) "
               "품목리스트 (2026년 6월 기준, 공공데이터포털)")


# ─────────────────────────────────────────
# 3. 내 약 불러오기
# ─────────────────────────────────────────
rows = store.meds(pid)
cache = store.cache_get(r["product_key"] for r in rows if not r["product_key"].startswith("note:"))


def to_med(key, label=None):
    """저장된 key → 검사용 Med (DUR 약은 공동 캐시의 전체 성분으로 보강)"""
    if key.startswith("note:"):
        return note_med(key, label)
    if key.startswith("api-"):
        return med_from_cache(cache[key]) if key in cache else None
    row = data.product_row(key)
    if row is None:
        return None
    m = data.med_from_row(row)
    if key in cache:
        m.extra_ingrs = frozenset(set(m.extra_ingrs) | (set(cache[key]["ingredients"]) - set(m.dur_ingrs)))
    return m


def enrich_full_ingredients(code, pname):
    """DUR 약을 추가할 때 식약처 허가정보로 전체 주성분을 받아 공동 캐시에 저장 (이름이 정확히 같을 때만)"""
    if not API_ON or code in cache:
        return
    try:
        res = mfds_api.search(short_name(pname), rows=10)
    except Exception:
        return
    target = norm_drug_name(short_name(pname))
    for r in res:
        if norm_drug_name(r["name"]) == target:
            ings = data.parse_ingredients(r["ingredients_raw"])
            store.cache_put(code, r["name"], ings, r["ingredients_raw"])
            return


my = []
for r in rows:
    m = to_med(r["product_key"], r.get("label"))
    if m:
        m.times, m.med_id = r["times"], r["id"]
        my.append(m)
meds = [m for m in my if m.ingrs]          # 성분을 알아야 검사 가능
findings = analyze_all(meds, prof, data)

st.title("💊 내 약 지킴이")
st.write("복용 중인 약을 등록하면 복약 시간을 관리하고, "
         "함께 먹으면 안 되는 약을 알려드려요.")

tab1, tab2, tab3, tab4 = st.tabs(["📝 내 약 등록", "✅ 오늘의 복약", "⚠️ 안전성 확인", "👤 프로필"])


def preview(cand):
    """등록 전 미리보기 경고"""
    pre = single_checks(cand, prof, data) if cand.ingrs else []
    for d in meds:
        if d.key != cand.key and cand.ingrs:
            pre += pair_checks(cand, d, data)
    if not cand.ingrs:
        st.info("성분 정보가 없어 안전성 확인 대상에서 제외돼요.")
    elif pre:
        lines = []
        for f in pre:
            icon = INFO[f["종류"]]["icon"]
            others = [n for n in f["약"] if n != cand.name]
            if others:
                lines.append(f"{icon} **{f['종류']}**: 내 약 '{short_name(others[0])}'과(와) 함께 주의")
            else:
                lines.append(f"{icon} **{f['종류']}** 대상 약이에요")
        box = st.error if any(f["level"] == "금기" for f in pre) else st.warning
        box("이 약을 추가하기 전에 확인하세요\n\n" + "\n\n".join(dict.fromkeys(lines))
            + "\n\n자세한 내용은 '안전성 확인' 탭에서 볼 수 있어요.")
    else:
        st.success("✅ 현재 정보로는 확인된 주의 사항이 없어요.")


# ─────────────────────────────────────────
# 4. 탭1: 약 등록
# ─────────────────────────────────────────
with tab1:
    st.subheader("약 검색해서 추가하기")
    if st.session_state.pop("clear_kw", False):         # 추가 후 검색창 비우기
        st.session_state.kw = ""
    keyword = st.text_input("약 이름 또는 성분명을 2글자 이상 입력하세요", key="kw",
                            placeholder="예: 타이레놀, 세레콕시브, 아스피린, celecoxib")
    if len(keyword.strip()) >= 2:
        kw = keyword.strip()
        found = data.search(kw)
        cached = store.cache_search(kw)                      # 이전에 식약처에서 받아 둔 약 (공동 DB)
        options = [("cache", r["key"]) for r in cached] + [("dur", c) for c in found["제품코드"]]
        api_res = []
        if not options and API_ON:                           # DUR·공동 DB에 없으면 식약처에 자동 조회
            if st.session_state.get("api_q") != kw:
                try:
                    with st.spinner("식약처 허가정보에서 찾는 중..."):
                        st.session_state.api_res = mfds_api.search(kw)
                except Exception as e:
                    st.session_state.api_res = []
                    st.error(f"식약처 조회에 실패했어요. 잠시 후 다시 시도해 주세요. ({e})")
                st.session_state.api_q = kw
            api_res = [r for r in st.session_state.get("api_res", [])
                       if data.parse_ingredients(r["ingredients_raw"])]
            options = [("api", i) for i in range(len(api_res))]
        cmap = {r["key"]: r for r in cached}
        fmap = found.set_index("제품코드")

        def label(o):
            try:
                if o[0] == "cache":
                    return f"{cmap[o[1]]['name']}  ·  식약처 허가정보"
                if o[0] == "api":
                    return f"{api_res[o[1]]['name']}  ·  식약처 허가정보"
                return f"{fmap.loc[o[1], '제품명']}  ·  {fmap.loc[o[1], '업체명']}"
            except (KeyError, IndexError):       # 이전 화면의 선택값이 남아 있을 때
                return str(o[1])

        if not options:
            st.info("찾는 약이 없어요. 이름을 다시 확인하거나(예: '정', '캡슐' 빼고 검색), 영양제·건강기능식품이면 "
                    "아래 '영양제 등 추가'를 이용하세요." +
                    ("" if API_ON else " (식약처 API 키를 설정하면 DUR 목록 밖의 약도 찾아요.)"))
        else:
            sel = st.selectbox(f"검색 결과 {len(options)}건", options, format_func=label)
            if sel[0] == "api":
                r = api_res[sel[1]]
                cand = Med(key=f"api-{r['item_seq'] or norm_drug_name(r['name'])}", name=r["name"],
                           extra_ingrs=frozenset(data.parse_ingredients(r["ingredients_raw"])))
            elif sel[0] == "cache":
                cand = med_from_cache(cmap[sel[1]])
            else:
                cand = to_med(sel[1])
            if cand.ingrs:
                st.caption("🧪 성분: " + ", ".join(data.label(i) for i in sorted(cand.ingrs)))
            preview(cand)
            times = st.multiselect("복용 시간", TIMES, default=["아침"], key="t_search")
            if st.button("➕ 내 약에 추가", type="primary"):
                if sel[0] == "api":                          # 공식 데이터만 공동 DB에 저장
                    store.cache_put(cand.key, cand.name, sorted(cand.ingrs), r["ingredients_raw"])
                elif sel[0] == "dur":
                    enrich_full_ingredients(cand.key, cand.name)
                if store.add_med(pid, cand.key, times):
                    st.session_state.clear_kw = True
                    st.rerun()
                else:
                    st.warning("이미 등록된 약이에요.")

    with st.expander("🌿 영양제·건강기능식품 등 추가 (복약 시간 관리만)"):
        st.caption("의약품이 아닌 제품은 성분 정보가 없어 안전성 확인에서 제외돼요. "
                   "복약 체크리스트에는 함께 나와요.")
        note = st.text_input("제품 이름", key="note_name", placeholder="예: 오메가3, 종합비타민")
        n_times = st.multiselect("복용 시간", TIMES, default=["아침"], key="t_note")
        if st.button("추가", key="note_btn") and note.strip():
            store.add_med(pid, f"note:{note.strip()}", n_times, label=note.strip())
            st.rerun()

    st.divider()
    st.subheader(f"📋 {prof.name}님이 먹는 약 ({len(my)}개)")
    if not my:
        st.write("아직 등록한 약이 없어요.")
    for d in my:
        icons = sorted({INFO[f["종류"]]["icon"] for f in findings if d.name in f["약"]})
        c1, c2, c3 = st.columns([5, 1, 1])
        badge = " ".join(icons) if icons else ("➖" if not d.ingrs else "✅")
        note = "  \n_성분 정보가 없어 안전성 확인 대상 아님_" if not d.ingrs else ""
        c1.write(f"{badge} **{short_name(d.name)}**  \n복용: {', '.join(d.times) or '시간 미지정'}{note}")
        with c2.popover("⏰"):
            nt = st.multiselect("복용 시간", TIMES, default=d.times, key=f"edit_{d.med_id}")
            if st.button("저장", key=f"save_{d.med_id}"):
                store.update_times(d.med_id, nt)
                st.rerun()
        if c3.button("삭제", key=f"del_{d.med_id}"):
            store.remove_med(d.med_id)
            st.rerun()
    if findings:
        st.caption("아이콘이 붙은 약은 '안전성 확인' 탭에서 자세한 설명을 볼 수 있어요.")

# ─────────────────────────────────────────
# 5. 탭2: 오늘의 복약 (날짜별 저장)
# ─────────────────────────────────────────
with tab2:
    today = date.today().isoformat()
    st.subheader(f"오늘의 복약 체크리스트 ({today})")
    taken = store.taken(pid, today)

    def toggle(slot, mid, key):
        store.set_taken(pid, today, slot, mid, st.session_state[key])

    total, done = 0, 0
    for t in TIMES:
        items = [d for d in my if t in d.times]
        if not items:
            continue
        st.markdown(f"#### 🕒 {t}")
        for d in items:
            total += 1
            k = f"chk_{pid}_{today}_{t}_{d.med_id}"
            val = (t, d.med_id) in taken
            if st.checkbox(short_name(d.name), value=val, key=k, on_change=toggle, args=(t, d.med_id, k)):
                done += 1
    if total == 0:
        st.write("'내 약 등록' 탭에서 약과 복용 시간을 먼저 등록해 주세요.")
    else:
        st.progress(done / total, text=f"오늘 {total}회 중 {done}회 복용 완료")
        flag = f"balloons_{pid}_{today}"
        if done == total and not st.session_state.get(flag):
            st.balloons()
            st.session_state[flag] = True        # 하루 한 번만
        elif done < total:
            st.session_state[flag] = False

        days = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        cnt = store.intake_counts(pid, days)
        chart = pd.DataFrame({"날짜": [x[5:] for x in days],
                              "복용률(%)": [round(100 * cnt.get(x, 0) / total) for x in days]}).set_index("날짜")
        st.markdown("##### 최근 7일 복용률")
        st.bar_chart(chart, height=180)
        st.caption("현재 복용 계획(하루 %d회) 기준으로 계산했어요." % total)

# ─────────────────────────────────────────
# 6. 탭3: 안전성 확인
# ─────────────────────────────────────────
with tab3:
    st.subheader("함께 먹어도 괜찮을까?")
    if not meds:
        st.write("'내 약 등록' 탭에서 약을 등록하면 자동으로 확인해 드려요.")
    else:
        n_ban = sum(f["level"] == "금기" for f in findings)
        c1, c2, c3 = st.columns(3)
        c1.metric("확인한 약", f"{len(meds)}개")
        c2.metric("🔴 금기", f"{n_ban}건")
        c3.metric("🟡 주의", f"{len(findings) - n_ban}건")
        if len(my) >= 5:
            st.info(f"💡 {len(my)}가지 약을 먹고 있어요. 5가지 이상이면 '다제복용'으로, 정기적으로 "
                    "약사·의사와 전체 약 목록을 함께 점검받는 것이 좋아요.")
        if not findings:
            st.success("등록된 약에서 금기·주의 사항이 발견되지 않았어요.")

        for kind in ORDER:
            items = [f for f in findings if f["종류"] == kind]
            if not items:
                continue
            info = INFO[kind]
            st.markdown(f"### {info['icon']} {kind} ({len(items)}건)")
            st.caption(f"**{kind}란?** {info['what']}")
            for f in items:
                box = st.error if f["level"] == "금기" else st.warning
                names_ = " + ".join(f"**{short_name(n)}**" for n in f["약"])
                ings = " / ".join(data.label(i) for i in dict.fromkeys(f["성분"]))
                text = f"{names_}\n\n🧪 성분: {ings}\n\n❓ **왜 주의해야 하나요?** {f['사유']}"
                if f["참고"]:
                    text += f"\n\n📌 **참고**: {f['참고']}"
                text += f"\n\n👉 **어떻게 하나요?** {info['todo']}"
                box(text)

        if prof.age_days() is not None and prof.age_days() < 65 * 365.25:
            st.caption("※ 노인주의 항목은 나이가 65세 이상일 때만 확인합니다.")
        if not prof.pregnant:
            st.caption("※ 임부금기 항목은 프로필에서 '임신 중'을 선택했을 때만 확인합니다.")

    st.divider()
    st.caption("※ 'DUR 정보 없음'이 '안전함'을 뜻하지는 않습니다. 직접 입력한 약(영양제 등)은 "
               "확인 대상에서 제외됩니다. 성분 중복은 이 앱이 자체적으로 확인하는 항목이며 DUR 공식 항목이 아닙니다.")
    st.caption("※ 상호작용주의·효능군중복·분할주의·기피성분도 이 앱이 자체적으로 확인하는 참고 항목이며 "
               "DUR 공식 항목이 아닙니다. '성분명 기준 확인'으로 표시된 항목은 제형에 따라 실제와 다를 수 있습니다.")

# ─────────────────────────────────────────
# 7. 탭4: 프로필
# ─────────────────────────────────────────
with tab4:
    st.subheader(f"{prof.name}님 프로필")
    if profile_form(prow, key=f"edit_{pid}") is not None:
        st.success("저장했어요.")
        st.rerun()
    with st.expander("➕ 새 프로필 추가 (가족 등)"):
        if (nid := profile_form(key="add")) is not None:
            st.session_state.pid = nid
            st.rerun()
    with st.expander("🗑️ 이 프로필 삭제"):
        sure = st.checkbox(f"'{prof.name}' 프로필과 복용약·복약 기록을 모두 삭제합니다.")
        if st.button("삭제", disabled=not sure):
            store.delete_profile(pid)
            st.session_state.pop("pid", None)
            st.rerun()
