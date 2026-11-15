"""
검색 결과 중복 점검: app.py의 '약 검색' 결과 목록을 그대로 재현해서 같은 약이 두 번 나오는지 확인
  사용법:  python check_dupes.py 리벨서스 레블리미드 광동아스피린
  - MFDS_API_KEY가 있으면 식약처 결과까지 포함, 없으면 DUR 목록만으로 점검
  - 공동 캐시(Supabase drug_cache) 결과는 포함하지 않음
"""
import re
import sys
from collections import defaultdict

import mfds_api
from core import DURData, DurIndex, same_name, short_name

data = DURData()


IDX = DurIndex(data.drugs)
INGR = IDX.ingr


def build_options(kw):
    """app.py tab1의 options 생성 부분 재현 (cache 제외)"""
    api_res = []
    if mfds_api.get_key():
        api_res = [r for r in mfds_api.search(kw, rows=50) if data.parse_ingredients(r["ingredients_raw"])]
    options, api_for_code = [], {}
    for i, r in enumerate(api_res):
        codes = IDX.match(r)  # app.py와 동일
        for code in codes:
            if code not in api_for_code:
                api_for_code[code] = i
                options.append(("dur", code))
        if not codes:
            options.append(("api", i))
    seen = {o[1] for o in options if o[0] == "dur"}
    options += [("dur", c) for c in data.search(kw)["제품코드"] if c not in seen]
    return options, api_res


def describe(o, api_res):
    if o[0] == "api":
        r = api_res[o[1]]
        return r["name"], r.get("company", ""), "식약처"
    row = data.product_row(o[1])
    return row["제품명"], row["업체명"], f"DUR {o[1]}"


UNIT = {"mg": 1, "밀리그램": 1, "밀리그람": 1, "g": 1000, "그램": 1000, "mcg": 0.001, "마이크로그램": 0.001}
STR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|밀리그램|밀리그람|mcg|마이크로그램|g|그램)", re.I)


def strength(name):
    """용량(mg). 제품명 → 없으면 DUR의 '_(0.1g/1정)' 부분에서. 복합제·액제 등은 첫 값만 봄"""
    for part in (short_name(name), name[len(short_name(name)):]):
        m = STR_RE.search(part)
        if m:
            return round(float(m.group(1)) * UNIT[m.group(2).lower()], 3)
    return None


def why(names, srcs):
    """중복이 생긴 이유 추정"""
    keys = {same_name(n) for n in names}
    if len({src.split()[0] for src in srcs}) == 1 and len(keys) == 1 and len(srcs) > 1 and srcs[0] != "식약처":
        return "DUR 목록 안에서 같은 이름 제품코드가 여러 개(업체·포장 차이) — 식약처 연결 문제 아님"
    if len(keys) == 1:
        k = keys.pop()
        if len(INGR.get(k, ())) > 1:
            return "DUR에 같은 비교이름·다른 성분코드(용량별)가 있어 연결 안 됨"
        return "DUR에 같은 이름 제품코드가 여러 개(업체·포장 차이)"
    return "이름 표기가 달라 연결 실패 (예: mg ↔ 밀리그램, 용량 표기 위치) → " + " / ".join(sorted(keys))


def check(kw):
    options, api_res = build_options(kw)
    rows = [describe(o, api_res) for o in options]
    print(f"\n━━ '{kw}' : 결과 {len(rows)}건 (식약처 {sum(o[0]=='api' for o in options)}, "
          f"DUR {sum(o[0]=='dur' for o in options)}) {'' if api_res or not mfds_api.get_key() else '· 식약처 0건'}")
    groups = defaultdict(list)
    for nm, co, src in rows:
        groups[(STR_RE.sub("", same_name(nm)), strength(nm))].append((nm, co, src))
    dup = {k: v for k, v in groups.items() if len(v) > 1}
    if not dup:
        print("  ✅ 같은 약으로 보이는 중복 없음")
    for k, v in dup.items():
        print(f"  ⚠️ '{k[0]}' {k[1] or '?'}mg {len(v)}건 — {why([x[0] for x in v], [x[2] for x in v])}")
        for nm, co, src in v:
            print(f"     · {nm}  ·  {co}   [{src}]")


if __name__ == "__main__":
    if not mfds_api.get_key():
        print("※ MFDS_API_KEY가 없어 DUR 목록만으로 점검합니다 (식약처↔DUR 중복은 확인 불가)")
    for kw in sys.argv[1:] or ["리벨서스", "레블리미드", "어린이부루펜", "광동아스피린", "아스피린"]:
        check(kw)
