import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, g, jsonify, render_template, request

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bento.db")

# 食材成本細項（取代單一的「食材」，對照店裡的成本表分類）
# 這些項目本身沒有個別標準佔比，是全部加總後跟 FOOD_GROUP_TARGET_PERCENT 比較
FOOD_SUBCATEGORY_NAMES = [
    "肉",
    "包材(食材)",
    "雜貨",
    "青菜",
    "蛋",
    "珍珠香腸",
    "主餐配菜",
    "套餐配菜",
    "湯品配菜",
    "泡菜",
    "醬汁",
    "冷飲",
]

FOOD_GROUP_TARGET_PERCENT = 42  # 所有食材項目加總，不可超過這個佔比

# (name, target_percent, is_payroll_category)
OTHER_CATEGORIES = [
    ("人事", 25, 1),
    ("租金", 12, 0),
    ("包材/餐盒容器", 5, 0),
    ("水電", 3, 0),
    ("瓦斯", 2, 0),
    ("電話費", 1, 0),
    ("雜支", 3, 0),
]

DEFAULT_CATEGORIES = [
    (name, 0, i + 1, 0, 1) for i, name in enumerate(FOOD_SUBCATEGORY_NAMES)
] + [
    (name, target, len(FOOD_SUBCATEGORY_NAMES) + i + 1, is_payroll, 0)
    for i, (name, target, is_payroll) in enumerate(OTHER_CATEGORIES)
]

