import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, g, jsonify, render_template, request

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bento.db")

# 食材採購沒辦法拆成細項（每2、3天一張進貨單，只能key總金額），所以食材是單一項目。
# 一般成本項目：(name, target_percent, is_payroll_category, daily_computable)
# daily_computable=1 代表可以準確拆算出「當日成本」（人事＝當日工時+月薪/天數、租金＝月租金/天數）；
# 其餘項目是月結帳單（水電、瓦斯、電話費、包材、雜支）或只有每2、3天一筆的進貨（食材），
# 沒辦法準確攤算到單日，daily_computable=0，日檢視時不計入、僅供參考。
DEFAULT_CATEGORIES = [
    # (name, target_percent, sort_order, is_payroll_category, daily_computable)
    ("食材", 42, 1, 0, 0),
    ("人事", 25, 2, 1, 1),
    ("租金", 12, 3, 0, 1),
    ("包材/餐盒容器", 5, 4, 0, 0),
    ("水電", 3, 5, 0, 0),
    ("瓦斯", 2, 6, 0, 0),
    ("電話費", 1, 7, 0, 0),
    ("雜支", 3, 8, 0, 0),
]

DEFAULT_INCOME_CATEGORIES = [
    # (name, sort_order)
    ("其他雜項收入", 1),
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

# 食材單價：先放 0 佔位，等實際單價確認後再到「標準成本」頁面填入
# 單價由進貨單換算：豬肉片 540/3000g、洋蔥 320/10000g、高麗菜 700/20000g、
# 泡菜 360/3000g、豬絞肉 600/4000g、白飯(米) 1300/30000g、
# 蛋 800/180顆、珍珠香腸 610/(6包x150顆... 一包150顆)、百頁豆腐 1150/(6包x75片)、
# 雞腿 685/25片、豬排 520/25片、排骨 610/20片、雞排 640/20片、牛肉片 750/3000g
# 碗、蓋子是包材，跟「包材/餐盒容器」成本項目比對用，不算進食材成本
DEFAULT_INGREDIENTS = [
    # (name, unit, unit_cost, category)  category: food | packaging
    ("洋蔥", "克", 0.032, "food"),
    ("豬肉片", "克", 0.18, "food"),
    ("白飯", "克", 0.0433, "food"),
    ("蛋", "顆", 4.44, "food"),
    ("珍珠香腸", "顆", 4.07, "food"),
    ("高麗菜", "克", 0.035, "food"),
    ("百頁豆腐", "片", 2.56, "food"),
    ("泡菜", "克", 0.12, "food"),
    ("豬絞肉", "克", 0.15, "food"),
    ("雞腿", "片", 27.4, "food"),
    ("豬排", "片", 20.8, "food"),
    ("排骨", "片", 30.5, "food"),
    ("雞排", "片", 32, "food"),
    ("牛肉片", "克", 0.25, "food"),
    ("碗", "個", 2.25, "packaging"),
    ("蓋子", "個", 1.25, "packaging"),
]

# 8 個便當品項與各自的配方（食材名稱, 用量）；醬汁/水/油等低金額隱形成本先不計入
# 每個便當都用1個碗+1個蓋子
_PACKAGING = [("碗", 1), ("蓋子", 1)]
DEFAULT_BENTO_ITEMS = [
    ("招牌燒肉便當", [("洋蔥", 60), ("豬肉片", 60), ("白飯", 200), ("蛋", 1), ("珍珠香腸", 1), ("高麗菜", 70), ("百頁豆腐", 1)] + _PACKAGING),
    ("泡菜燒肉便當", [("泡菜", 60), ("豬肉片", 60), ("白飯", 200), ("蛋", 1), ("珍珠香腸", 1), ("高麗菜", 70), ("百頁豆腐", 1)] + _PACKAGING),
    ("打拋豬肉便當", [("豬絞肉", 80), ("白飯", 200), ("蛋", 1), ("珍珠香腸", 1), ("高麗菜", 70), ("百頁豆腐", 1)] + _PACKAGING),
    ("照燒雞腿便當", [("雞腿", 1), ("白飯", 200), ("蛋", 1), ("珍珠香腸", 1), ("高麗菜", 70), ("百頁豆腐", 1)] + _PACKAGING),
    ("黃金豬排便當", [("豬排", 1), ("白飯", 200), ("蛋", 1), ("珍珠香腸", 1), ("高麗菜", 70), ("百頁豆腐", 1)] + _PACKAGING),
    ("和風牛肉便當", [("洋蔥", 60), ("牛肉片", 80), ("白飯", 200), ("蛋", 1), ("珍珠香腸", 1), ("高麗菜", 70), ("百頁豆腐", 1)] + _PACKAGING),
    ("厚燒排骨便當", [("排骨", 1), ("白飯", 200), ("蛋", 1), ("珍珠香腸", 1), ("高麗菜", 70), ("百頁豆腐", 1)] + _PACKAGING),
    ("蜜汁雞排便當", [("雞排", 1), ("白飯", 200), ("蛋", 1), ("珍珠香腸", 1), ("高麗菜", 70), ("百頁豆腐", 1)] + _PACKAGING),
]

DEFAULT_BENTO_PRICES = {
    "招牌燒肉便當": 99,
    "泡菜燒肉便當": 105,
    "打拋豬肉便當": 110,
    "照燒雞腿便當": 115,
    "黃金豬排便當": 115,
    "和風牛肉便當": 120,
    "厚燒排骨便當": 125,
    "蜜汁雞排便當": 135,
}


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


# 上一版曾把食材拆成 12 個細項，但實際上進貨單沒辦法拆，這裡合併回單一「食材」項目
_OLD_FOOD_SUBCATEGORY_NAMES = [
    "肉", "包材(食材)", "雜貨", "青菜", "蛋", "珍珠香腸",
    "主餐配菜", "套餐配菜", "湯品配菜", "泡菜", "醬汁", "冷飲",
]


def _migrate_consolidate_food_categories(conn):
    """把曾經拆開的 12 個食材細項，合併回單一「食材」項目（金額一起帶過去，不遺失）。"""
    food_row = conn.execute("SELECT id FROM categories WHERE name = '食材'").fetchone()
    if food_row:
        food_id = food_row[0]
    else:
        target = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'food_group_target'"
        ).fetchone()
        target_percent = target[0] if target else 42
        next_order = conn.execute("SELECT COALESCE(MIN(sort_order), 1) AS m FROM categories").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO categories (name, target_percent, sort_order, is_payroll_category) VALUES ('食材', ?, ?, 0)",
            (target_percent, next_order),
        )
        food_id = cur.lastrowid

    placeholders = ",".join("?" for _ in _OLD_FOOD_SUBCATEGORY_NAMES)
    old_rows = conn.execute(
        f"SELECT id FROM categories WHERE name IN ({placeholders})", _OLD_FOOD_SUBCATEGORY_NAMES
    ).fetchall()
    for (old_id,) in old_rows:
        if old_id == food_id:
            continue
        conn.execute("UPDATE cost_records SET category_id = ? WHERE category_id = ?", (food_id, old_id))
        conn.execute("DELETE FROM categories WHERE id = ?", (old_id,))


