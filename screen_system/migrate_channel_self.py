"""
migrate_channel_self.py
  自社サイト(/shop = detail_sizeGuide_v26.html)からの注文を記録するため、
  sales_channel ENUM に 'self' を追加する。

  既存値: 'rakuten' | 'amazon' | 'yahoo' | 'base_ec'  → 'self' を追記。

実行:
    set DATABASE_URL=postgresql://postgres:パスワード@localhost:5432/screen
    python migrate_channel_self.py

何度実行しても安全(IF NOT EXISTS)。ALTER TYPE ... ADD VALUE はトランザクション外で
実行する必要があるため autocommit で流します。
"""
import os
import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1234@localhost:5432/screen")


def main():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("ALTER TYPE sales_channel ADD VALUE IF NOT EXISTS 'self'")
        cur.execute("SELECT enum_range(NULL::sales_channel)")
        vals = cur.fetchone()[0]
    print(f"完了: sales_channel = {vals}")


if __name__ == "__main__":
    main()
