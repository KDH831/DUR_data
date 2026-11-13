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
    combo_dict = {(r.성분코드A, r.성분코드B): (r.상세정보, r.비고) for r in combo.itertuples()}
    return drugs, combo_dict, elderly, age, preg

drugs, combo_dict, elderly, age_rules, preg = load_data()

TIMES = ["아침", "점심", "저녁", "자기 전"]

# 경고 종류별 아이콘, 이름, 설명, 행동 요령
INFO = {
    "병용금기": {
        "icon": "🔴", "level": "금기",
        "what": "두 약을 함께 복용하면 약의 효과가 지나치게 강해지거나 약해지고, "
                "심각한 부작용이 생길 수 있어 식품의약품안전처가 함께 사용하지 않도록 지정한 조합이에요.",
        "todo": "임의로 약을 끊지 말고, 처방한 의사나 약사에게 두 약을 모두 복용 중이라는 사실을 꼭 알리세요."},
    "성분중복": {
        "icon": "🔁", "level": "주의",
        "what": "서로 다른 이름의 약에 같은 성분이 들어 있어요. 함께 먹으면 그 성분을 "
                "생각보다 많이 먹게 되어 과다 복용이 될 수 있어요.",
        "todo": "두 약을 모두 먹어야 하는지 약사에게 확인하세요."},
    "노인주의": {
        "icon": "🟡", "level": "주의",
        "what": "65세 이상 어르신은 간·신장 기능 등이 약해져 이 약의 부작용이 더 쉽게 나타날 수 있어 "
                "신중하게 사용해야 하는 약이에요. 먹으면 안 된다는 뜻은 아니에요.",
        "todo": "처방대로 복용하되, 평소와 다른 증상이 생기면 바로 의사·약사와 상의하세요."},
    "연령금기": {
        "icon": "🎂", "level": "금기",
        "what": "특정 나이대에서는 안전성이 확인되지 않았거나 위험할 수 있어 사용하지 않도록 지정된 약이에요.",
        "todo": "나이에 맞는 약인지 처방한 의사나 약사에게 확인하세요."},
    "임부금기": {
        "icon": "🤰", "level": "금기",
        "what": "임신 중 복용하면 태아에게 해로울 수 있어 사용을 피하도록 지정된 약이에요.",
        "todo": "임신 중이거나 임신 가능성이 있다면 복용 전에 반드시 의사와 상의하세요."},
}

if "my_drugs" not in st.session_state:
    st.session_state.my_drugs = []

# ─────────────────────────────────────────
# 2. 안전성 검사 함수 (두 탭에서 함께 사용)
# ─────────────────────────────────────────
def age_matches(rule, user_age):
    """연령금기 규칙이 사용자 나이에 해당하는지 확인 (개월 단위로 비교)."""
    n = float(rule["특정연령"])
    unit = rule["특정연령단위"]
    limit = n * 12 if "세" in unit else n if "개월" in unit else n / 4.345
    me = user_age * 12
    cond = rule["연령처리조건"]
    if "미만" in cond: return me < limit
    if "이하" in cond: return me <= limit
    if "이상" in cond: return me >= limit
    if "초과" in cond: return me > limit
    return False

def single_checks(d, user_age, pregnant):
    """약 한 개에 대한 검사: 노인주의, 연령금기, 임부금기"""
    out = []
    if user_age >= 65:
        for r in elderly[elderly["성분코드"] == d["성분코드"]].itertuples():
            out.append({"종류": "노인주의", "약": [d["제품명"]], "성분": [d["성분명"]],
                        "사유": r.상세정보, "참고": ""})
    for _, r in age_rules[age_rules["성분코드"] == d["성분코드"]].iterrows():
        if age_matches(r, user_age):
            cond = f"{r['특정연령']}{r['특정연령단위'].split()[0]} {r['연령처리조건'].split()[0]} 사용 금기"
            out.append({"종류": "연령금기", "약": [d["제품명"]], "성분": [d["성분명"]],
                        "사유": r["상세정보"], "참고": cond})
    if pregnant:
        for r in preg[preg["성분코드"] == d["성분코드"]].itertuples():
            out.append({"종류": "임부금기", "약": [d["제품명"]], "성분": [d["성분명"]],
                        "사유": r.상세정보, "참고": f"금기등급 {r.금기등급}"})
    return out