def _migrate_daily_computable(conn):
    """人事、租金可以準確攤算到單日；其餘月結/進貨型項目不行。"""
    conn.execute("UPDATE categories SET daily_computable = 1 WHERE name IN ('人事', '租金')")


def _migrate_ingredient_prices(conn):
    """把換算好的食材單價回填進去；只補還是 0（沒被使用者自己改過）的項目，不覆蓋手動設定值。"""
    for name, unit, unit_cost, category in DEFAULT_INGREDIENTS:
        conn.execute(
            "INSERT OR IGNORE INTO ingredients (name, unit, unit_cost, category) VALUES (?, ?, ?, ?)",
            (name, unit, unit_cost, category),
        )
        conn.execute(
            "UPDATE ingredients SET unit_cost = ? WHERE name = ? AND unit_cost = 0",
            (unit_cost, name),
        )
        conn.execute(
            "UPDATE ingredients SET category = ? WHERE name = ?",
            (category, name),
        )
    # 這幾項單價曾經算錯過，這裡修正成正確值；只在還是上一版算出來的舊值時才覆蓋，
    # 避免蓋掉使用者後來自己手動調整過的單價
    for name, old_value, new_value in [
        ("泡菜", 0.16, 0.12),
        ("百頁豆腐", 6.8, 2.56),
        ("豬排", 25.6, 20.8),
        ("豬絞肉", 1.5, 0.15),
    ]:
        conn.execute(
            "UPDATE ingredients SET unit_cost = ? WHERE name = ? AND unit_cost = ?",
            (new_value, name, old_value),
        )


