# 💊 내 약 지킴이 (DUR 기반 다제복용 관리)

```
pip install -r requirements.txt
streamlit run app.py
```

## 파일 구성
| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 화면 (약 등록 / 오늘의 복약 / 안전성 확인 / 프로필) |
| `core.py` | 검사 엔진: 성분명 정규화, 한↔영 성분 사전, 복합제, 모든 검사 |
| `rules.py` | 앱 자체 '주의' 상호작용·효능군 목록 (DUR 공식 아님, 수정 가능) |
| `store.py` | 저장: 내 컴퓨터 모드(SQLite) / 웹 모드(Supabase, 계정별 분리 + 공동 약 캐시) |
| `schema.sql` | Supabase 테이블·보안 규칙(RLS) |
| `DEPLOY.md` | 웹사이트 배포 방법 |
| `mfds_api.py` | 식약처 의약품 제품 허가정보 API (선택) |
| `test_api.py` | 식약처 API 연결 확인 |
| `build_full_ingredients.py` | 전체 주성분을 미리 한꺼번에 받기 (선택, 앱은 약 추가 시 자동으로 받음) |
| `*.csv` | 식약처 DUR 데이터 (2026년 6월 기준) |

## 검사 항목
- DUR: 병용금기, 연령금기(생년월일 기준 일·개월 단위), 임부금기(1등급 금기 / 2등급·M 주의), 노인주의
- 앱 자체: 성분중복(정규화 성분 기준), 효능군중복, 주의 상호작용, 기피성분(프로필), 분할주의(프로필)

## 식약처 API 키 (선택)
공공데이터포털에서 '식품의약품안전처_의약품 제품 허가정보' 활용신청 후
환경변수 `MFDS_API_KEY` 또는 `.streamlit/secrets.toml`에 `MFDS_API_KEY = "..."`.
- DUR 목록에 없는 약: 검색하면 자동으로 식약처에서 찾아 공동 DB에 저장 (사용자가 성분을 입력하는 기능은 없음)
- DUR 목록 약: 추가할 때 전체 주성분을 받아 공동 DB에 저장 (복합제 성분 누락 보완)
- 서비스 버전·필드명은 활용가이드 확인 후 `mfds_api.py`의 `URL`, `INGR_FIELDS` 수정

## 실행 모드
- `secrets.toml`에 SUPABASE 값이 없으면 **내 컴퓨터 모드** (로그인 없음, `user_data.db`)
- 있으면 **웹 모드** (회원가입·로그인, 계정별 저장) → `DEPLOY.md`
