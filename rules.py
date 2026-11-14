"""
앱 자체 '주의' 규칙 (DUR 공식 항목 아님)
──────────────────────────────────────────────────────────────
DUR 공공데이터에는 '병용금기'만 있고, 임상에서 흔히 확인하는 '주의' 수준
상호작용(예: 와파린 + 소염진통제)은 빠져 있어서 따로 정리한 목록입니다.
- 성분명은 core.norm_en()으로 정규화된 영문 소문자 기준
- '~calcium'처럼 물결표로 시작하면 'calcium ...'으로 시작하는 모든 성분
  (예: calcium carbonate, calcium citrate). 칼슘 판토텐산처럼 칼슘이 '염'일 뿐인 성분은
  정규화 단계에서 'pantothenate'로 바뀌어 여기에 걸리지 않음
- 규칙은 일반적인 참고 정보이며, 개인별 판단은 의사·약사가 합니다.
"""

# ── 약효군 ──────────────────────────────────────────────────
# 이름: (한글 표시명, 성분 목록, 중복주의 여부, 중복 시 덧붙일 말)
CLASSES = {
    "NSAID": ("소염진통제(NSAID)", [
        "ibuprofen", "dexibuprofen", "naproxen", "diclofenac", "aceclofenac", "celecoxib",
        "polmacoxib", "etoricoxib", "meloxicam", "piroxicam", "lornoxicam", "ketoprofen",
        "dexketoprofen", "loxoprofen", "zaltoprofen", "pelubiprofen", "etodolac", "nabumetone",
        "indomethacin", "mefenamic acid", "talniflumate", "flurbiprofen", "ketorolac",
        "sulindac", "fenoprofen"], True, ""),
    "ANTICOAG": ("항응고제", [
        "warfarin", "rivaroxaban", "apixaban", "edoxaban", "dabigatran"], True, ""),
    "ANTIPLT": ("항혈소판제", [
        "aspirin", "clopidogrel", "prasugrel", "ticagrelor", "cilostazol", "ticlopidine",
        "sarpogrelate", "triflusal"], True,
        "심혈관 시술 후 등에는 의도적으로 두 가지를 함께 쓰기도 하니 처방 의도를 확인하세요."),
    "SSRI": ("항우울제(SSRI·SNRI)", [
        "fluoxetine", "sertraline", "paroxetine", "escitalopram", "citalopram", "fluvoxamine",
        "venlafaxine", "desvenlafaxine", "duloxetine", "milnacipran"], True, ""),
    "SEDATIVE": ("신경안정제·수면제(벤조디아제핀·Z약물)", [
        "alprazolam", "lorazepam", "diazepam", "clonazepam", "etizolam", "triazolam",
        "flurazepam", "bromazepam", "clobazam", "chlordiazepoxide", "clotiazepam",
        "midazolam", "zolpidem", "zopiclone", "eszopiclone"], True, ""),
    "OPIOID": ("마약성 진통제(오피오이드)", [
        "tramadol", "tapentadol", "codeine", "dihydrocodeine", "hydrocodone", "oxycodone",
        "hydromorphone", "morphine", "fentanyl", "buprenorphine", "methadone", "pethidine"],
        True, ""),
    "ACEI": ("혈압약(ACE 억제제)", [
        "captopril", "enalapril", "lisinopril", "ramipril", "perindopril", "imidapril",
        "fosinopril", "cilazapril", "benazepril", "moexipril", "zofenopril"], True, ""),
    "ARB": ("혈압약(ARB)", [
        "losartan", "valsartan", "olmesartan", "telmisartan", "irbesartan", "candesartan",
        "eprosartan", "fimasartan", "azilsartan"], True, ""),
    "K_SPARING": ("칼륨보존 이뇨제", ["spironolactone", "eplerenone", "amiloride", "triamterene"],
                  False, ""),
    "K_SUPP": ("칼륨 보충제", ["potassium chloride", "potassium citrate", "potassium gluconate",
                            "potassium bicarbonate", "potassium"], False, ""),
    "DIURETIC": ("이뇨제(루프·티아지드계)", [
        "furosemide", "torsemide", "hydrochlorothiazide", "chlorthalidone", "indapamide"],
        False, ""),
    "ACID": ("위산분비억제제(PPI·P-CAB)", [
        "omeprazole", "esomeprazole", "lansoprazole", "dexlansoprazole", "pantoprazole",
        "rabeprazole", "ilaprazole", "tegoprazan", "fexuprazan", "vonoprazan"], True, ""),
    "STATIN": ("고지혈증약(스타틴)", [
        "atorvastatin", "rosuvastatin", "simvastatin", "pravastatin", "pitavastatin",
        "fluvastatin", "lovastatin"], True, ""),
    "AH1": ("1세대 항히스타민제(졸음 유발)", [
        "chlorpheniramine", "dexchlorpheniramine", "diphenhydramine", "hydroxyzine",
        "cyproheptadine", "promethazine", "triprolidine", "carbinoxamine", "brompheniramine",
        "pheniramine", "clemastine", "doxylamine", "mequitazine"], True,
        "종합감기약에 자주 들어 있어 모르고 겹치기 쉬워요."),
    "THYROID": ("갑상선호르몬제", ["levothyroxine", "liothyronine"], False, ""),
    "CATION": ("칼슘·마그네슘·알루미늄·철·아연 제제(제산제·영양제 포함)", [
        "~calcium", "~magnesium", "~aluminum", "~aluminium", "~ferrous", "~ferric", "~zinc",
        "iron", "polysaccharide-iron complex", "sucralfate"], False, ""),
    "QUINOLONE": ("퀴놀론계 항생제", [
        "ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin", "gemifloxacin",
        "norfloxacin"], False, ""),
    "TETRA": ("테트라사이클린계 항생제", ["doxycycline", "minocycline", "tetracycline"], False, ""),
    "CLOPI": ("클로피도그렐", ["clopidogrel"], False, ""),
    "OME": ("오메프라졸·에스오메프라졸", ["omeprazole", "esomeprazole"], False, ""),
    "TRAMADOL": ("트라마돌", ["tramadol"], False, ""),
    "WARFARIN": ("와파린", ["warfarin"], False, ""),
    "APAP": ("아세트아미노펜", ["acetaminophen"], False, ""),
}

