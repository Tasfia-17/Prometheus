"""Midas Bank — FastAPI demo with injected SQLite thread-safety bug.

The bug: a single shared sqlite3.Connection is created at module load time.
SQLite connections are NOT thread-safe by default. Under concurrent load
(FastAPI uses a thread pool for sync endpoints), multiple threads share
the same connection → "ProgrammingError: SQLite objects created in a thread
can only be used in that same thread."

This passes all serial unit tests. It fails ~60% of requests at 60 VUs.
"""
import sqlite3
import threading
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── BUG: shared connection, not thread-safe ──
_shared_conn = None


def get_db():
    """BUG: returns the same connection to every thread."""
    return _shared_conn


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            owner TEXT NOT NULL,
            balance REAL NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_account_id INTEGER,
            to_account_id INTEGER,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO accounts (id, owner, balance) VALUES
            (1, 'Alice', 10000.0),
            (2, 'Bob', 5000.0),
            (3, 'Charlie', 2500.0);
    """)
    conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _shared_conn
    _shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
    init_db(_shared_conn)
    yield
    _shared_conn.close()


app = FastAPI(title="Midas Bank", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

VALID_TOKEN = "test-token-midas"


def require_auth(authorization: str = Header(...)):
    if authorization != f"Bearer {VALID_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return authorization


# ── Models ──
class TransferRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: float
    description: str = ""


class DepositRequest(BaseModel):
    account_id: int
    amount: float
    description: str = ""


# ── Routes ──
@app.get("/api/health")
def health():
    return {"status": "ok", "service": "midas-bank"}


@app.get("/api/accounts")
def list_accounts(auth=Depends(require_auth)):
    db = get_db()
    rows = db.execute("SELECT id, owner, balance FROM accounts").fetchall()
    return [{"id": r[0], "owner": r[1], "balance": r[2]} for r in rows]


@app.get("/api/accounts/{account_id}")
def get_account(account_id: int, auth=Depends(require_auth)):
    db = get_db()
    row = db.execute("SELECT id, owner, balance FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"id": row[0], "owner": row[1], "balance": row[2]}


@app.get("/api/accounts/{account_id}/transactions")
def get_transactions(account_id: int, limit: int = 20, auth=Depends(require_auth)):
    db = get_db()
    rows = db.execute(
        "SELECT id, from_account_id, to_account_id, amount, type, description, created_at "
        "FROM transactions WHERE from_account_id=? OR to_account_id=? "
        "ORDER BY id DESC LIMIT ?",
        (account_id, account_id, limit)
    ).fetchall()
    return [{"id": r[0], "from_account_id": r[1], "to_account_id": r[2],
             "amount": r[3], "type": r[4], "description": r[5], "created_at": r[6]} for r in rows]


@app.post("/api/transactions/transfer", status_code=201)
def transfer(req: TransferRequest, auth=Depends(require_auth)):
    db = get_db()
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if req.from_account_id == req.to_account_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to same account")

    src = db.execute("SELECT balance FROM accounts WHERE id=?", (req.from_account_id,)).fetchone()
    dst = db.execute("SELECT id FROM accounts WHERE id=?", (req.to_account_id,)).fetchone()
    if not src:
        raise HTTPException(status_code=404, detail="Source account not found")
    if not dst:
        raise HTTPException(status_code=404, detail="Destination account not found")
    if src[0] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient funds")

    db.execute("UPDATE accounts SET balance=balance-? WHERE id=?", (req.amount, req.from_account_id))
    db.execute("UPDATE accounts SET balance=balance+? WHERE id=?", (req.amount, req.to_account_id))
    cur = db.execute(
        "INSERT INTO transactions (from_account_id, to_account_id, amount, type, description) VALUES (?,?,?,?,?)",
        (req.from_account_id, req.to_account_id, req.amount, "transfer", req.description)
    )
    db.commit()
    return {"id": cur.lastrowid, "from_account_id": req.from_account_id,
            "to_account_id": req.to_account_id, "amount": req.amount,
            "type": "transfer", "description": req.description,
            "created_at": datetime.utcnow().isoformat()}


@app.post("/api/transactions/deposit", status_code=201)
def deposit(req: DepositRequest, auth=Depends(require_auth)):
    db = get_db()
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    row = db.execute("SELECT id FROM accounts WHERE id=?", (req.account_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    db.execute("UPDATE accounts SET balance=balance+? WHERE id=?", (req.amount, req.account_id))
    cur = db.execute(
        "INSERT INTO transactions (to_account_id, amount, type, description) VALUES (?,?,?,?)",
        (req.account_id, req.amount, "deposit", req.description)
    )
    db.commit()
    return {"id": cur.lastrowid, "to_account_id": req.account_id, "amount": req.amount,
            "type": "deposit", "description": req.description,
            "created_at": datetime.utcnow().isoformat()}


@app.get("/api/accounts/{account_id}/balance")
def get_balance(account_id: int, auth=Depends(require_auth)):
    db = get_db()
    row = db.execute("SELECT balance FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"account_id": account_id, "balance": row[0]}
