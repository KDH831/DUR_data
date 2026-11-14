"""
drugs.csv의 '성분명'은 DUR 대상 성분만 담고 있어서(예: 게보린정 → isopropylantipyrine만)
복합제의 나머지 성분이 빠져 있습니다. 이 스크립트는 식약처 허가정보 API로 제품별 '전체 주성분'을
받아 full_ingredients.csv(제품코드, 제품명, 성분)로 저장합니다. 앱은 이 파일이 있으면 자동으로 씁니다.

사용법 (프로젝트 폴더에서):
    set MFDS_API_KEY=발급받은키        (macOS/Linux: export MFDS_API_KEY=...)
    python tools/build_full_ingredients.py
- 중간에 끊겨도 다시 실행하면 이어서 진행합니다. (개발계정 일일 호출 한도에 주의)
"""
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd  # noqa: E402
import mfds_api  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "full_ingredients.csv")


def main(limit=None, pause=0.1):
    if not mfds_api.get_key():
        sys.exit("MFDS_API_KEY 환경변수를 먼저 설정하세요.")
    drugs = pd.read_csv(os.path.join(BASE, "drugs.csv"), dtype=str).dropna(subset=["제품코드"])
    done = set()
    if os.path.exists(OUT):
        done = set(pd.read_csv(OUT, dtype=str)["제품코드"])
    new_file = not os.path.exists(OUT)
    n = 0
    with open(OUT, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["제품코드", "제품명", "성분"])
        for r in drugs.itertuples():
            if r.제품코드 in done:
                continue
            query = r.제품명.split("_(")[0]
            try:
                res = mfds_api.search(query, rows=5)
            except Exception as e:
                print("중단:", e, "→ 다시 실행하면 이어서 진행합니다.")
                break
            exact = [x for x in res if x["name"].replace(" ", "") == query.replace(" ", "")] or res[:1]
            w.writerow([r.제품코드, r.제품명, exact[0]["ingredients_raw"] if exact else ""])
            n += 1
            if limit and n >= limit:
                break
            time.sleep(pause)
    print(f"{n}건 추가 → {OUT}")


if __name__ == "__main__":
    main()
