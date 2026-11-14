"""
검사 엔진 (Streamlit 없이도 동작 → 테스트·재사용 가능)

핵심 아이디어
  - 모든 검사는 '정규화된 성분명' 기준으로 할 수 있게 함
      rosuvastatin calcium (as rosuvastatin) → rosuvastatin
      acetaminophen(encapsulated)            → acetaminophen
      아세트아미노펜 / 염산메트포르민          → acetaminophen / metformin (한↔영 사전)
  - 약 1개 = 성분 N개 (복합제)
  - DUR 성분코드가 있는 약은 코드로 정확히 검사,
    코드가 없거나(자동 등록 약) DUR에 안 잡힌 추가 성분은 성분명으로 검사
"""
import os
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

import pandas as pd

from rules import CLASSES, PAIR_RULES

BASE = os.path.dirname(os.path.abspath(__file__))

# ══════════════════════════════════════════════════════════════
# 1. 성분명 정규화
# ══════════════════════════════════════════════════════════════
SALT_TAIL = {
    "hydrochloride", "hcl", "dihydrochloride", "hydrobromide", "hbr", "sulfate", "sulphate",
    "bisulfate", "phosphate", "maleate", "fumarate", "succinate", "tartrate", "bitartrate",
    "besylate", "besilate", "mesylate", "mesilate", "citrate", "acetate", "nitrate", "lactate",
    "gluconate", "tosylate", "camsylate", "orotate", "malate", "oxalate", "napadisilate",
    "sodium", "disodium", "trisodium", "dipotassium", "potassium", "calcium", "magnesium", "arginine", "lysine", "tromethamine",
    "hydrate", "monohydrate", "dihydrate", "trihydrate", "hemihydrate", "sesquihydrate",
    "pentahydrate", "anhydrous", "anhydride", "micronized", "medoxomil", "cilexetil",
    "etexilate", "axetil", "pivoxil", "proxetil", "mofetil", "salt", "base", "chloride",
    "bromide", "carbonate", "oxide",
}
HYDRATE = {"hydrate", "monohydrate", "dihydrate", "trihydrate", "hemihydrate",
           "sesquihydrate", "pentahydrate", "anhydrous", "micronized"}
MINERAL_HEAD = {"sodium", "potassium", "calcium", "magnesium", "aluminum", "aluminium",
                "ferrous", "ferric", "zinc", "lithium", "iron"}
EN_ALIAS = {"paracetamol": "acetaminophen", "acetylsalicylic acid": "aspirin",
            "salicylic acid acetate": "aspirin", "levothyroxine sodium": "levothyroxine",
            "chlorphenamine": "chlorpheniramine", "esomeprazol": "esomeprazole", "caffeine anhydrous": "caffeine", "anhydrous caffeine": "caffeine", "dexchlorphenamine": "dexchlorpheniramine"}

KO_SALT_TAIL = ["삼수화물", "이수화물", "일수화물", "반수화물", "마그네슘", "황산수소염", "염산염", "황산염", "말레산염", "베실산염", "푸마르산염", "타르타르산염", "숙신산염",
                "메실산염", "질산염", "인산염", "시트르산염", "브롬화수소산염", "칼슘수화물", "칼슘",
                "나트륨", "칼륨", "수화물", "무수물", "미분화", "메독소밀", "실렉세틸", "에텍실레이트"]
KO_SALT_HEAD = ["염산", "황산", "말레산", "질산", "인산", "브롬화수소산", "푸마르산", "타르타르산"]
KO_MINERAL_HEAD = ["탄산", "산화", "수산화", "염화", "구연산", "글루콘산"]  # 탄산칼슘 등은 그대로 둠

