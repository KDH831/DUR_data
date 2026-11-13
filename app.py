import streamlit as st
import pandas as pd
from itertools import combinations

st.set_page_config(page_title="내 약 지킴이", page_icon="💊", layout="centered")

# ─────────────────────────────────────────
# 1. 데이터 불러오기 (처음 한 번만 읽고 기억해 둠)
# ─────────────────────────────────────────
@st.cache_data
def load_data():
    drugs = pd.read_csv("drugs.csv", dtype=str)
    combo = pd.read_csv("combo.csv", dtype=str).fillna("")
    elderly = pd.read_csv("elderly.csv", dtype=str)
    age = pd.read_csv("age.csv", dtype=str)
    preg = pd.read_csv("pregnancy.csv", dtype=str)
    # 병용금기를 빠르게 찾기 위한 사전: (성분A, 성분B) → (사유, 비고)
    combo_dict = {(r.성분코드A, r.성분코드B): (r.상세정보, r.비고) for r in combo.itertuples()}
    return drugs, combo_dict, elderly, age, preg

drugs, combo_dict, elderly, age_rules, preg = load_data()

TIMES = ["아침", "점심", "저녁", "자기 전"]

if "my_drugs" not in st.session_state:
    st.session_state.my_drugs = []   # 등록한 약 목록

# ─────────────────────────────────────────
# 2. 사이드바: 사용자 정보
# ─────────────────────────────────────────
with st.sidebar:
    st.header("👤 사용자 정보")
    user_age = st.number_input("나이 (세)", min_value=0, max_value=120, value=70)
    pregnant = st.checkbox("임신 중이거나 임신 가능성이 있음")
    st.divider()
    st.caption("⚠️ 이 서비스는 참고용입니다. 약의 복용·중단·변경은 "
               "반드시 의사 또는 약사와 상담하세요.")
    st.caption("데이터 출처: 식품의약품안전처 의약품안전사용서비스(DUR) "
               "품목리스트 (2026년 6월 기준, 공공데이터포털)")

st.title("💊 내 약 지킴이")
st.write("복용 중인 약을 등록하면 복약 시간을 관리하고, "
         "함께 먹으면 안 되는 약을 알려드려요.")

tab1, tab2, tab3 = st.tabs(["📝 내 약 등록", "✅ 오늘의 복약", "⚠️ 안전성 확인"])

# ─────────────────────────────────────────
# 3. 탭1: 약 등록
# ─────────────────────────────────────────
with tab1:
    st.subheader("약 검색해서 추가하기")
    keyword = st.text_input("약 이름을 2글자 이상 입력하세요", placeholder="예: 아스피린, 타이레놀")

    if len(keyword.strip()) >= 2:
        found = drugs[drugs["제품명"].str.contains(keyword.strip(), regex=False, na=False)].head(100)
        if found.empty:
            st.info("DUR 목록에서 찾지 못했어요. 아래 '직접 입력'으로 추가할 수 있어요.")
        else:
            labels = [f"{r.제품명}  ·  {r.업체명}" for r in found.itertuples()]
            idx = st.selectbox(f"검색 결과 {len(found)}건", range(len(found)),
                               format_func=lambda i: labels[i])
            times = st.multiselect("복용 시간", TIMES, default=["아침"], key="t_search")
            if st.button("➕ 내 약에 추가", type="primary"):
                row = found.iloc[idx]
                if any(d["제품코드"] == row["제품코드"] for d in st.session_state.my_drugs):
                    st.warning("이미 등록된 약이에요.")
                else:
                    st.session_state.my_drugs.append({
                        "제품코드": row["제품코드"], "제품명": row["제품명"],
                        "성분코드": row["성분코드"], "성분명": row["성분명"],
                        "시간": times})
                    st.success(f"'{row['제품명']}'을(를) 추가했어요.")

    with st.expander("목록에 없는 약 직접 입력 (영양제 등)"):
        custom = st.text_input("약 이름", key="custom_name")
        c_times = st.multiselect("복용 시간", TIMES, default=["아침"], key="t_custom")
        if st.button("➕ 직접 추가") and custom.strip():
            st.session_state.my_drugs.append({
                "제품코드": "직접입력-" + custom.strip(), "제품명": custom.strip(),
                "성분코드": "", "성분명": "", "시간": c_times})
            st.success(f"'{custom.strip()}'을(를) 추가했어요. (안전성 확인 대상에서는 제외됩니다)")

    st.divider()
    st.subheader(f"📋 내가 먹는 약 ({len(st.session_state.my_drugs)}개)")
    if not st.session_state.my_drugs:
        st.write("아직 등록한 약이 없어요.")
    for i, d in enumerate(st.session_state.my_drugs):
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{d['제품명']}**  \n복용: {', '.join(d['시간']) or '시간 미지정'}")
        if c2.button("삭제", key=f"del_{i}"):
            st.session_state.my_drugs.pop(i)
            st.rerun()

