"""테스트용 가짜 Supabase (메모리). RLS 흉내: user 클라이언트는 자기 user_id 행만, drug_cache는 읽기만."""
# 실제 서버에 접속하지 않고 로그인·저장·탈퇴 흐름을 확인하기 위한 대역(stub)
import itertools, fnmatch
from types import SimpleNamespace as NS

DB = {"profiles": [], "meds": [], "intake": [], "drug_cache": []}
SEQ = itertools.count(1)
USERS = {}
PK = {"intake": ("profile_id", "day", "slot", "med_id"), "drug_cache": ("key",)}

class Q:
    def __init__(self, c, t): self.c, self.t, self.f, self.op, self.payload, self.lim, self.ord = c, t, [], "select", None, None, None
    def select(self, *_): self.op = "select"; return self
    def insert(self, v): self.op, self.payload = "insert", v; return self
    def upsert(self, v): self.op, self.payload = "upsert", v; return self
    def update(self, v): self.op, self.payload = "update", v; return self
    def delete(self): self.op = "delete"; return self
    def eq(self, k, v): self.f.append(lambda r: r.get(k) == v); return self
    def in_(self, k, vs): vs = list(vs); self.f.append(lambda r: r.get(k) in vs); return self
    def like(self, k, p): self.f.append(lambda r: fnmatch.fnmatchcase(str(r.get(k)), p.replace("%", "*"))); return self
    def ilike(self, k, p): self.f.append(lambda r: fnmatch.fnmatch(str(r.get(k)).lower(), p.lower().replace("%", "*"))); return self
    def order(self, k): self.ord = k; return self
    def limit(self, n): self.lim = n; return self
    def _rows(self):
        rows = DB[self.t]
        if self.t != "drug_cache" and not self.c.admin:
            rows = [r for r in rows if r["user_id"] == self.c.uid]
        return [r for r in rows if all(f(r) for f in self.f)]
    def execute(self):
        if self.t == "drug_cache" and self.op != "select" and not self.c.admin:
            raise PermissionError("RLS: drug_cache는 사용자 쓰기 불가")
        if self.op == "select":
            rows = self._rows()
            if self.ord: rows = sorted(rows, key=lambda r: r[self.ord])
            return NS(data=[dict(r) for r in rows[: self.lim]])
        if self.op in ("insert", "upsert"):
            v = dict(self.payload)
            if self.t != "drug_cache": v["user_id"] = self.c.uid
            if self.t in ("profiles", "meds") and "id" not in v: v["id"] = next(SEQ)
            if self.t == "meds":
                prof = [p for p in DB["profiles"] if p["id"] == v["profile_id"]]
                assert prof and prof[0]["user_id"] == self.c.uid, "RLS: 남의 프로필"
                v.setdefault("label", None); v.setdefault("times", [])
            if self.t == "profiles": v.setdefault("avoid", []); v.setdefault("memo", "")
            if self.op == "upsert":
                pk = PK.get(self.t, ("id",))
                DB[self.t] = [r for r in DB[self.t] if tuple(r.get(k) for k in pk) != tuple(v.get(k) for k in pk)]
            DB[self.t].append(v); return NS(data=[dict(v)])
        if self.op == "update":
            rows = self._rows()
            for r in rows: r.update(self.payload)
            return NS(data=rows)
        if self.op == "delete":
            rows = self._rows(); ids = {id(r) for r in rows}
            DB[self.t] = [r for r in DB[self.t] if id(r) not in ids]
            if self.t == "profiles":   # cascade
                pids = {r["id"] for r in rows}
                DB["meds"] = [m for m in DB["meds"] if m["profile_id"] not in pids]
                DB["intake"] = [m for m in DB["intake"] if m["profile_id"] not in pids]
            if self.t == "meds":
                mids = {r["id"] for r in rows}
                DB["intake"] = [m for m in DB["intake"] if m["med_id"] not in mids]
            return NS(data=rows)

class Auth:
    def __init__(self, c): self.c = c
    def sign_up(self, cred):
        USERS[cred["email"]] = cred["password"]; self.c.uid = cred["email"]
        return NS(user=NS(email=cred["email"], id=cred["email"]), session=NS(access_token="t"))
    def sign_in_with_password(self, cred):
        if USERS.get(cred["email"]) != cred["password"]: raise Exception("Invalid login credentials")
        self.c.uid = cred["email"]; return NS(user=NS(email=cred["email"], id=cred["email"]), session=NS(access_token="t"))
    def sign_out(self, *a): self.c.uid = None
    def reset_password_for_email(self, email, options=None): OUTBOX.append(email)
    def verify_otp(self, p):
        if p.get("token_hash") == "GOOD" or (p.get("token") == "12345678" and p.get("email") in USERS):
            self.c.uid = p.get("email") or next(iter(USERS)); return NS(user=NS(email=self.c.uid, id=self.c.uid), session=NS())
        raise Exception("Token has expired or is invalid")
    def update_user(self, attrs):
        USERS[self.c.uid] = attrs["password"]; return NS(user=NS(email=self.c.uid, id=self.c.uid))
    def get_session(self): return NS(refresh_token="rt-" + str(self.c.uid)) if self.c.uid else None
    def refresh_session(self, rt): raise Exception("invalid")

OUTBOX = []
class Admin:
    def delete_user(self, uid):
        assert uid in USERS; del USERS[uid]
        for t in ("profiles", "meds", "intake"):
            DB[t] = [r for r in DB[t] if r["user_id"] != uid]

class Client:
    def __init__(self, url, key):
        self.admin = key == "SERVICE"; self.uid = None; self.auth = Auth(self)
        if self.admin: self.auth.admin = Admin()
    def table(self, t): return Q(self, t)

def create_client(url, key): return Client(url, key)


def reset():
    for t in DB:
        DB[t].clear()
    USERS.clear()
    OUTBOX.clear()