KO_SEED = {   # DUR 제품명에서 자동 학습되지 않는 규칙 성분 + 흔한 영양제 성분
    "베나제프릴": "benazepril", "브로마제팜": "bromazepam", "브롬페니라민": "brompheniramine",
    "카르비녹사민": "carbinoxamine", "시탈로프람": "citalopram", "클로티아제팜": "clotiazepam",
    "시프로헵타딘": "cyproheptadine", "덱스클로르페니라민": "dexchlorpheniramine",
    "에플레레논": "eplerenone", "에스오메프라졸": "esomeprazole", "페노프로펜": "fenoprofen",
    "플루복사민": "fluvoxamine", "포시노프릴": "fosinopril", "히드로클로로티아지드": "hydrochlorothiazide",
    "하이드로클로로티아자이드": "hydrochlorothiazide", "히드로코돈": "hydrocodone",
    "인다파미드": "indapamide", "레보티록신": "levothyroxine", "로르녹시캄": "lornoxicam",
    "로바스타틴": "lovastatin", "메페남산": "mefenamic acid", "메타돈": "methadone",
    "노르플록사신": "norfloxacin", "페티딘": "pethidine", "페니라민": "pheniramine",
    "프라수그렐": "prasugrel", "프로메타진": "promethazine", "수크랄페이트": "sucralfate",
    "술린닥": "sulindac", "토르세미드": "torsemide", "트리암테렌": "triamterene",
    "트리플루살": "triflusal", "트리프롤리딘": "triprolidine", "조피클론": "zopiclone",
    "파라세타몰": "acetaminophen", "탄산칼슘": "calcium carbonate", "구연산칼슘": "calcium citrate",
    "산화마그네슘": "magnesium oxide", "수산화마그네슘": "magnesium hydroxide",
    "수산화알루미늄": "aluminum hydroxide", "황산제일철": "ferrous sulfate", "푸마르산제일철": "ferrous fumarate",
    "염화칼륨": "potassium chloride", "산화아연": "zinc oxide", "칼슘": "calcium",
    "마그네슘": "magnesium", "철": "iron", "철분": "iron", "아연": "zinc",
    # 종합감기약·진통제에 흔한 성분 (허가정보 API가 한글로 줄 때 대비)
    "카페인": "caffeine", "이소프로필안티피린": "isopropylantipyrine", "클로르페니라민": "chlorpheniramine",
    "슈도에페드린": "pseudoephedrine", "페닐에프린": "phenylephrine", "덱스트로메토르판": "dextromethorphan",
    "구아이페네신": "guaifenesin", "브롬헥신": "bromhexine", "노스카핀": "noscapine",
    "디펜히드라민": "diphenhydramine", "에텐자미드": "ethenzamide", "트리프롤리딘": "triprolidine",
    "아세틸시스테인": "acetylcysteine", "암브록솔": "ambroxol", "메틸에페드린": "methylephedrine",
    "레바미피드": "rebamipide",
}
HANGUL = re.compile(r"[가-힣]")


def split_top(s: str):
    """괄호 밖의 + , ; / 와 '. '에서만 자름 (괄호 안 쉼표는 보존)"""
    out, buf, depth = [], [], 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and (ch in "+,;/|" or (ch == "." and s[i + 1:i + 2] == " ")):
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [x.strip() for x in out if x.strip()]


def norm_en(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s)).lower().strip()
    m = re.search(r"\(\s*as\s+([^)]+)\)", s)
    if m:                                   # '(as rosuvastatin)' → 활성 성분 사용
        s = m.group(1)
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", s)
    s = s.replace("함유제제", " ").replace("함유", " ")
    s = re.sub(r"[^a-z0-9\-. ]", " ", s)
    # 함량·숫자 토큰 제거 (gadobutrol 9.0708g → gadobutrol)
    toks = [t.strip(".") for t in s.split()
            if not re.fullmatch(r"[\d.\-]+(mg|g|ml|mcg|ug|iu|%|mm|unit|units)?", t.strip("."))]
    toks = [t for t in toks if t and t not in {"mg", "g", "ml", "mcg", "ug", "iu", "l"}]
    if not toks:
        return ""
    if toks[0] in MINERAL_HEAD:             # 탄산칼슘·염화칼륨 같은 무기질은 이름 유지
        toks = [t for t in toks if t not in HYDRATE] or toks
    else:
        while len(toks) > 1 and toks[-1] in SALT_TAIL:
            toks.pop()
        while len(toks) > 1 and toks[0] in SALT_TAIL:
            toks.pop(0)
    name = " ".join(toks)
    return EN_ALIAS.get(name, name)