# ─────────────────────────────────────────
# 4. 탭2: 오늘의 복약 체크리스트
# ─────────────────────────────────────────
with tab2:
    st.subheader("오늘의 복약 체크리스트")
    total, done = 0, 0
    for t in TIMES:
        items = [d for d in st.session_state.my_drugs if t in d["시간"]]
        if not items:
            continue
        st.markdown(f"#### 🕒 {t}")
        for d in items:
            total += 1
            if st.checkbox(d["제품명"], key=f"chk_{t}_{d['제품코드']}"):
                done += 1
    if total == 0:
        st.write("'내 약 등록' 탭에서 약과 복용 시간을 먼저 등록해 주세요.")
    else:
        st.progress(done / total, text=f"오늘 {total}회 중 {done}회 복용 완료")
        if done == total:
            st.balloons()

# ─────────────────────────────────────────
# 5. 탭3: 안전성 확인
# ─────────────────────────────────────────
def age_matches(rule, user_age):
    """연령금기 규칙이 사용자 나이에 해당하는지 확인 (개월 단위로 비교)."""
    n = float(rule["특정연령"])
    unit = rule["특정연령단위"]
    limit = n * 12 if "세" in unit else n if "개월" in unit else n / 4.345  # 주 → 개월
    me = user_age * 12
    cond = rule["연령처리조건"]
    if "미만" in cond: return me < limit
    if "이하" in cond: return me <= limit
    if "이상" in cond: return me >= limit
    if "초과" in cond: return me > limit
    return False

with tab3:
    st.subheader("함께 먹어도 괜찮을까?")
    meds = [d for d in st.session_state.my_drugs if d["성분코드"]]

    if not meds:
        st.write("'내 약 등록' 탭에서 검색으로 약을 등록하면 자동으로 확인해 드려요.")
    else:
        warnings = 0

        # (1) 병용금기
        st.markdown("#### 🚫 병용금기 (함께 복용 금지)")
        found_combo = False
        for a, b in combinations(meds, 2):
            hit = combo_dict.get((a["성분코드"], b["성분코드"])) or \
                  combo_dict.get((b["성분코드"], a["성분코드"]))
            if hit:
                found_combo = True
                warnings += 1
                reason, note = hit
                msg = f"**{a['제품명']}** + **{b['제품명']}**\n\n사유: {reason}"
                if note:
                    msg += f"\n\n참고: {note}"
                st.error(msg)
        if not found_combo:
            st.success("등록된 약 사이에서 DUR 병용금기 조합이 발견되지 않았어요.")

        # (2) 같은 성분 중복
        dup = {}
        for d in meds:
            dup.setdefault(d["성분명"], []).append(d["제품명"])
        dups = {k: v for k, v in dup.items() if len(v) > 1}
        if dups:
            st.markdown("#### 🔁 같은 성분 중복")
            for ing, names in dups.items():
                warnings += 1
                st.warning(f"성분 **{ing}**이(가) 여러 약에 들어 있어요: "
                           + ", ".join(names) + "\n\n과다 복용이 되지 않도록 약사와 확인하세요.")

        # (3) 노인주의
        if user_age >= 65:
            st.markdown("#### 👵 노인주의 (65세 이상 주의 필요)")
            any_e = False
            for d in meds:
                for r in elderly[elderly["성분코드"] == d["성분코드"]].itertuples():
                    any_e = True
                    warnings += 1
                    st.warning(f"**{d['제품명']}**\n\n{r.상세정보}")
            if not any_e:
                st.success("노인주의 대상 약이 없어요.")

        # (4) 연령금기
        hits = []
        for d in meds:
            for _, r in age_rules[age_rules["성분코드"] == d["성분코드"]].iterrows():
                if age_matches(r, user_age):
                    hits.append((d, r))
        if hits:
            st.markdown("#### 🎂 연령금기")
            for d, r in hits:
                warnings += 1
                st.error(f"**{d['제품명']}** — {r['특정연령']}{r['특정연령단위'].split()[0]} "
                         f"{r['연령처리조건'].split()[0]} 금기\n\n{r['상세정보']}")

        # (5) 임부금기
        if pregnant:
            st.markdown("#### 🤰 임부금기")
            any_p = False
            for d in meds:
                for r in preg[preg["성분코드"] == d["성분코드"]].itertuples():
                    any_p = True
                    warnings += 1
                    st.error(f"**{d['제품명']}** (금기등급 {r.금기등급})\n\n{r.상세정보}")
            if not any_p:
                st.success("임부금기 대상 약이 없어요.")

        st.divider()
        if warnings:
            st.info(f"총 {warnings}건의 주의 사항이 있어요. 임의로 약을 끊지 말고 "
                    "의사·약사와 상담하세요.")
        st.caption("※ 'DUR 정보 없음'이 '안전함'을 뜻하지는 않습니다. "
                   "직접 입력한 약은 확인 대상에서 제외됩니다.")