def pair_checks(a, b):
    """약 두 개에 대한 검사: 병용금기, 성분중복"""
    out = []
    hit = combo_dict.get((a["성분코드"], b["성분코드"])) or \
          combo_dict.get((b["성분코드"], a["성분코드"]))
    if hit:
        out.append({"종류": "병용금기", "약": [a["제품명"], b["제품명"]],
                    "성분": [a["성분명"], b["성분명"]], "사유": hit[0], "참고": hit[1]})
    if a["성분명"] == b["성분명"]:
        out.append({"종류": "성분중복", "약": [a["제품명"], b["제품명"]],
                    "성분": [a["성분명"]], "사유": "같은 성분이 두 약에 모두 들어 있음", "참고": ""})
    return out

def analyze_all(meds, user_age, pregnant):
    findings = []
    for a, b in combinations(meds, 2):
        findings += pair_checks(a, b)
    for d in meds:
        findings += single_checks(d, user_age, pregnant)
    return findings

def short_name(name):
    """'제품명_(용량)'에서 용량 부분을 떼어 짧게 표시"""
    return name.split("_(")[0]

# ─────────────────────────────────────────
# 3. 사이드바
# ─────────────────────────────────────────
with st.sidebar:
    st.header("👤 사용자 정보")
    user_age = st.number_input("나이 (세)", min_value=0, max_value=120, value=70)
    pregnant = st.checkbox("임신 중이거나 임신 가능성이 있음")
    st.divider()
    st.markdown("**아이콘 안내**")
    for k, v in INFO.items():
        st.caption(f"{v['icon']} {k} ({v['level']})")
    st.divider()
    st.caption("⚠️ 이 서비스는 참고용입니다. 약의 복용·중단·변경은 "
               "반드시 의사 또는 약사와 상담하세요.")
    st.caption("데이터 출처: 식품의약품안전처 의약품안전사용서비스(DUR) "
               "품목리스트 (2026년 6월 기준, 공공데이터포털)")

st.title("💊 내 약 지킴이")
st.write("복용 중인 약을 등록하면 복약 시간을 관리하고, "
         "함께 먹으면 안 되는 약을 알려드려요.")

meds = [d for d in st.session_state.my_drugs if d["성분코드"]]
findings = analyze_all(meds, user_age, pregnant)

tab1, tab2, tab3 = st.tabs(["📝 내 약 등록", "✅ 오늘의 복약", "⚠️ 안전성 확인"])

# ─────────────────────────────────────────
# 4. 탭1: 약 등록 (등록 전 미리 경고)
# ─────────────────────────────────────────
with tab1:
    st.subheader("약 검색해서 추가하기")
    keyword = st.text_input("약 이름 또는 성분명을 2글자 이상 입력하세요",
                            placeholder="예: 세레콕시브, 아스피린, celecoxib")

    if len(keyword.strip()) >= 2:
        kw = keyword.strip()
        mask = drugs["제품명"].str.contains(kw, regex=False, na=False) | \
               drugs["성분명"].str.contains(kw, case=False, regex=False, na=False)
        found = drugs[mask].head(100)
        if found.empty:
            st.info("DUR 목록에서 찾지 못했어요. 아래 '직접 입력'으로 추가할 수 있어요.")
        else:
            labels = [f"{r.제품명}  ·  {r.업체명}" for r in found.itertuples()]
            idx = st.selectbox(f"검색 결과 {len(found)}건", range(len(found)),
                               format_func=lambda i: labels[i])
            cand = found.iloc[idx].to_dict()

            # 등록 전 미리보기 경고
            pre = single_checks(cand, user_age, pregnant)
            for d in meds:
                if d["제품코드"] != cand["제품코드"]:
                    pre += pair_checks(cand, d)
            if pre:
                lines = []
                for f in pre:
                    icon = INFO[f["종류"]]["icon"]
                    if f["종류"] in ("병용금기", "성분중복"):
                        other = [n for n in f["약"] if n != cand["제품명"]][0]
                        lines.append(f"{icon} **{f['종류']}**: 내 약 '{short_name(other)}'과(와) 함께 주의")
                    else:
                        lines.append(f"{icon} **{f['종류']}** 대상 약이에요")
                box = st.error if any(INFO[f["종류"]]["level"] == "금기" for f in pre) else st.warning
                box("이 약을 추가하기 전에 확인하세요\n\n" + "\n\n".join(lines)
                    + "\n\n자세한 내용은 '안전성 확인' 탭에서 볼 수 있어요.")
            else:
                st.success("✅ 현재 정보로는 확인된 주의 사항이 없어요.")

            times = st.multiselect("복용 시간", TIMES, default=["아침"], key="t_search")
            if st.button("➕ 내 약에 추가", type="primary"):
                if any(d["제품코드"] == cand["제품코드"] for d in st.session_state.my_drugs):
                    st.warning("이미 등록된 약이에요.")
                else:
                    st.session_state.my_drugs.append({
                        "제품코드": cand["제품코드"], "제품명": cand["제품명"],
                        "성분코드": cand["성분코드"], "성분명": cand["성분명"], "시간": times})
                    st.rerun()

    with st.expander("목록에 없는 약 직접 입력 (영양제 등)"):
        custom = st.text_input("약 이름", key="custom_name")
        c_times = st.multiselect("복용 시간", TIMES, default=["아침"], key="t_custom")
        if st.button("➕ 직접 추가") and custom.strip():
            st.session_state.my_drugs.append({
                "제품코드": "직접입력-" + custom.strip(), "제품명": custom.strip(),
                "성분코드": "", "성분명": "", "시간": c_times})
            st.rerun()

    st.divider()
    st.subheader(f"📋 내가 먹는 약 ({len(st.session_state.my_drugs)}개)")
    if not st.session_state.my_drugs:
        st.write("아직 등록한 약이 없어요.")
    for i, d in enumerate(st.session_state.my_drugs):
        icons = sorted({INFO[f["종류"]]["icon"] for f in findings if d["제품명"] in f["약"]})
        c1, c2 = st.columns([5, 1])
        badge = " ".join(icons) if icons else ("➖" if not d["성분코드"] else "✅")
        note = "  \n_DUR 확인 대상 아님_" if not d["성분코드"] else ""
        c1.write(f"{badge} **{short_name(d['제품명'])}**  \n복용: {', '.join(d['시간']) or '시간 미지정'}{note}")
        if c2.button("삭제", key=f"del_{i}"):
            st.session_state.my_drugs.pop(i)
            st.rerun()
    if findings:
        st.caption("아이콘이 붙은 약은 '안전성 확인' 탭에서 자세한 설명을 볼 수 있어요.")