def norm_ko(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s))
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", s)
    s = re.sub(r"[^가-힣a-zA-Z]", "", s)
    if any(s.startswith(h) for h in KO_MINERAL_HEAD):     # 탄산칼슘 등은 이름 유지
        return s
    if True:
        for h in KO_SALT_HEAD:
            if s.startswith(h) and len(s) > len(h) + 1:
                s = s[len(h):]
                break
    changed = True
    while changed:
        changed = False
        for suf in KO_SALT_TAIL:
            if s.endswith(suf) and len(s) > len(suf) + 1:
                s = s[: -len(suf)]
                changed = True
    return s


# ══════════════════════════════════════════════════════════════
# 2. 데이터 로딩 + 색인
# ══════════════════════════════════════════════════════════════
@dataclass
class Med:
    key: str                     # 제품코드 또는 'reg-<id>'
    name: str
    dur_code: str = ""           # DUR 성분코드 (없으면 '')
    dur_ingrs: frozenset = frozenset()    # DUR 데이터에서 온 성분
    extra_ingrs: frozenset = frozenset()  # 그 외(제품명·허가정보·사용자 입력)에서 온 성분
    times: list = field(default_factory=list)
    med_id: int = 0

    @property
    def ingrs(self):
        return self.dur_ingrs | self.extra_ingrs