def _migrate_bento_items(conn):
    """幫已存在（但建立於便當品項功能之前）的資料庫種入8個便當品項與配方。"""
    existing_count = conn.execute("SELECT COUNT(*) FROM bento_items").fetchone()[0]
    if existing_count > 0:
        return
    ingredient_ids = {row[0]: row[1] for row in conn.execute("SELECT name, id FROM ingredients")}
    for bento_name, recipe in DEFAULT_BENTO_ITEMS:
        cur = conn.execute(
            "INSERT INTO bento_items (name, selling_price) VALUES (?, ?)",
            (bento_name, DEFAULT_BENTO_PRICES.get(bento_name, 0)),
        )
        bento_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO bento_recipe (bento_item_id, ingredient_id, quantity) VALUES (?, ?, ?)",
            [(bento_id, ingredient_ids[ing_name], qty) for ing_name, qty in recipe],
        )


def _migrate_bento_prices(conn):
    """把便當售價回填進去；只補還是 0（沒被使用者自己改過）的品項，不覆蓋手動設定值。"""
    for name, price in DEFAULT_BENTO_PRICES.items():
        conn.execute(
            "UPDATE bento_items SET selling_price = ? WHERE name = ? AND selling_price = 0",
            (price, name),
        )


def _migrate_beef_bento(conn):
    """和風牛肉便當原本誤用「豬肉片」，改成正確的「牛肉片」。"""
    beef_row = conn.execute("SELECT id FROM ingredients WHERE name = '牛肉片'").fetchone()
    if not beef_row:
        return
    beef_id = beef_row[0]

    conn.execute(
        """
        UPDATE bento_recipe
        SET ingredient_id = ?
        WHERE ingredient_id = (SELECT id FROM ingredients WHERE name = '豬肉片')
          AND bento_item_id = (SELECT id FROM bento_items WHERE name = '和風牛肉便當')
        """,
        (beef_id,),
    )


def _migrate_packaging_recipe(conn):
    """幫每個已存在的便當品項補上碗、蓋子（如果配方裡還沒有）。"""
    packaging_ids = {
        row[0]: row[1]
        for row in conn.execute("SELECT name, id FROM ingredients WHERE category = 'packaging'")
    }
    if not packaging_ids:
        return
    for bento_id, in conn.execute("SELECT id FROM bento_items"):
        existing = {
            row[0]
            for row in conn.execute(
                "SELECT ingredient_id FROM bento_recipe WHERE bento_item_id = ?", (bento_id,)
            )
        }
        for name, quantity in _PACKAGING:
            ing_id = packaging_ids.get(name)
            if ing_id and ing_id not in existing:
                conn.execute(
                    "INSERT INTO bento_recipe (bento_item_id, ingredient_id, quantity) VALUES (?, ?, ?)",
                    (bento_id, ing_id, quantity),
                )


def _migrate_income_categories(conn):
    """幫已存在的資料庫補上收入項目（如果還沒有的話）。"""
    existing_names = {row[0] for row in conn.execute("SELECT name FROM income_categories")}
    next_order = conn.execute(
        "SELECT COALESCE(MAX(sort_order), 0) AS m FROM income_categories"
    ).fetchone()[0] + 1
    for name, _ in DEFAULT_INCOME_CATEGORIES:
        if name not in existing_names:
            conn.execute(
                "INSERT INTO income_categories (name, sort_order) VALUES (?, ?)",
                (name, next_order),
            )
            next_order += 1


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
    _ensure_column(conn, "categories", "daily_computable", "INTEGER NOT NULL DEFAULT 0")

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
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            unit TEXT NOT NULL,
            unit_cost REAL NOT NULL DEFAULT 0
        )
        """
    )
    _ensure_column(conn, "ingredients", "category", "TEXT NOT NULL DEFAULT 'food'")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bento_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    _ensure_column(conn, "bento_items", "selling_price", "REAL NOT NULL DEFAULT 0")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bento_recipe (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bento_item_id INTEGER NOT NULL,
            ingredient_id INTEGER NOT NULL,
            quantity REAL NOT NULL,
            FOREIGN KEY (bento_item_id) REFERENCES bento_items(id),
            FOREIGN KEY (ingredient_id) REFERENCES ingredients(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bento_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bento_item_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (bento_item_id) REFERENCES bento_items(id),
            UNIQUE (bento_item_id, date)
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS income_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS income_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            note TEXT DEFAULT '',
            FOREIGN KEY (category_id) REFERENCES income_categories(id)
        )
        """
    )
    if first_time:
        conn.executemany(
            "INSERT INTO categories (name, target_percent, sort_order, is_payroll_category, daily_computable) VALUES (?, ?, ?, ?, ?)",
            DEFAULT_CATEGORIES,
        )
        conn.executemany(
            "INSERT INTO employees (name, employee_type, monthly_salary, hourly_rate) VALUES (?, ?, ?, ?)",
            DEFAULT_EMPLOYEES,
        )
        conn.executemany(
            "INSERT INTO income_categories (name, sort_order) VALUES (?, ?)",
            DEFAULT_INCOME_CATEGORIES,
        )
        conn.executemany(
            "INSERT INTO ingredients (name, unit, unit_cost, category) VALUES (?, ?, ?, ?)",
            DEFAULT_INGREDIENTS,
        )
        ingredient_ids = {row[0]: row[1] for row in conn.execute("SELECT name, id FROM ingredients")}
        for bento_name, recipe in DEFAULT_BENTO_ITEMS:
            cur = conn.execute(
                "INSERT INTO bento_items (name, selling_price) VALUES (?, ?)",
                (bento_name, DEFAULT_BENTO_PRICES.get(bento_name, 0)),
            )
            bento_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO bento_recipe (bento_item_id, ingredient_id, quantity) VALUES (?, ?, ?)",
                [(bento_id, ingredient_ids[ing_name], qty) for ing_name, qty in recipe],
            )
    _migrate_consolidate_food_categories(conn)
    _migrate_daily_computable(conn)
    _migrate_ingredient_prices(conn)
    _migrate_bento_items(conn)
    _migrate_bento_prices(conn)
    _migrate_beef_bento(conn)
    _migrate_packaging_recipe(conn)
    _migrate_income_categories(conn)
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
    return render_template("report.html", month=date.today().strftime("%Y-%m"), today=date.today().isoformat())


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/staff")
def staff_page():
    return render_template("staff.html", today=date.today().isoformat())