DEFAULT_EMPLOYEES = [
    # (name, employee_type, monthly_salary, hourly_rate)
    ("林翰于", "正職", 42000, None),
    ("陳逸雲", "計時", None, 198),
    ("詹與真", "計時", None, 198),
    ("李柏成", "計時", None, 198),
    ("陳俞安", "計時", None, 198),
    ("記永安", "計時", None, 198),
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


def _ensure_column(conn, table, column, decl):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _migrate_food_subcategories(conn):
    """Split the old generic 食材 category into the shop's detailed food sub-categories."""
    old_food = conn.execute("SELECT id FROM categories WHERE name = '食材'").fetchone()
    if old_food:
        old_id = old_food[0]
        used = conn.execute(
            "SELECT COUNT(*) FROM cost_records WHERE category_id = ?", (old_id,)
        ).fetchone()[0]
        if used > 0:
            conn.execute("UPDATE categories SET is_active = 0 WHERE id = ?", (old_id,))
        else:
            conn.execute("DELETE FROM categories WHERE id = ?", (old_id,))

    existing_names = {row[0] for row in conn.execute("SELECT name FROM categories")}
    next_order = conn.execute("SELECT COALESCE(MAX(sort_order), 0) AS m FROM categories").fetchone()[0] + 1
    for name in FOOD_SUBCATEGORY_NAMES:
        if name not in existing_names:
            conn.execute(
                "INSERT INTO categories (name, target_percent, sort_order, is_payroll_category, is_food_group) VALUES (?, 0, ?, 0, 1)",
                (name, next_order),
            )
            next_order += 1

    # 食材子項目沒有個別標準，只看加總；確保旗標與個別目標值一致
    placeholders = ",".join("?" for _ in FOOD_SUBCATEGORY_NAMES)
    conn.execute(
        f"UPDATE categories SET is_food_group = 1, target_percent = 0 WHERE name IN ({placeholders})",
        FOOD_SUBCATEGORY_NAMES,
    )
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('food_group_target', ?)",
        (FOOD_GROUP_TARGET_PERCENT,),
    )


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
    _ensure_column(conn, "categories", "is_payroll_category", "INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE categories SET is_payroll_category = 1 WHERE name = '人事' AND is_payroll_category = 0")
    _ensure_column(conn, "categories", "is_food_group", "INTEGER NOT NULL DEFAULT 0")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            employee_type TEXT NOT NULL CHECK (employee_type IN ('正職', '計時')),
            monthly_salary REAL,
            hourly_rate REAL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS work_hours (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            hours REAL NOT NULL,
            FOREIGN KEY (employee_id) REFERENCES employees(id),
            UNIQUE (employee_id, date)
        )
        """
    )
    if first_time:
        conn.executemany(
            "INSERT INTO categories (name, target_percent, sort_order, is_payroll_category, is_food_group) VALUES (?, ?, ?, ?, ?)",
            DEFAULT_CATEGORIES,
        )
        conn.executemany(
            "INSERT INTO employees (name, employee_type, monthly_salary, hourly_rate) VALUES (?, ?, ?, ?)",
            DEFAULT_EMPLOYEES,
        )
    _migrate_food_subcategories(conn)
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


@app.route("/staff")
def staff_page():
    return render_template("staff.html", today=date.today().isoformat())


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
    is_food_group = 1 if data.get("is_food_group") else 0
    if not name:
        return jsonify({"error": "項目名稱為必填"}), 400
    try:
        target_percent = 0 if is_food_group else float(target_percent)
    except (TypeError, ValueError):
        return jsonify({"error": "目標佔比必須為數字"}), 400

    db = get_db()
    max_order = db.execute("SELECT COALESCE(MAX(sort_order), 0) AS m FROM categories").fetchone()["m"]
    try:
        cur = db.execute(
            "INSERT INTO categories (name, target_percent, sort_order, is_food_group) VALUES (?, ?, ?, ?)",
            (name, target_percent, max_order + 1, is_food_group),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此項目名稱已存在"}), 400
    return jsonify({"id": cur.lastrowid, "name": name, "target_percent": target_percent, "is_food_group": is_food_group})


@app.route("/api/categories/<int:cat_id>", methods=["PUT"])
def update_category(cat_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if not row:
        return jsonify({"error": "找不到此項目"}), 404

    name = data.get("name", row["name"]).strip()
    is_food_group = 1 if data.get("is_food_group", row["is_food_group"]) else 0
    target_percent = data.get("target_percent", row["target_percent"])
    is_active = data.get("is_active", row["is_active"])
    try:
        target_percent = 0 if is_food_group else float(target_percent)
    except (TypeError, ValueError):
        return jsonify({"error": "目標佔比必須為數字"}), 400

    try:
        db.execute(
            "UPDATE categories SET name = ?, target_percent = ?, is_active = ?, is_food_group = ? WHERE id = ?",
            (name, target_percent, 1 if is_active else 0, is_food_group, cat_id),
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
    cat = db.execute("SELECT id, is_payroll_category FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not cat:
        return jsonify({"error": "找不到此成本項目"}), 400
    if cat["is_payroll_category"]:
        return jsonify({"error": "人事成本請至「人事設定」頁面登記薪資與工時，不用在這裡手動新增"}), 400

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


# ---------- API: employees ----------

@app.route("/api/employees", methods=["GET"])
def list_employees():
    db = get_db()
    only_active = request.args.get("active", "1") == "1"
    query = "SELECT * FROM employees"
    if only_active:
        query += " WHERE is_active = 1"
    query += " ORDER BY employee_type, id"
    rows = db.execute(query).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/employees", methods=["POST"])
def create_employee():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    employee_type = data.get("employee_type")
    monthly_salary = data.get("monthly_salary")
    hourly_rate = data.get("hourly_rate")

    if not name or employee_type not in ("正職", "計時"):
        return jsonify({"error": "姓名為必填，employee_type 必須是 正職 或 計時"}), 400

    try:
        monthly_salary = float(monthly_salary) if employee_type == "正職" and monthly_salary not in (None, "") else None
        hourly_rate = float(hourly_rate) if employee_type == "計時" and hourly_rate not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "薪資/時薪必須為數字"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO employees (name, employee_type, monthly_salary, hourly_rate) VALUES (?, ?, ?, ?)",
        (name, employee_type, monthly_salary, hourly_rate),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "message": "新增成功"})


@app.route("/api/employees/<int:emp_id>", methods=["PUT"])
def update_employee(emp_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM employees WHERE id = ?", (emp_id,)).fetchone()
    if not row:
        return jsonify({"error": "找不到此員工"}), 404

    name = (data.get("name", row["name"]) or "").strip()
    employee_type = data.get("employee_type", row["employee_type"])
    if employee_type not in ("正職", "計時"):
        return jsonify({"error": "employee_type 必須是 正職 或 計時"}), 400
    monthly_salary = data.get("monthly_salary", row["monthly_salary"])
    hourly_rate = data.get("hourly_rate", row["hourly_rate"])
    is_active = data.get("is_active", row["is_active"])

    try:
        monthly_salary = float(monthly_salary) if employee_type == "正職" and monthly_salary not in (None, "") else None
        hourly_rate = float(hourly_rate) if employee_type == "計時" and hourly_rate not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"error": "薪資/時薪必須為數字"}), 400

    db.execute(
        """
        UPDATE employees
        SET name = ?, employee_type = ?, monthly_salary = ?, hourly_rate = ?, is_active = ?
        WHERE id = ?
        """,
        (name, employee_type, monthly_salary, hourly_rate, 1 if is_active else 0, emp_id),
    )
    db.commit()
    return jsonify({"message": "更新成功"})


@app.route("/api/employees/<int:emp_id>", methods=["DELETE"])
def delete_employee(emp_id):
    db = get_db()
    used = db.execute(
        "SELECT COUNT(*) AS c FROM work_hours WHERE employee_id = ?", (emp_id,)
    ).fetchone()["c"]
    if used > 0:
        db.execute("UPDATE employees SET is_active = 0 WHERE id = ?", (emp_id,))
        db.commit()
        return jsonify({"message": "此員工已有工時紀錄，已改為停用而非刪除"})
    db.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    db.commit()
    return jsonify({"message": "刪除成功"})


# ---------- API: work hours (計時人員每日時數) ----------

@app.route("/api/work_hours", methods=["GET"])
def get_work_hours():
    d = request.args.get("date")
    if not d:
        return jsonify({"error": "date 為必填"}), 400
    db = get_db()
    rows = db.execute(
        """
        SELECT e.id AS employee_id, e.name, e.hourly_rate, wh.hours
        FROM employees e
        LEFT JOIN work_hours wh ON wh.employee_id = e.id AND wh.date = ?
        WHERE e.employee_type = '計時' AND e.is_active = 1
        ORDER BY e.id
        """,
        (d,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/work_hours", methods=["POST"])
def upsert_work_hours():
    data = request.get_json(force=True) or {}
    d = data.get("date")
    employee_id = data.get("employee_id")
    hours = data.get("hours")
    if not d or not employee_id or hours is None:
        return jsonify({"error": "date、employee_id、hours 為必填"}), 400
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        return jsonify({"error": "時數必須為數字"}), 400

    db = get_db()
    emp = db.execute(
        "SELECT id FROM employees WHERE id = ? AND employee_type = '計時'", (employee_id,)
    ).fetchone()
    if not emp:
        return jsonify({"error": "找不到此計時員工"}), 400

    db.execute(
        """
        INSERT INTO work_hours (employee_id, date, hours) VALUES (?, ?, ?)
        ON CONFLICT(employee_id, date) DO UPDATE SET hours = excluded.hours
        """,
        (employee_id, d, hours),
    )
    db.commit()
    return jsonify({"message": "已儲存"})


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
        """
        SELECT * FROM categories
        WHERE is_active = 1
           OR id IN (SELECT DISTINCT category_id FROM cost_records WHERE date >= ? AND date < ?)
        ORDER BY sort_order, id
        """,
        (start, end),
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

    payroll_total = None
    if any(c["is_payroll_category"] for c in categories):
        payroll_total = 0.0
        salaried = db.execute(
            "SELECT COALESCE(SUM(monthly_salary), 0) AS total FROM employees WHERE employee_type = '正職' AND is_active = 1"
        ).fetchone()["total"]
        payroll_total += salaried

        hourly_rows = db.execute(
            """
            SELECT e.hourly_rate, COALESCE(SUM(wh.hours), 0) AS total_hours
            FROM employees e
            LEFT JOIN work_hours wh ON wh.employee_id = e.id AND wh.date >= ? AND wh.date < ?
            WHERE e.employee_type = '計時' AND e.is_active = 1
            GROUP BY e.id
            """,
            (start, end),
        ).fetchall()
        for r in hourly_rows:
            payroll_total += (r["hourly_rate"] or 0) * r["total_hours"]

    food_group_target_row = db.execute(
        "SELECT value FROM app_settings WHERE key = 'food_group_target'"
    ).fetchone()
    food_group_target = food_group_target_row["value"] if food_group_target_row else FOOD_GROUP_TARGET_PERCENT

    cost_breakdown = []
    total_cost = 0
    food_group_amount = 0
    for c in categories:
        if c["is_payroll_category"]:
            amount = payroll_total or 0
        else:
            amount = cost_by_category.get(c["id"], 0) or 0
        total_cost += amount
        percent = (amount / revenue * 100) if revenue > 0 else 0
        is_food_group = bool(c["is_food_group"])
        if is_food_group:
            food_group_amount += amount
        cost_breakdown.append(
            {
                "category_id": c["id"],
                "name": c["name"],
                "amount": amount,
                "percent": round(percent, 2),
                "is_food_group": is_food_group,
                # 食材子項目沒有個別標準，只看全部加總是否超過 food_group 的標準
                "target_percent": None if is_food_group else c["target_percent"],
                "exceeded": False if is_food_group else percent > c["target_percent"],
            }
        )

    food_group_percent = (food_group_amount / revenue * 100) if revenue > 0 else 0
    food_group = {
        "amount": food_group_amount,
        "percent": round(food_group_percent, 2),
        "target_percent": food_group_target,
        "exceeded": food_group_percent > food_group_target,
    }

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
            "food_group": food_group,
            "daily": daily,
        }
    )


# ---------- API: settings ----------

@app.route("/api/settings/food_group_target", methods=["GET"])
def get_food_group_target():
    db = get_db()
    row = db.execute("SELECT value FROM app_settings WHERE key = 'food_group_target'").fetchone()
    return jsonify({"target_percent": row["value"] if row else FOOD_GROUP_TARGET_PERCENT})


@app.route("/api/settings/food_group_target", methods=["PUT"])
def update_food_group_target():
    data = request.get_json(force=True) or {}
    target = data.get("target_percent")
    try:
        target = float(target)
    except (TypeError, ValueError):
        return jsonify({"error": "標準佔比必須為數字"}), 400

    db = get_db()
    db.execute(
        """
        INSERT INTO app_settings (key, value) VALUES ('food_group_target', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (target,),
    )
    db.commit()
    return jsonify({"message": "更新成功", "target_percent": target})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