class DURData:
    def __init__(self, folder=BASE):
        rd = lambda f: pd.read_csv(os.path.join(folder, f), dtype=str).fillna("")
        self.drugs = rd("drugs.csv")
        self.drugs = self.drugs[self.drugs["제품코드"] != ""].reset_index(drop=True)
        combo, elderly, age, preg = rd("combo.csv"), rd("elderly.csv"), rd("age.csv"), rd("pregnancy.csv")

        # 성분코드 → 정규화 성분
        self.code_ingrs = {}
        for code, nm in zip(self.drugs["성분코드"], self.drugs["성분명"]):
            if code not in self.code_ingrs:
                self.code_ingrs[code] = frozenset(filter(None, map(norm_en, split_top(nm))))

        self._build_ko_dict()

        # 전체 성분 보강 파일(tools/build_full_ingredients.py로 생성, 선택)
        self.full = {}
        fp = os.path.join(folder, "full_ingredients.csv")
        if os.path.exists(fp):
            for r in rd("full_ingredients.csv").itertuples():
                self.full[r.제품코드] = frozenset(filter(None, map(self.normalize, split_top(r.성분))))

        # 제품별 추가 성분 (제품명 괄호 속 한글 성분 + 보강 파일)
        extras = []
        for code, pname, icode in zip(self.drugs["제품코드"], self.drugs["제품명"], self.drugs["성분코드"]):
            ex = set(self.full.get(code, ()))
            for grp in re.findall(r"\(([^()]*)\)", pname.split("_(")[0]):
                if HANGUL.search(grp) and "수출" not in grp:
                    for part in split_top(grp):
                        en = self.ko2en.get(norm_ko(part))
                        if en:
                            ex.add(en)
            extras.append(frozenset(ex - self.code_ingrs.get(icode, frozenset())))
        self.drugs["_extra"] = extras
        self.drugs["_ingr_text"] = [
            "|" + "|".join(sorted(self.code_ingrs.get(c, frozenset()) | e)) + "|"
            for c, e in zip(self.drugs["성분코드"], extras)]

        # 병용금기: 코드 쌍 + 성분명 쌍
        self.combo_code, self.combo_name = {}, {}
        for r in combo.itertuples():
            val = (r.상세정보, r.비고)
            self.combo_code[(r.성분코드A, r.성분코드B)] = val
            self.combo_code[(r.성분코드B, r.성분코드A)] = val
            for a in filter(None, map(norm_en, split_top(r.성분명A))):
                for b in filter(None, map(norm_en, split_top(r.성분명B))):
                    if a != b:
                        self.combo_name.setdefault(frozenset((a, b)), val)

        # 단일 약 규칙: 코드별 + 성분명별
        def index(df, cols):
            by_code, by_name = defaultdict(list), defaultdict(list)
            for r in df.to_dict("records"):
                rec = {c: r[c] for c in cols}
                by_code[r["성분코드"]].append(rec)
                for n in filter(None, map(norm_en, split_top(r["성분명"]))):
                    if rec not in by_name[n]:
                        by_name[n].append(rec)
            return by_code, by_name
        self.elderly_code, self.elderly_name = index(elderly, ["상세정보"])
        self.age_code, self.age_name = index(age, ["특정연령", "특정연령단위", "연령처리조건", "상세정보"])
        self.preg_code, self.preg_name = index(preg, ["금기등급", "상세정보"])

        # 성분 선택 목록 (자동 등록·프로필 기피성분 입력용)
        all_en = set().union(*self.code_ingrs.values()) | set(self.ko2en.values())
        self.vocab = sorted(all_en)

    # ── 한글 → 영문 성분 사전: 제품명 '(아세트아미노펜)' + 단일성분 '성분명' 짝으로 학습
    def _build_ko_dict(self):
        votes = defaultdict(Counter)
        for pname, nm in zip(self.drugs["제품명"], self.drugs["성분명"]):
            ens = [x for x in map(norm_en, split_top(nm)) if x]
            groups = [g for g in re.findall(r"\(([^()]*)\)", pname.split("_(")[0])
                      if HANGUL.search(g) and "수출" not in g]
            if len(groups) != 1:
                continue
            kos = [norm_ko(p) for p in split_top(groups[0])]
            kos = [k for k in kos if len(k) >= 2 and not re.search(r"백신|유전자|재조합|수출|함유|회용|주사|밀리|그램|그람", k)]
            if len(ens) == 1 and len(kos) == 1:
                votes[kos[0]][ens[0]] += 1
        self.ko2en = {}
        for k, c in votes.items():
            en, n = c.most_common(1)[0]
            if n / sum(c.values()) >= 0.6:      # 표가 한쪽으로 확실히 모일 때만
                self.ko2en[k] = en
        for k, en in KO_SEED.items():           # 규칙에 쓰는 성분은 수동 사전으로 보강
            self.ko2en.setdefault(norm_ko(k), en)
        # 영문 → 대표 한글명(표시용)
        rev = defaultdict(Counter)
        for k, c in votes.items():
            for en, n in c.items():
                rev[en][k] += n
        self.en2ko = {en: c.most_common(1)[0][0] for en, c in rev.items()}

    def normalize(self, s: str) -> str:
        """한글이든 영문이든 → 정규화 영문(사전에 없으면 정규화 한글 그대로)"""
        if HANGUL.search(s):
            k = norm_ko(s)
            return self.ko2en.get(k, k)
        return norm_en(s)

    def label(self, ing: str) -> str:
        ko = self.en2ko.get(ing)
        return f"{ko} · {ing}" if ko else ing

    # ── 검색 (제품명 / 영문 성분 / 한글 성분)
    def search(self, kw: str, limit=100):
        kw = kw.strip()
        d = self.drugs
        mask = d["제품명"].str.contains(kw, regex=False) | \
            d["성분명"].str.contains(kw, case=False, regex=False)
        if HANGUL.search(kw):
            k = norm_ko(kw)
            hits = {en for ko, en in self.ko2en.items() if k and k in ko}
            for en in hits:
                mask |= d["_ingr_text"].str.contains("|" + en + "|", regex=False)
        return d[mask].head(limit)

    def med_from_row(self, row) -> Med:
        return Med(key=row["제품코드"], name=row["제품명"], dur_code=row["성분코드"],
                   dur_ingrs=self.code_ingrs.get(row["성분코드"], frozenset()),
                   extra_ingrs=frozenset(row["_extra"]))

    def parse_ingredients(self, raw):
        return sorted({self.normalize(x) for x in split_top(raw or "")} - {""})

    def product_row(self, code):
        r = self.drugs[self.drugs["제품코드"] == code]
        return None if r.empty else r.iloc[0]