# ── 주의 상호작용 (약효군 A, 약효군 B, 이유) ──────────────────
PAIR_RULES = [
    ("ANTICOAG", "NSAID",   "출혈(특히 위장관 출혈) 위험이 커져요."),
    ("ANTICOAG", "ANTIPLT", "출혈 위험이 커져요."),
    ("ANTIPLT",  "NSAID",   "위장관 출혈 위험이 커지고, 이부프로펜 등은 저용량 아스피린의 "
                            "심혈관 보호 효과를 떨어뜨릴 수 있어요."),
    ("SSRI", "ANTICOAG",    "출혈 위험이 커질 수 있어요."),
    ("SSRI", "ANTIPLT",     "출혈 위험이 커질 수 있어요."),
    ("SSRI", "NSAID",       "위장관 출혈 위험이 커질 수 있어요."),
    ("SSRI", "TRAMADOL",    "세로토닌 증후군이나 경련 위험이 커질 수 있어요."),
    ("SEDATIVE", "OPIOID",  "졸음·진정이 지나치게 강해지고 호흡이 억제될 수 있어요."),
    ("AH1", "SEDATIVE",     "졸음·진정 작용이 더해져요. 운전·낙상에 주의하세요."),
    ("AH1", "OPIOID",       "졸음·진정 작용이 더해져요. 운전·낙상에 주의하세요."),
    ("ACEI", "ARB",         "두 계열을 함께 쓰면 고칼륨혈증·저혈압·신기능 저하 위험이 있어 "
                            "일반적으로 함께 쓰지 않아요."),
    ("ACEI", "K_SPARING",   "혈중 칼륨이 지나치게 높아질(고칼륨혈증) 수 있어요."),
    ("ARB",  "K_SPARING",   "혈중 칼륨이 지나치게 높아질(고칼륨혈증) 수 있어요."),
    ("ACEI", "K_SUPP",      "혈중 칼륨이 지나치게 높아질(고칼륨혈증) 수 있어요."),
    ("ARB",  "K_SUPP",      "혈중 칼륨이 지나치게 높아질(고칼륨혈증) 수 있어요."),
    ("ACEI", "NSAID",       "혈압약 효과가 떨어지고, 특히 이뇨제와 함께면 신장 기능이 나빠질 수 있어요."),
    ("ARB",  "NSAID",       "혈압약 효과가 떨어지고, 특히 이뇨제와 함께면 신장 기능이 나빠질 수 있어요."),
    ("DIURETIC", "NSAID",   "이뇨제·혈압약 효과가 떨어지고 신장 기능이 나빠질 수 있어요."),
    ("CLOPI", "OME",        "클로피도그렐의 혈전 예방 효과가 줄어들 수 있어요."),
    ("THYROID", "CATION",   "갑상선호르몬제 흡수가 줄어요. 보통 4시간 정도 간격을 두고 먹어요."),
    ("QUINOLONE", "CATION", "항생제 흡수가 크게 줄어요. 몇 시간 간격을 두고 먹어야 해요."),
    ("TETRA", "CATION",     "항생제 흡수가 크게 줄어요. 몇 시간 간격을 두고 먹어야 해요."),
    ("WARFARIN", "APAP",    "아세트아미노펜을 고용량으로 오래 먹으면 와파린 효과(INR)가 "
                            "올라갈 수 있어요. 가끔 먹는 정도는 보통 괜찮아요."),
]
