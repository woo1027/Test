import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, g, jsonify, render_template, request

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bento.db")

DEFAULT_CATEGORIES = [
    ("食材", 35, 1),
    ("人事", 25, 2),
    ("租金", 12, 3),
    ("包材/餐盒容器", 5, 4),
    ("水電", 3, 5),
    ("瓦斯", 2, 6),
    ("電話費", 1, 7),
    ("雜支", 3, 8),
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    first_time = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            target_percent REAL NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_sales (
            date TEXT PRIMARY KEY,
            revenue REAL NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cost_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            note TEXT DEFAULT '',
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
        """
    )
    if first_time:
        conn.executemany(
            "INSERT INTO categories (name, target_percent, sort_order) VALUES (?, ?, ?)",
            DEFAULT_CATEGORIES,
        )
    conn.commit()
    conn.close()


def month_bounds(month_str):
    start = datetime.strptime(month_str, "%Y-%m").date()
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start.isoformat(), end.isoformat()


# ---------- Pages ----------

@app.route("/")
def index():
    return render_template("index.html", today=date.today().isoformat())


@app.route("/report")
def report_page():
    return render_template("report.html", month=date.today().strftime("%Y-%m"))


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


# ---------- API: categories ----------

@app.route("/api/categories", methods=["GET"])
def list_categories():
    db = get_db()
    only_active = request.args.get("active", "1") == "1"
    query = "SELECT * FROM categories"
    if only_active:
        query += " WHERE is_active = 1"
    query += " ORDER BY sort_order, id"
    rows = db.execute(query).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/categories", methods=["POST"])
def create_category():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    target_percent = data.get("target_percent", 0)
    if not name:
        return jsonify({"error": "項目名稱為必填"}), 400
    try:
        target_percent = float(target_percent)
    except (TypeError, ValueError):
        return jsonify({"error": "目標佔比必須為數字"}), 400

    db = get_db()
    max_order = db.execute("SELECT COALESCE(MAX(sort_order), 0) AS m FROM categories").fetchone()["m"]
    try:
        cur = db.execute(
            "INSERT INTO categories (name, target_percent, sort_order) VALUES (?, ?, ?)",
            (name, target_percent, max_order + 1),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此項目名稱已存在"}), 400
    return jsonify({"id": cur.lastrowid, "name": name, "target_percent": target_percent})


@app.route("/api/categories/<int:cat_id>", methods=["PUT"])
def update_category(cat_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if not row:
        return jsonify({"error": "找不到此項目"}), 404

    name = data.get("name", row["name"]).strip()
    target_percent = data.get("target_percent", row["target_percent"])
    is_active = data.get("is_active", row["is_active"])
    try:
        target_percent = float(target_percent)
    except (TypeError, ValueError):
        return jsonify({"error": "目標佔比必須為數字"}), 400

    try:
        db.execute(
            "UPDATE categories SET name = ?, target_percent = ?, is_active = ? WHERE id = ?",
            (name, target_percent, 1 if is_active else 0, cat_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此項目名稱已存在"}), 400
    return jsonify({"message": "更新成功"})


@app.route("/api/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    db = get_db()
    used = db.execute(
        "SELECT COUNT(*) AS c FROM cost_records WHERE category_id = ?", (cat_id,)
    ).fetchone()["c"]
    if used > 0:
        db.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (cat_id,))
        db.commit()
        return jsonify({"message": "此項目已有歷史紀錄，已改為停用而非刪除"})
    db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    db.commit()
    return jsonify({"message": "刪除成功"})


# ---------- API: daily sales ----------

@app.route("/api/sales", methods=["GET"])
def get_sales():
    d = request.args.get("date")
    if not d:
        return jsonify({"error": "date 為必填"}), 400
    db = get_db()
    row = db.execute("SELECT * FROM daily_sales WHERE date = ?", (d,)).fetchone()
    return jsonify({"date": d, "revenue": row["revenue"] if row else 0})


@app.route("/api/sales", methods=["POST"])
def upsert_sales():
    data = request.get_json(force=True) or {}
    d = data.get("date")
    revenue = data.get("revenue")
    if not d or revenue is None:
        return jsonify({"error": "date 和 revenue 為必填"}), 400
    try:
        revenue = float(revenue)
    except (TypeError, ValueError):
        return jsonify({"error": "營業額必須為數字"}), 400

    db = get_db()
    db.execute(
        """
        INSERT INTO daily_sales (date, revenue) VALUES (?, ?)
        ON CONFLICT(date) DO UPDATE SET revenue = excluded.revenue
        """,
        (d, revenue),
    )
    db.commit()
    return jsonify({"message": "已儲存", "date": d, "revenue": revenue})


# ---------- API: cost records ----------

@app.route("/api/costs", methods=["GET"])
def list_costs():
    d = request.args.get("date")
    db = get_db()
    if d:
        rows = db.execute(
            """
            SELECT cr.id, cr.date, cr.amount, cr.note, c.id AS category_id, c.name AS category_name
            FROM cost_records cr JOIN categories c ON c.id = cr.category_id
            WHERE cr.date = ?
            ORDER BY cr.id DESC
            """,
            (d,),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT cr.id, cr.date, cr.amount, cr.note, c.id AS category_id, c.name AS category_name
            FROM cost_records cr JOIN categories c ON c.id = cr.category_id
            ORDER BY cr.date DESC, cr.id DESC
            LIMIT 100
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/costs", methods=["POST"])
def add_cost():
    data = request.get_json(force=True) or {}
    d = data.get("date")
    category_id = data.get("category_id")
    amount = data.get("amount")
    note = (data.get("note") or "").strip()

    if not d or not category_id or amount is None:
        return jsonify({"error": "date、category_id、amount 為必填"}), 400
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({"error": "金額必須為數字"}), 400

    db = get_db()
    cat = db.execute("SELECT id FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not cat:
        return jsonify({"error": "找不到此成本項目"}), 400

    cur = db.execute(
        "INSERT INTO cost_records (date, category_id, amount, note) VALUES (?, ?, ?, ?)",
        (d, category_id, amount, note),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "message": "新增成功"})


@app.route("/api/costs/<int:cost_id>", methods=["DELETE"])
def delete_cost(cost_id):
    db = get_db()
    db.execute("DELETE FROM cost_records WHERE id = ?", (cost_id,))
    db.commit()
    return jsonify({"message": "刪除成功"})


# ---------- API: dashboard / reports ----------

@app.route("/api/recent", methods=["GET"])
def recent_summary():
    days = int(request.args.get("days", 14))
    db = get_db()
    end = date.today()
    start = end - timedelta(days=days - 1)

    sales_rows = db.execute(
        "SELECT date, revenue FROM daily_sales WHERE date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    revenue_by_date = {r["date"]: r["revenue"] for r in sales_rows}

    cost_rows = db.execute(
        "SELECT date, SUM(amount) AS total FROM cost_records WHERE date BETWEEN ? AND ? GROUP BY date",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    cost_by_date = {r["date"]: r["total"] for r in cost_rows}

    result = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        revenue = revenue_by_date.get(d, 0) or 0
        cost = cost_by_date.get(d, 0) or 0
        result.append({"date": d, "revenue": revenue, "cost": cost, "profit": revenue - cost})
    result.reverse()
    return jsonify(result)


@app.route("/api/report/monthly", methods=["GET"])
def monthly_report():
    month = request.args.get("month")
    if not month:
        return jsonify({"error": "month 為必填 (格式 YYYY-MM)"}), 400
    try:
        start, end = month_bounds(month)
    except ValueError:
        return jsonify({"error": "month 格式錯誤，需為 YYYY-MM"}), 400

    db = get_db()

    revenue = db.execute(
        "SELECT COALESCE(SUM(revenue), 0) AS total FROM daily_sales WHERE date >= ? AND date < ?",
        (start, end),
    ).fetchone()["total"]

    categories = db.execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order, id"
    ).fetchall()

    cost_totals = db.execute(
        """
        SELECT category_id, SUM(amount) AS total
        FROM cost_records
        WHERE date >= ? AND date < ?
        GROUP BY category_id
        """,
        (start, end),
    ).fetchall()
    cost_by_category = {r["category_id"]: r["total"] for r in cost_totals}

    cost_breakdown = []
    total_cost = 0
    for c in categories:
        amount = cost_by_category.get(c["id"], 0) or 0
        total_cost += amount
        percent = (amount / revenue * 100) if revenue > 0 else 0
        cost_breakdown.append(
            {
                "category_id": c["id"],
                "name": c["name"],
                "amount": amount,
                "percent": round(percent, 2),
                "target_percent": c["target_percent"],
                "exceeded": percent > c["target_percent"],
            }
        )

    profit = revenue - total_cost
    profit_margin = (profit / revenue * 100) if revenue > 0 else 0

    daily_rows = db.execute(
        "SELECT date, revenue FROM daily_sales WHERE date >= ? AND date < ? ORDER BY date",
        (start, end),
    ).fetchall()
    daily_cost_rows = db.execute(
        "SELECT date, SUM(amount) AS total FROM cost_records WHERE date >= ? AND date < ? GROUP BY date",
        (start, end),
    ).fetchall()
    daily_cost_map = {r["date"]: r["total"] for r in daily_cost_rows}
    daily = [
        {
            "date": r["date"],
            "revenue": r["revenue"],
            "cost": daily_cost_map.get(r["date"], 0) or 0,
        }
        for r in daily_rows
    ]

    return jsonify(
        {
            "month": month,
            "revenue": revenue,
            "total_cost": total_cost,
            "profit": profit,
            "profit_margin": round(profit_margin, 2),
            "cost_breakdown": cost_breakdown,
            "daily": daily,
        }
    )


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