# ══════════════════════════════════════════════════════════════
# 3. 검사
# ══════════════════════════════════════════════════════════════
@dataclass
class Profile:
    name: str = "나"
    birthdate: date = None
    pregnant: bool = False
    crush: bool = False          # 알약을 쪼개거나 갈아서 먹음
    avoid: list = field(default_factory=list)   # 기피 성분/약효군 (정규화 영문 또는 'class:NSAID')

    def age_days(self, today=None):
        if not self.birthdate:
            return None
        return ((today or date.today()) - self.birthdate).days

    def age_text(self, today=None):
        d = self.age_days(today)
        if d is None:
            return "나이 미입력"
        t, b = today or date.today(), self.birthdate
        months = (t.year - b.year) * 12 + t.month - b.month - (t.day < b.day)
        if months < 24:
            return f"{months}개월" if months >= 1 else f"{d}일"
        return f"만 {months // 12}세" + (f" {months % 12}개월" if months // 12 < 6 else "")


def in_class(ing, cls):
    for m in CLASSES[cls][1]:
        if m.startswith("~"):
            p = m[1:]
            if ing == p or ing.startswith(p + " "):
                return True
        elif ing == m:
            return True
    return False


def class_hits(ingrs, cls):
    return {i for i in ingrs if in_class(i, cls)}


UNIT_DAYS = {"세": 365.25, "개월": 30.4375, "주": 7}


def age_matches(rule, age_days):
    n = float(rule["특정연령"])
    unit = rule["특정연령단위"].split()[0]
    limit = n * UNIT_DAYS.get(unit, 365.25)
    cond = rule["연령처리조건"]
    if "미만" in cond: return age_days < limit
    if "이하" in cond:                       # '2세 이하' = 만 3세가 되기 전까지
        nxt = (n + 1) * UNIT_DAYS.get(unit, 365.25)
        return age_days < nxt
    if "이상" in cond: return age_days >= limit
    if "초과" in cond: return age_days >= (n + 1) * UNIT_DAYS.get(unit, 365.25)
    return False


SR_PATTERN = re.compile(r"서방|장용|이알|지속|(?<![A-Za-z])(ER|SR|CR|XR|XL|LA|MR|OROS)(?![A-Za-z])")


def _f(kind, level, meds, ingrs, why, note=""):
    return {"종류": kind, "level": level, "약": [m.name for m in meds],
            "성분": list(ingrs), "사유": why, "참고": note}


def _name_scope(m: Med):
    """성분명 기준 검사 대상: DUR 코드 없는 약은 전체, 있는 약은 추가 성분만"""
    return m.ingrs if not m.dur_code else m.extra_ingrs


def single_checks(m: Med, prof: Profile, data: DURData, today=None):
    out = []
    age = prof.age_days(today)
    scope = _name_scope(m)

    def rules(by_code, by_name):
        seen = []
        for r in by_code.get(m.dur_code, []) if m.dur_code else []:
            seen.append((r, None))
        for ing in scope:
            for r in by_name.get(ing, []):
                if all(r is not s for s, _ in seen):
                    seen.append((r, ing))
        return seen

    # 기피 성분 (프로필)
    for a in prof.avoid:
        if a.startswith("class:"):
            cls = a[6:]
            hit = class_hits(m.ingrs, cls) if cls in CLASSES else set()
            if hit:
                out.append(_f("기피성분", "금기", [m], hit,
                              f"프로필에 '{CLASSES[cls][0]}'을(를) 피해야 한다고 등록했어요."))
        elif a in m.ingrs:
            out.append(_f("기피성분", "금기", [m], [a], "프로필에 피해야 할 성분으로 등록한 성분이 들어 있어요."))

    if age is not None and age >= 65 * 365.25:
        for r, by in rules(data.elderly_code, data.elderly_name):
            out.append(_f("노인주의", "주의", [m], m.ingrs if by is None else [by], r["상세정보"],
                          "" if by is None else "성분명 기준 확인"))
    if age is not None:
        for r, by in rules(data.age_code, data.age_name):
            if age_matches(r, age):
                cond = f"{r['특정연령']}{r['특정연령단위'].split()[0]} {r['연령처리조건'].split()[0]} 사용 금기"
                if by is not None:
                    cond += " · 성분명 기준 확인"
                out.append(_f("연령금기", "금기", [m], m.ingrs if by is None else [by], r["상세정보"], cond))
    if prof.pregnant:
        for r, by in rules(data.preg_code, data.preg_name):
            g = r["금기등급"]
            kind, level = ("임부금기", "금기") if g == "1" else ("임부주의", "주의")
            note = {"1": "1등급", "2": "2등급", "M": "적응증에 따라 1·2등급"}.get(g, f"등급 {g}")
            if by is not None:
                note += " · 성분명 기준 확인"
            out.append(_f(kind, level, [m], m.ingrs if by is None else [by], r["상세정보"], note))
    if prof.crush and SR_PATTERN.search(m.name):
        out.append(_f("분할주의", "주의", [m], m.ingrs,
                      "서방형·장용성 등 특수 제형으로 보여요. 쪼개거나 씹거나 갈면 약이 한꺼번에 "
                      "흡수되거나 효과가 떨어질 수 있어요.", "제품명 기준 추정"))
    return out


def pair_checks(a: Med, b: Med, data: DURData):
    out = []
    banned = False
    # ① 병용금기 – 코드로 정확히
    if a.dur_code and b.dur_code:
        hit = data.combo_code.get((a.dur_code, b.dur_code))
        if hit:
            out.append(_f("병용금기", "금기", [a, b], sorted(a.dur_ingrs | b.dur_ingrs), hit[0], hit[1]))
            banned = True
    # ② 병용금기 – 성분명으로 (자동 등록 약·추가 성분)
    if not banned:
        sa, sb = _name_scope(a), _name_scope(b)
        for i in a.ingrs:
            for j in b.ingrs:
                if i == j or not (i in sa or j in sb):
                    continue
                hit = data.combo_name.get(frozenset((i, j)))
                if hit:
                    note = "성분명 기준 확인(제형에 따라 다를 수 있음)"
                    out.append(_f("병용금기", "금기", [a, b], [i, j], hit[0],
                                  f"{hit[1]} · {note}" if hit[1] else note))
                    banned = True
    # ③ 성분 중복
    same = a.ingrs & b.ingrs
    if same:
        out.append(_f("성분중복", "주의", [a, b], sorted(same), "같은 성분이 두 약에 모두 들어 있음"))
    # ④ 효능군 중복
    for cls, (label, _, dup, extra) in CLASSES.items():
        if not dup:
            continue
        ha, hb = class_hits(a.ingrs, cls), class_hits(b.ingrs, cls)
        if ha and hb and not (ha == hb == (ha & same)):
            out.append(_f("효능군중복", "주의", [a, b], sorted(ha | hb),
                          f"두 약 모두 {label}이에요. 비슷한 효과의 약이 겹치면 부작용 위험이 커져요. {extra}".strip()))
    # ⑤ 주의 상호작용 (금기로 이미 잡힌 쌍은 생략)
    if not banned:
        for x, y, why in PAIR_RULES:
            for p, q in ((a, b), (b, a)):
                hx, hy = class_hits(p.ingrs, x), class_hits(q.ingrs, y)
                if hx and hy:
                    out.append(_f("상호작용주의", "주의", [p, q], sorted(hx | hy), why,
                                  f"{CLASSES[x][0]} + {CLASSES[y][0]}"))
                    break
    return out


def analyze_all(meds, prof, data, today=None):
    findings = []
    for a, b in combinations(meds, 2):
        findings += pair_checks(a, b, data)
    for m in meds:
        findings += single_checks(m, prof, data, today)
    # 같은 내용 중복 제거
    uniq, seen = [], set()
    for f in findings:
        k = (f["종류"], tuple(sorted(f["약"])), tuple(sorted(f["성분"])), f["사유"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def short_name(name):
    return name.split("_(")[0]


DOSAGE_FORMS = ["필름코팅정", "서방정", "장용정", "연질캡슐", "경질캡슐", "캡슐", "츄어블정", "발포정",
                "정", "시럽", "현탁액", "액", "산", "과립", "크림", "연고", "패치"]


def norm_drug_name(name: str) -> str:
    """'OO정 500mg' → 'oo' (자동 등록 약 중복 방지·검색용)"""
    s = re.sub(r"\(.*?\)|\[.*?\]", "", unicodedata.normalize("NFKC", name))
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"\d+(\.\d+)?(mg|g|ml|밀리그램|밀리그람|그램|mcg|µg|%)", "", s, flags=re.I)
    s = re.sub(r"\d+", "", s)
    for f in DOSAGE_FORMS:
        if s.endswith(f) and len(s) > len(f) + 1:
            s = s[: -len(f)]
            break
    return s.lower()


def med_from_cache(rec) -> Med:
    """식약처 API로 받아 공동 캐시에 저장된 약 (DUR 목록 밖)"""
    return Med(key=rec["key"], name=rec["name"], extra_ingrs=frozenset(rec["ingredients"]))


def note_med(key, label) -> Med:
    """영양제 등 성분 정보 없이 시간 관리만 하는 항목"""
    return Med(key=key, name=label or key[5:])
