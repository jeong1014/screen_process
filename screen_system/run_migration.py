"""
run_migration.py — psql を使わずにマイグレーションSQLを実行する。
アプリと同じ psycopg / DATABASE_URL を使うので、追加インストール不要。

使い方(screen_system フォルダで):
    python run_migration.py
    python run_migration.py 別のファイル.sql        # ファイル指定も可

DATABASE_URL は環境変数から。未設定なら app.py と同じ既定値を使う。
"""
import os
import sys
import re
import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:1234@localhost:5432/screen"
)

SQL_FILE = sys.argv[1] if len(sys.argv) > 1 else "migration_remove_packing.sql"


def load_statements(path):
    raw = open(path, encoding="utf-8").read()
    # -- 行コメントを除去
    lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
    body = "\n".join(lines)
    # 明示的な BEGIN/COMMIT はこちらのトランザクションで管理するので取り除く
    body = re.sub(r"\b(BEGIN|COMMIT)\s*;", "", body, flags=re.IGNORECASE)
    # ';' 区切りで分割(このマイグレーションは関数/ドル引用符を含まないので単純分割でOK)
    return [s.strip() for s in body.split(";") if s.strip()]


def show_state(cur, label):
    print(f"\n--- {label} ---")
    cur.execute("SELECT stage_no, code, name_ja FROM production_stages ORDER BY stage_no")
    print("production_stages:", [(r[0], r[2]) for r in cur.fetchall()])
    cur.execute("SELECT current_stage, count(*) FROM order_items GROUP BY current_stage ORDER BY current_stage")
    print("current_stage 分布:", [(r[0], r[1]) for r in cur.fetchall()])


def main():
    print(f"DB      : {DATABASE_URL}")
    print(f"SQL     : {SQL_FILE}")
    stmts = load_statements(SQL_FILE)
    print(f"文の数  : {len(stmts)}")

    # row_factory を使わず素の tuple で取得(表示用)
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            try:
                show_state(cur, "実行前")
            except Exception as e:
                print("(実行前の状態取得はスキップ:", e, ")")

            print("\n>>> マイグレーション実行中 ...")
            for i, s in enumerate(stmts, 1):
                head = " ".join(s.split())[:70]
                print(f"  [{i}/{len(stmts)}] {head} ...")
                cur.execute(s)

            show_state(cur, "実行後")
        conn.commit()
    print("\n✅ 完了しました。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        print("  ロールバックされました(DBは変更されていません)。")
        sys.exit(1)