@app.route("/recipe")
def recipe_page():
    return render_template("recipe.html")


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
    daily_computable = 1 if data.get("daily_computable") else 0
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
            "INSERT INTO categories (name, target_percent, sort_order, daily_computable) VALUES (?, ?, ?, ?)",
            (name, target_percent, max_order + 1, daily_computable),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此項目名稱已存在"}), 400
    return jsonify({"id": cur.lastrowid, "name": name, "target_percent": target_percent, "daily_computable": daily_computable})


@app.route("/api/categories/<int:cat_id>", methods=["PUT"])
def update_category(cat_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    if not row:
        return jsonify({"error": "找不到此項目"}), 404

    name = data.get("name", row["name"]).strip()
    daily_computable = 1 if data.get("daily_computable", row["daily_computable"]) else 0
    target_percent = data.get("target_percent", row["target_percent"])
    is_active = data.get("is_active", row["is_active"])
    try:
        target_percent = float(target_percent)
    except (TypeError, ValueError):
        return jsonify({"error": "目標佔比必須為數字"}), 400

    try:
        db.execute(
            "UPDATE categories SET name = ?, target_percent = ?, is_active = ?, daily_computable = ? WHERE id = ?",
            (name, target_percent, 1 if is_active else 0, daily_computable, cat_id),
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


# ---------- API: income categories ----------

@app.route("/api/income_categories", methods=["GET"])
def list_income_categories():
    db = get_db()
    only_active = request.args.get("active", "1") == "1"
    query = "SELECT * FROM income_categories"
    if only_active:
        query += " WHERE is_active = 1"
    query += " ORDER BY sort_order, id"
    rows = db.execute(query).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/income_categories", methods=["POST"])
def create_income_category():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "項目名稱為必填"}), 400

    db = get_db()
    max_order = db.execute(
        "SELECT COALESCE(MAX(sort_order), 0) AS m FROM income_categories"
    ).fetchone()["m"]
    try:
        cur = db.execute(
            "INSERT INTO income_categories (name, sort_order) VALUES (?, ?)",
            (name, max_order + 1),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此項目名稱已存在"}), 400
    return jsonify({"id": cur.lastrowid, "name": name})


@app.route("/api/income_categories/<int:cat_id>", methods=["PUT"])
def update_income_category(cat_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM income_categories WHERE id = ?", (cat_id,)).fetchone()
    if not row:
        return jsonify({"error": "找不到此項目"}), 404

    name = data.get("name", row["name"]).strip()
    is_active = data.get("is_active", row["is_active"])
    try:
        db.execute(
            "UPDATE income_categories SET name = ?, is_active = ? WHERE id = ?",
            (name, 1 if is_active else 0, cat_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此項目名稱已存在"}), 400
    return jsonify({"message": "更新成功"})


@app.route("/api/income_categories/<int:cat_id>", methods=["DELETE"])
def delete_income_category(cat_id):
    db = get_db()
    used = db.execute(
        "SELECT COUNT(*) AS c FROM income_records WHERE category_id = ?", (cat_id,)
    ).fetchone()["c"]
    if used > 0:
        db.execute("UPDATE income_categories SET is_active = 0 WHERE id = ?", (cat_id,))
        db.commit()
        return jsonify({"message": "此項目已有歷史紀錄，已改為停用而非刪除"})
    db.execute("DELETE FROM income_categories WHERE id = ?", (cat_id,))
    db.commit()
    return jsonify({"message": "刪除成功"})


# ---------- API: special income records ----------

@app.route("/api/income", methods=["GET"])
def list_income():
    d = request.args.get("date")
    db = get_db()
    if d:
        rows = db.execute(
            """
            SELECT ir.id, ir.date, ir.amount, ir.note, c.id AS category_id, c.name AS category_name
            FROM income_records ir JOIN income_categories c ON c.id = ir.category_id
            WHERE ir.date = ?
            ORDER BY ir.id DESC
            """,
            (d,),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT ir.id, ir.date, ir.amount, ir.note, c.id AS category_id, c.name AS category_name
            FROM income_records ir JOIN income_categories c ON c.id = ir.category_id
            ORDER BY ir.date DESC, ir.id DESC
            LIMIT 100
            """
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/income", methods=["POST"])
def add_income():
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
    cat = db.execute("SELECT id FROM income_categories WHERE id = ?", (category_id,)).fetchone()
    if not cat:
        return jsonify({"error": "找不到此收入項目"}), 400

    cur = db.execute(
        "INSERT INTO income_records (date, category_id, amount, note) VALUES (?, ?, ?, ?)",
        (d, category_id, amount, note),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "message": "新增成功"})


@app.route("/api/income/<int:income_id>", methods=["DELETE"])
def delete_income(income_id):
    db = get_db()
    db.execute("DELETE FROM income_records WHERE id = ?", (income_id,))
    db.commit()
    return jsonify({"message": "刪除成功"})


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

    income_rows = db.execute(
        "SELECT date, SUM(amount) AS total FROM income_records WHERE date BETWEEN ? AND ? GROUP BY date",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    income_by_date = {r["date"]: r["total"] for r in income_rows}

    result = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        register_revenue = revenue_by_date.get(d, 0) or 0
        special_income = income_by_date.get(d, 0) or 0
        revenue = register_revenue + special_income
        cost = cost_by_date.get(d, 0) or 0
        result.append({
            "date": d,
            "revenue": revenue,
            "register_revenue": register_revenue,
            "special_income": special_income,
            "cost": cost,
            "profit": revenue - cost,
        })
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

    register_revenue = db.execute(
        "SELECT COALESCE(SUM(revenue), 0) AS total FROM daily_sales WHERE date >= ? AND date < ?",
        (start, end),
    ).fetchone()["total"]
    special_income = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM income_records WHERE date >= ? AND date < ?",
        (start, end),
    ).fetchone()["total"]
    revenue = register_revenue + special_income

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

    cost_breakdown = []
    total_cost = 0
    for c in categories:
        if c["is_payroll_category"]:
            amount = payroll_total or 0
        else:
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

    food_standard = compute_standard_cost_vs_actual(db, start, end, "food", "食材")
    packaging_standard = compute_standard_cost_vs_actual(db, start, end, "packaging", "包材/餐盒容器")
    revenue_check = compute_revenue_check(db, start, end, register_revenue)

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
    daily_income_rows = db.execute(
        "SELECT date, SUM(amount) AS total FROM income_records WHERE date >= ? AND date < ? GROUP BY date",
        (start, end),
    ).fetchall()
    daily_income_map = {r["date"]: r["total"] for r in daily_income_rows}
    daily = [
        {
            "date": r["date"],
            "revenue": r["revenue"] + (daily_income_map.get(r["date"], 0) or 0),
            "cost": daily_cost_map.get(r["date"], 0) or 0,
        }
        for r in daily_rows
    ]

    return jsonify(
        {
            "month": month,
            "revenue": revenue,
            "register_revenue": register_revenue,
            "special_income": special_income,
            "total_cost": total_cost,
            "profit": profit,
            "profit_margin": round(profit_margin, 2),
            "cost_breakdown": cost_breakdown,
            "food_standard": food_standard,
            "packaging_standard": packaging_standard,
            "revenue_check": revenue_check,
            "daily": daily,
        }
    )


@app.route("/api/report/daily", methods=["GET"])
def daily_report():
    d = request.args.get("date")
    if not d:
        return jsonify({"error": "date 為必填 (格式 YYYY-MM-DD)"}), 400
    try:
        the_date = datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "date 格式錯誤，需為 YYYY-MM-DD"}), 400

    db = get_db()
    days = days_in_month(the_date)
    month_start, month_end = month_bounds(the_date.strftime("%Y-%m"))

    revenue_row = db.execute("SELECT revenue FROM daily_sales WHERE date = ?", (d,)).fetchone()
    register_revenue = revenue_row["revenue"] if revenue_row else 0
    special_income_today = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM income_records WHERE date = ?", (d,)
    ).fetchone()["total"]
    revenue = register_revenue + special_income_today

    categories = db.execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY sort_order, id"
    ).fetchall()

    payroll_today, payroll_breakdown = compute_payroll_for_date(db, the_date, days)

    computable = []
    computable_subtotal = 0
    reference = []
    for c in categories:
        if c["is_payroll_category"]:
            amount = payroll_today
            computable.append({
                "category_id": c["id"], "name": c["name"], "amount": amount,
                "note": "當日計時工時 × 時薪 ＋ 正職月薪 ÷ 當月天數",
                "breakdown": payroll_breakdown,
            })
            computable_subtotal += amount
        elif c["daily_computable"]:
            month_total = db.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM cost_records WHERE category_id = ? AND date >= ? AND date < ?",
                (c["id"], month_start, month_end),
            ).fetchone()["total"]
            amount = month_total / days
            computable.append({
                "category_id": c["id"], "name": c["name"], "amount": round(amount, 2),
                "note": f"當月合計 {fmt_amount(month_total)} ÷ {days} 天",
            })
            computable_subtotal += amount
        else:
            today_amount = db.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total FROM cost_records WHERE category_id = ? AND date = ?",
                (c["id"], d),
            ).fetchone()["total"]
            reference.append({"category_id": c["id"], "name": c["name"], "amount_today": today_amount})

    return jsonify(
        {
            "date": d,
            "days_in_month": days,
            "revenue": revenue,
            "register_revenue": register_revenue,
            "special_income": special_income_today,
            "computable_costs": computable,
            "computable_subtotal": round(computable_subtotal, 2),
            "reference_costs": reference,
        }
    )


def fmt_amount(v):
    return f"{v:,.0f}"


def days_in_month(d):
    if d.month == 12:
        next_month = date(d.year + 1, 1, 1)
    else:
        next_month = date(d.year, d.month + 1, 1)
    return (next_month - date(d.year, d.month, 1)).days


def compute_payroll_for_date(db, the_date, days_in_current_month):
    breakdown = []
    total = 0.0

    salaried_rows = db.execute(
        "SELECT id, name, monthly_salary FROM employees WHERE employee_type = '正職' AND is_active = 1"
    ).fetchall()
    for r in salaried_rows:
        daily_wage = round((r["monthly_salary"] or 0) / days_in_current_month, 2)
        total += daily_wage
        breakdown.append(
            {
                "employee_id": r["id"],
                "name": r["name"],
                "employee_type": "正職",
                "hours": None,
                "rate": None,
                "amount": daily_wage,
                "note": f"月薪 {fmt_amount(r['monthly_salary'] or 0)} ÷ {days_in_current_month} 天",
            }
        )

    hourly_rows = db.execute(
        """
        SELECT e.id, e.name, e.hourly_rate, COALESCE(wh.hours, 0) AS hours
        FROM employees e
        LEFT JOIN work_hours wh ON wh.employee_id = e.id AND wh.date = ?
        WHERE e.employee_type = '計時' AND e.is_active = 1
        """,
        (the_date.isoformat(),),
    ).fetchall()
    for r in hourly_rows:
        amount = round((r["hourly_rate"] or 0) * r["hours"], 2)
        total += amount
        breakdown.append(
            {
                "employee_id": r["id"],
                "name": r["name"],
                "employee_type": "計時",
                "hours": r["hours"],
                "rate": r["hourly_rate"],
                "amount": amount,
                "note": f"{fmt_amount(r['hours'])} 小時 × {fmt_amount(r['hourly_rate'] or 0)}",
            }
        )

    return round(total, 2), breakdown


# ---------- 便當標準成本（食材理論成本 vs 實際採購金額）----------

def compute_standard_cost_vs_actual(db, start, end, ingredient_category, actual_category_name):
    """算出用配方推出的理論成本，跟某個成本項目當月實際花費比對。
    ingredient_category 決定配方裡只算哪一類食材（food=食材、packaging=包材），
    actual_category_name 是要拿來比對實際花費的成本項目名稱（例如「食材」「包材/餐盒容器」）。
    """
    bento_rows = db.execute(
        """
        SELECT bi.id AS bento_item_id, bi.name, COALESCE(SUM(bs.quantity), 0) AS quantity
        FROM bento_items bi
        LEFT JOIN bento_sales bs ON bs.bento_item_id = bi.id AND bs.date >= ? AND bs.date < ?
        WHERE bi.is_active = 1
        GROUP BY bi.id
        """,
        (start, end),
    ).fetchall()

    recipe_costs = {
        r["bento_item_id"]: r["cost"]
        for r in db.execute(
            """
            SELECT br.bento_item_id, SUM(br.quantity * i.unit_cost) AS cost
            FROM bento_recipe br JOIN ingredients i ON i.id = br.ingredient_id
            WHERE i.category = ?
            GROUP BY br.bento_item_id
            """,
            (ingredient_category,),
        ).fetchall()
    }

    items = []
    theoretical_total = 0
    total_quantity = 0
    for r in bento_rows:
        cost_per_unit = recipe_costs.get(r["bento_item_id"], 0) or 0
        subtotal = cost_per_unit * r["quantity"]
        theoretical_total += subtotal
        total_quantity += r["quantity"]
        items.append(
            {
                "bento_item_id": r["bento_item_id"],
                "name": r["name"],
                "quantity": r["quantity"],
                "standard_cost_per_unit": round(cost_per_unit, 2),
                "theoretical_cost": round(subtotal, 2),
            }
        )

    actual_category = db.execute(
        "SELECT id FROM categories WHERE name = ?", (actual_category_name,)
    ).fetchone()
    actual_cost = 0
    if actual_category:
        actual_cost = db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM cost_records WHERE category_id = ? AND date >= ? AND date < ?",
            (actual_category["id"], start, end),
        ).fetchone()["total"]

    return {
        "items": items,
        "total_quantity": total_quantity,
        "theoretical_cost": round(theoretical_total, 2),
        "actual_cost": actual_cost,
        "difference": round(actual_cost - theoretical_total, 2),
    }


def compute_revenue_check(db, start, end, register_revenue):
    """用「賣出數量 x 售價」算出理論營業額，跟收銀機實際登記的營業額比對，抓漏登記或折扣落差。"""
    rows = db.execute(
        """
        SELECT bi.id AS bento_item_id, bi.name, bi.selling_price, COALESCE(SUM(bs.quantity), 0) AS quantity
        FROM bento_items bi
        LEFT JOIN bento_sales bs ON bs.bento_item_id = bi.id AND bs.date >= ? AND bs.date < ?
        WHERE bi.is_active = 1
        GROUP BY bi.id
        """,
        (start, end),
    ).fetchall()

    items = []
    theoretical_revenue = 0
    for r in rows:
        subtotal = r["selling_price"] * r["quantity"]
        theoretical_revenue += subtotal
        items.append(
            {
                "bento_item_id": r["bento_item_id"],
                "name": r["name"],
                "quantity": r["quantity"],
                "selling_price": r["selling_price"],
                "theoretical_revenue": round(subtotal, 2),
            }
        )

    return {
        "items": items,
        "theoretical_revenue": round(theoretical_revenue, 2),
        "actual_revenue": register_revenue,
        "difference": round(register_revenue - theoretical_revenue, 2),
    }


# ---------- API: ingredients ----------

@app.route("/api/ingredients", methods=["GET"])
def list_ingredients():
    db = get_db()
    rows = db.execute("SELECT * FROM ingredients ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/ingredients", methods=["POST"])
def create_ingredient():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    unit = (data.get("unit") or "").strip()
    unit_cost = data.get("unit_cost", 0)
    category = data.get("category", "food")
    if category not in ("food", "packaging"):
        category = "food"
    if not name or not unit:
        return jsonify({"error": "名稱與單位為必填"}), 400
    try:
        unit_cost = float(unit_cost)
    except (TypeError, ValueError):
        return jsonify({"error": "單價必須為數字"}), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO ingredients (name, unit, unit_cost, category) VALUES (?, ?, ?, ?)",
            (name, unit, unit_cost, category),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此食材名稱已存在"}), 400
    return jsonify({"id": cur.lastrowid, "message": "新增成功"})


@app.route("/api/ingredients/<int:ing_id>", methods=["PUT"])
def update_ingredient(ing_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM ingredients WHERE id = ?", (ing_id,)).fetchone()
    if not row:
        return jsonify({"error": "找不到此食材"}), 404

    name = (data.get("name", row["name"]) or "").strip()
    unit = (data.get("unit", row["unit"]) or "").strip()
    unit_cost = data.get("unit_cost", row["unit_cost"])
    category = data.get("category", row["category"])
    if category not in ("food", "packaging"):
        category = row["category"]
    try:
        unit_cost = float(unit_cost)
    except (TypeError, ValueError):
        return jsonify({"error": "單價必須為數字"}), 400

    try:
        db.execute(
            "UPDATE ingredients SET name = ?, unit = ?, unit_cost = ?, category = ? WHERE id = ?",
            (name, unit, unit_cost, category, ing_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此食材名稱已存在"}), 400
    return jsonify({"message": "更新成功"})


# ---------- API: bento items / recipe / sales ----------

@app.route("/api/bento_items", methods=["GET"])
def list_bento_items():
    db = get_db()
    items = db.execute("SELECT * FROM bento_items WHERE is_active = 1 ORDER BY id").fetchall()
    recipe_rows = db.execute(
        """
        SELECT br.id, br.bento_item_id, br.ingredient_id, br.quantity,
               i.name AS ingredient_name, i.unit, i.unit_cost
        FROM bento_recipe br JOIN ingredients i ON i.id = br.ingredient_id
        ORDER BY br.id
        """
    ).fetchall()

    recipes_by_item = {}
    for r in recipe_rows:
        recipes_by_item.setdefault(r["bento_item_id"], []).append(dict(r))

    result = []
    for item in items:
        recipe = recipes_by_item.get(item["id"], [])
        standard_cost = sum(r["quantity"] * r["unit_cost"] for r in recipe)
        selling_price = item["selling_price"]
        margin = selling_price - standard_cost
        margin_percent = (margin / selling_price * 100) if selling_price > 0 else 0
        result.append(
            {
                "id": item["id"],
                "name": item["name"],
                "recipe": recipe,
                "standard_cost": round(standard_cost, 2),
                "selling_price": selling_price,
                "margin": round(margin, 2),
                "margin_percent": round(margin_percent, 2),
            }
        )
    return jsonify(result)


@app.route("/api/bento_items/<int:item_id>", methods=["PUT"])
def update_bento_item(item_id):
    data = request.get_json(force=True) or {}
    db = get_db()
    row = db.execute("SELECT * FROM bento_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        return jsonify({"error": "找不到此便當品項"}), 404

    name = (data.get("name", row["name"]) or "").strip()
    selling_price = data.get("selling_price", row["selling_price"])
    try:
        selling_price = float(selling_price)
    except (TypeError, ValueError):
        return jsonify({"error": "售價必須為數字"}), 400

    try:
        db.execute(
            "UPDATE bento_items SET name = ?, selling_price = ? WHERE id = ?",
            (name, selling_price, item_id),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "此品項名稱已存在"}), 400
    return jsonify({"message": "更新成功"})


@app.route("/api/bento_recipe/<int:recipe_id>", methods=["PUT"])
def update_bento_recipe(recipe_id):
    data = request.get_json(force=True) or {}
    quantity = data.get("quantity")
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return jsonify({"error": "用量必須為數字"}), 400

    db = get_db()
    row = db.execute("SELECT id FROM bento_recipe WHERE id = ?", (recipe_id,)).fetchone()
    if not row:
        return jsonify({"error": "找不到此配方項目"}), 404
    db.execute("UPDATE bento_recipe SET quantity = ? WHERE id = ?", (quantity, recipe_id))
    db.commit()
    return jsonify({"message": "更新成功"})


@app.route("/api/bento_sales", methods=["GET"])
def get_bento_sales():
    d = request.args.get("date")
    if not d:
        return jsonify({"error": "date 為必填"}), 400
    db = get_db()
    rows = db.execute(
        """
        SELECT bi.id AS bento_item_id, bi.name, bs.quantity
        FROM bento_items bi
        LEFT JOIN bento_sales bs ON bs.bento_item_id = bi.id AND bs.date = ?
        WHERE bi.is_active = 1
        ORDER BY bi.id
        """,
        (d,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/bento_sales", methods=["POST"])
def upsert_bento_sales():
    data = request.get_json(force=True) or {}
    d = data.get("date")
    bento_item_id = data.get("bento_item_id")
    quantity = data.get("quantity")
    if not d or not bento_item_id or quantity is None:
        return jsonify({"error": "date、bento_item_id、quantity 為必填"}), 400
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return jsonify({"error": "數量必須為整數"}), 400

    db = get_db()
    item = db.execute("SELECT id FROM bento_items WHERE id = ?", (bento_item_id,)).fetchone()
    if not item:
        return jsonify({"error": "找不到此便當品項"}), 400

    db.execute(
        """
        INSERT INTO bento_sales (bento_item_id, date, quantity) VALUES (?, ?, ?)
        ON CONFLICT(bento_item_id, date) DO UPDATE SET quantity = excluded.quantity
        """,
        (bento_item_id, d, quantity),
    )
    db.commit()
    return jsonify({"message": "已儲存"})


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
