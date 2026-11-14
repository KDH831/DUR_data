"""
저장소 계층 – 두 가지 모드, 같은 메서드
  LocalStore    : SQLite 파일 하나 (내 컴퓨터에서 혼자 쓸 때, 로그인 없음)
  SupabaseStore : 계정별 데이터 분리(RLS) + 공동 약 캐시 (웹사이트로 배포할 때)

사용자 데이터 : profiles, meds, intake  → 계정마다 따로
공동 데이터   : drug_cache              → 식약처 API에서 받은 공식 정보만, 앱 서버만 기록
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

DEFAULT_DB = os.environ.get("MEDS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_data.db"))


def _today():
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()     # 한국 날짜


def _iso(d):
    return d.isoformat() if hasattr(d, "isoformat") else d


# ══════════════════════════════════════════════════════════════
# 로컬 (SQLite)
# ══════════════════════════════════════════════════════════════
LOCAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, birthdate TEXT,
    pregnant INTEGER DEFAULT 0, crush INTEGER DEFAULT 0, avoid TEXT DEFAULT '[]', memo TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS meds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    product_key TEXT NOT NULL, label TEXT, times TEXT DEFAULT '[]', added_at TEXT,
    UNIQUE (profile_id, product_key));
CREATE TABLE IF NOT EXISTS intake (
    profile_id INTEGER NOT NULL, day TEXT NOT NULL, slot TEXT NOT NULL, med_id INTEGER NOT NULL,
    PRIMARY KEY (profile_id, day, slot, med_id));
CREATE TABLE IF NOT EXISTS drug_cache (
    key TEXT PRIMARY KEY, name TEXT NOT NULL, ingredients TEXT NOT NULL, raw TEXT,
    source TEXT DEFAULT 'mfds_api', fetched_at TEXT);
"""


class LocalStore:
    shared = False      # 공동 DB 아님

    def __init__(self, path=DEFAULT_DB):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(LOCAL_SCHEMA)

    @staticmethod
    def _p(r):
        return dict(r) | {"avoid": json.loads(r["avoid"]), "pregnant": bool(r["pregnant"]),
                          "crush": bool(r["crush"])}

    # 프로필
    def profiles(self):
        return [self._p(r) for r in self.conn.execute("SELECT * FROM profiles ORDER BY id")]

    def save_profile(self, pid, name, birthdate, pregnant, crush, avoid, memo):
        v = (name, _iso(birthdate), int(pregnant), int(crush), json.dumps(avoid, ensure_ascii=False), memo)
        with self.conn:
            if pid:
                self.conn.execute("UPDATE profiles SET name=?,birthdate=?,pregnant=?,crush=?,avoid=?,memo=? "
                                  "WHERE id=?", v + (pid,))
                return pid
            return self.conn.execute("INSERT INTO profiles (name,birthdate,pregnant,crush,avoid,memo) "
                                     "VALUES (?,?,?,?,?,?)", v).lastrowid

    def delete_profile(self, pid):
        with self.conn:
            self.conn.execute("DELETE FROM intake WHERE profile_id=?", (pid,))
            self.conn.execute("DELETE FROM meds WHERE profile_id=?", (pid,))
            self.conn.execute("DELETE FROM profiles WHERE id=?", (pid,))

    # 복용약
    def meds(self, pid):
        return [dict(r) | {"times": json.loads(r["times"])} for r in
                self.conn.execute("SELECT * FROM meds WHERE profile_id=? ORDER BY id", (pid,))]

    def add_med(self, pid, key, times, label=None):
        with self.conn:
            return self.conn.execute(
                "INSERT OR IGNORE INTO meds (profile_id,product_key,label,times,added_at) VALUES (?,?,?,?,?)",
                (pid, key, label, json.dumps(times, ensure_ascii=False), _today())).rowcount > 0

    def update_times(self, med_id, times):
        with self.conn:
            self.conn.execute("UPDATE meds SET times=? WHERE id=?", (json.dumps(times, ensure_ascii=False), med_id))

    def remove_med(self, med_id):
        with self.conn:
            self.conn.execute("DELETE FROM intake WHERE med_id=?", (med_id,))
            self.conn.execute("DELETE FROM meds WHERE id=?", (med_id,))

    # 복약 기록
    def taken(self, pid, day):
        return {(r["slot"], r["med_id"]) for r in
                self.conn.execute("SELECT slot, med_id FROM intake WHERE profile_id=? AND day=?", (pid, day))}

    def set_taken(self, pid, day, slot, med_id, value):
        with self.conn:
            if value:
                self.conn.execute("INSERT OR IGNORE INTO intake VALUES (?,?,?,?)", (pid, day, slot, med_id))
            else:
                self.conn.execute("DELETE FROM intake WHERE profile_id=? AND day=? AND slot=? AND med_id=?",
                                  (pid, day, slot, med_id))

    def intake_counts(self, pid, days):
        q = f"SELECT day, COUNT(*) FROM intake WHERE profile_id=? AND day IN ({','.join('?' * len(days))}) GROUP BY day"
        return dict(self.conn.execute(q, (pid, *days)).fetchall())

    # 공동 약 캐시
    def cache_get(self, keys):
        keys = list(keys)
        if not keys:
            return {}
        q = f"SELECT * FROM drug_cache WHERE key IN ({','.join('?' * len(keys))})"
        return {r["key"]: dict(r) | {"ingredients": json.loads(r["ingredients"])} for r in self.conn.execute(q, keys)}

    def cache_search(self, kw, limit=30):
        return [dict(r) | {"ingredients": json.loads(r["ingredients"])} for r in self.conn.execute(
            "SELECT * FROM drug_cache WHERE key LIKE 'api-%' AND name LIKE ? LIMIT ?", (f"%{kw}%", limit))]

    def cache_put(self, key, name, ingredients, raw):
        if not ingredients:
            return
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO drug_cache VALUES (?,?,?,?, 'mfds_api', ?)",
                              (key, name, json.dumps(sorted(ingredients), ensure_ascii=False), raw,
                               _today()))


