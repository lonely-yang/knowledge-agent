"""校验并补全 kh_document 的解析状态列(idx_status/rag_status/kg_status)。
用法: python scripts/check_parse_status_cols.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
from core.config import settings as s

COLS = ["idx_status", "rag_status", "kg_status"]

def main():
    conn = psycopg.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, dbname=s.POSTGRES_DB,
    )
    with conn:
        with conn.cursor() as cur:
            # 查当前已存在的列
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = ANY(%s)",
                ("kh_document", COLS),
            )
            existing = {r[0] for r in cur.fetchall()}
            print("已存在:", existing)
            missing = [c for c in COLS if c not in existing]
            for c in missing:
                cur.execute(
                    f"ALTER TABLE kh_document ADD COLUMN IF NOT EXISTS {c} SMALLINT"
                )
                print("已新增:", c)
        conn.commit()
        # 复查
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = ANY(%s)",
                ("kh_document", COLS),
            )
            print("最终存在:", sorted(r[0] for r in cur.fetchall()))

if __name__ == "__main__":
    main()
