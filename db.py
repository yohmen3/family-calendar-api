"""データ永続化レイヤー — PostgreSQL or JSONファイル（焼菓子アプリと同じパターン）"""

import json
import os
from pathlib import Path

_DATABASE_URL = os.environ.get("DATABASE_URL")

if _DATABASE_URL:
    # Render の postgres:// を postgresql:// に変換
    if _DATABASE_URL.startswith("postgres://"):
        _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)

    import psycopg2
    import psycopg2.pool

    _pool = psycopg2.pool.SimpleConnectionPool(1, 5, _DATABASE_URL, sslmode="require")

    def _get_conn():
        return _pool.getconn()

    def _put_conn(conn):
        _pool.putconn(conn)

    def init_db():
        """テーブルを作成"""
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS json_store (
                        key  TEXT PRIMARY KEY,
                        data JSONB NOT NULL
                    )
                """)
            conn.commit()
        finally:
            _put_conn(conn)

    def load(key, default=None):
        """キーに対応するJSONデータを読み込む"""
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM json_store WHERE key = %s", (key,))
                row = cur.fetchone()
                if row:
                    return row[0]
        finally:
            _put_conn(conn)
        return default if default is not None else []

    def save(key, data):
        """キーに対応するJSONデータを保存（UPSERT）"""
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO json_store (key, data)
                    VALUES (%s, %s::jsonb)
                    ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data
                """, (key, json.dumps(data, ensure_ascii=False)))
            conn.commit()
        finally:
            _put_conn(conn)

else:
    # ローカル開発用：JSONファイルに保存
    DATA_DIR = Path(__file__).parent / "data"
    DATA_DIR.mkdir(exist_ok=True)

    def init_db():
        pass

    def load(key, default=None):
        p = DATA_DIR / f"{key}.json"
        if not p.exists():
            return default if default is not None else []
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def save(key, data):
        p = DATA_DIR / f"{key}.json"
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
