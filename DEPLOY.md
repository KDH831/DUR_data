# 웹사이트로 배포하기 (Supabase + Streamlit Community Cloud)

## 1. Supabase (계정·DB) – 무료
1. supabase.com 가입 → **New project** (Region: Northeast Asia (Seoul)), DB 비밀번호 저장
2. 왼쪽 **SQL Editor → New query** → `schema.sql` 내용 전체 붙여넣기 → **Run**
3. 왼쪽 **Project Settings → API** (또는 API Keys)에서 3가지 복사
   - Project URL → `SUPABASE_URL`
   - anon / publishable 키 → `SUPABASE_ANON_KEY`
   - service_role / secret 키 → `SUPABASE_SERVICE_KEY` ⚠️ 절대 공개 금지 (공동 약 DB 쓰기 권한)
4. **Authentication → Sign In / Providers → Email**: 가입 확인 메일이 필요 없으면 'Confirm email' 끄기
   **Authentication → URL Configuration → Site URL**: 배포 후 받은 앱 주소 입력

## 2. 내 컴퓨터에서 먼저 확인
`.streamlit/secrets.toml`에서 SUPABASE 3줄의 `#`를 지우고 값 입력 → `streamlit run app.py`
→ 로그인 화면이 나오면 성공

## 3. GitHub에 올리기
`.gitignore` 덕분에 `secrets.toml`(키), `user_data.db`는 올라가지 않습니다. 올리기 전 GitHub 화면에서 한 번 더 확인!

## 4. Streamlit Community Cloud
1. share.streamlit.io → GitHub로 로그인 → **Create app → Deploy a public app from GitHub**
2. Repository: 저장소 선택, Main file path: `app.py`
3. **Advanced settings → Secrets**에 `secrets.toml` 내용 4줄(MFDS + SUPABASE 3개) 붙여넣기 → **Deploy**

## 데이터 구조
| 테이블 | 누가 | 내용 |
|---|---|---|
| profiles, meds, intake | 계정별 (본인만 읽기·쓰기, RLS) | 프로필, 복용약, 날짜별 복약 기록 |
| drug_cache | 모두 읽기 / 앱 서버만 쓰기 | 식약처 허가정보 API에서 받은 공식 성분 정보 |

공개 서비스로 운영하려면 개인정보 처리방침(수집 항목: 이메일, 생년월일, 복용약, 임신 여부 등)을 마련하세요.