# ─────────────────────────────────────────
# 5. 탭2: 오늘의 복약 체크리스트
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
            if st.checkbox(short_name(d["제품명"]), key=f"chk_{t}_{d['제품코드']}"):
                done += 1
    if total == 0:
        st.write("'내 약 등록' 탭에서 약과 복용 시간을 먼저 등록해 주세요.")
    else:
        st.progress(done / total, text=f"오늘 {total}회 중 {done}회 복용 완료")
        if done == total:
            st.balloons()

# ─────────────────────────────────────────
# 6. 탭3: 안전성 확인 (자세한 설명)
# ─────────────────────────────────────────
with tab3:
    st.subheader("함께 먹어도 괜찮을까?")

    if not meds:
        st.write("'내 약 등록' 탭에서 검색으로 약을 등록하면 자동으로 확인해 드려요.")
    else:
        n_ban = sum(INFO[f["종류"]]["level"] == "금기" for f in findings)
        n_warn = len(findings) - n_ban
        c1, c2, c3 = st.columns(3)
        c1.metric("확인한 약", f"{len(meds)}개")
        c2.metric("🔴 금기", f"{n_ban}건")
        c3.metric("🟡 주의", f"{n_warn}건")

        if not findings:
            st.success("등록된 약에서 DUR 금기·주의 사항이 발견되지 않았어요.")

        order = ["병용금기", "연령금기", "임부금기", "성분중복", "노인주의"]
        for kind in order:
            items = [f for f in findings if f["종류"] == kind]
            if not items:
                continue
            info = INFO[kind]
            st.markdown(f"### {info['icon']} {kind} ({len(items)}건)")
            st.caption(f"**{kind}란?** {info['what']}")

            for f in items:
                box = st.error if info["level"] == "금기" else st.warning
                names = " + ".join(f"**{short_name(n)}**" for n in f["약"])
                ings = " / ".join(dict.fromkeys(f["성분"]))
                text = f"{names}\n\n🧪 성분: {ings}\n\n❓ **왜 주의해야 하나요?** {f['사유']}"
                if f["참고"]:
                    text += f"\n\n📌 **참고**: {f['참고']}"
                text += f"\n\n👉 **어떻게 하나요?** {info['todo']}"
                box(text)

        if user_age < 65:
            st.caption("※ 노인주의 항목은 나이가 65세 이상일 때만 확인합니다.")
        if not pregnant:
            st.caption("※ 임부금기 항목은 사이드바에서 '임신 중'을 선택했을 때만 확인합니다.")

    st.divider()
    st.caption("※ 'DUR 정보 없음'이 '안전함'을 뜻하지는 않습니다. 직접 입력한 약은 확인 대상에서 "
               "제외됩니다. 성분 중복은 이 앱이 자체적으로 확인하는 항목이며 DUR 공식 항목이 아닙니다.")