# ══════════════════════════════════════════════════════════════
# Supabase
# ══════════════════════════════════════════════════════════════
class SupabaseStore:
    """user_client: 로그인한 사용자 토큰을 쓰는 클라이언트 (RLS로 본인 데이터만 접근)
       admin_client: service_role 키 클라이언트 (공동 약 캐시 쓰기 전용, 서버에서만 사용)"""
    shared = True

    def __init__(self, user_client, admin_client):
        self.u, self.a = user_client, admin_client

    def _t(self, name):
        return self.u.table(name)

    # 프로필
    def profiles(self):
        return self._t("profiles").select("*").order("id").execute().data

    def save_profile(self, pid, name, birthdate, pregnant, crush, avoid, memo):
        v = {"name": name, "birthdate": _iso(birthdate), "pregnant": bool(pregnant), "crush": bool(crush),
             "avoid": avoid, "memo": memo}
        if pid:
            self._t("profiles").update(v).eq("id", pid).execute()
            return pid
        return self._t("profiles").insert(v).execute().data[0]["id"]

    def delete_profile(self, pid):
        self._t("profiles").delete().eq("id", pid).execute()      # meds·intake는 cascade

    # 복용약
    def meds(self, pid):
        return self._t("meds").select("*").eq("profile_id", pid).order("id").execute().data

    def add_med(self, pid, key, times, label=None):
        exists = self._t("meds").select("id").eq("profile_id", pid).eq("product_key", key).execute().data
        if exists:
            return False
        self._t("meds").insert({"profile_id": pid, "product_key": key, "label": label, "times": times}).execute()
        return True

    def update_times(self, med_id, times):
        self._t("meds").update({"times": times}).eq("id", med_id).execute()

    def remove_med(self, med_id):
        self._t("meds").delete().eq("id", med_id).execute()

    # 복약 기록
    def taken(self, pid, day):
        rows = self._t("intake").select("slot,med_id").eq("profile_id", pid).eq("day", day).execute().data
        return {(r["slot"], r["med_id"]) for r in rows}

    def set_taken(self, pid, day, slot, med_id, value):
        if value:
            self._t("intake").upsert({"profile_id": pid, "day": day, "slot": slot, "med_id": med_id}).execute()
        else:
            self._t("intake").delete().eq("profile_id", pid).eq("day", day).eq("slot", slot) \
                .eq("med_id", med_id).execute()

    def intake_counts(self, pid, days):
        rows = self._t("intake").select("day").eq("profile_id", pid).in_("day", list(days)).execute().data
        out = {}
        for r in rows:
            out[r["day"]] = out.get(r["day"], 0) + 1
        return out

    # 공동 약 캐시 (읽기: 사용자 권한 / 쓰기: 서버 권한)
    def cache_get(self, keys):
        keys = list(keys)
        if not keys:
            return {}
        return {r["key"]: r for r in self.u.table("drug_cache").select("*").in_("key", keys).execute().data}

    def cache_search(self, kw, limit=30):
        return self.u.table("drug_cache").select("*").like("key", "api-%").ilike("name", f"%{kw}%") \
            .limit(limit).execute().data

    def cache_put(self, key, name, ingredients, raw):
        if not ingredients or self.a is None:
            return
        self.a.table("drug_cache").upsert({"key": key, "name": name, "ingredients": sorted(ingredients),
                                           "raw": raw, "source": "mfds_api"}).execute()
