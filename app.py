from flask import Flask, render_template, request, redirect, url_for, flash, g
import sqlite3
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "jewerly.db"

app = Flask(__name__)
app.secret_key = "dev-secret-key"


# -----------------------------
# Database helpers
# -----------------------------
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


def to_int(value, default=0):
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def to_money(value, default=0):
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(round(float(str(value).replace(",", ""))))
    except (TypeError, ValueError):
        return default


def normalize_phone(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def normalize_date(value):
    value = (value or "").strip()
    if not value:
        return ""
    if "/" in value:
        parts = value.split("/")
        if len(parts) == 3:
            y, m, d = parts
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return value


def next_order_id(db):
    row = db.execute('''
        SELECT MAX(CAST(oID AS INTEGER)) AS max_id
        FROM "ORDER"
        WHERE oID GLOB '[0-9]*'
    ''').fetchone()
    return str((row["max_id"] or 0) + 1)


@app.template_filter("mask_phone")
def mask_phone(phone):
    phone = str(phone or "")
    if len(phone) == 10 and phone.isdigit():
        return phone[:4] + "***" + phone[-3:]
    return phone


def init_db():
    """Create tables matching jewerly.db schema if the db file is empty."""
    db = get_db()

    # 清掉舊版程式誤建立的 legacy orders 表。
    # 這張表會引用不存在的 customer.phone_num，會造成刪除 CUSTOMER 時 foreign key mismatch。
    db.execute("DROP TABLE IF EXISTS orders")

    db.executescript('''
    CREATE TABLE IF NOT EXISTS CUSTOMER (
        phone_number TEXT (10) PRIMARY KEY UNIQUE
            CHECK (length(phone_number) = 10 AND phone_number NOT GLOB '*[^0-9]*'),
        name TEXT,
        gender TEXT,
        age INTEGER,
        platform TEXT,
        area TEXT
    );

    CREATE TABLE IF NOT EXISTS PRODUCT (
        iID TEXT PRIMARY KEY UNIQUE,
        size TEXT,
        i_name TEXT,
        cost TEXT,
        suggested_price TEXT,
        real_price TEXT,
        profits TEXT,
        available TEXT
    );

    CREATE TABLE IF NOT EXISTS MATERIAL_INVENTORY (
        mID TEXT PRIMARY KEY UNIQUE,
        m_name TEXT,
        m_size TEXT,
        wholesale_price TEXT,
        store TEXT,
        purchase_date TEXT,
        unit_price TEXT,
        stock TEXT,
        safe_stock TEXT,
        note TEXT
    );

    CREATE TABLE IF NOT EXISTS RECIPE (
        iID TEXT REFERENCES PRODUCT (iID) ON DELETE CASCADE ON UPDATE CASCADE,
        mID TEXT REFERENCES MATERIAL_INVENTORY (mID) ON DELETE RESTRICT ON UPDATE CASCADE,
        m_amount TEXT,
        size TEXT
    );

    CREATE TABLE IF NOT EXISTS "ORDER" (
        oID TEXT PRIMARY KEY UNIQUE,
        phone_number TEXT (10) REFERENCES CUSTOMER (phone_number) ON DELETE RESTRICT ON UPDATE CASCADE
            CHECK (length(phone_number) = 10 AND phone_number NOT GLOB '*[^0-9]*'),
        order_time TEXT,
        state TEXT,
        total_amount TEXT,
        price TEXT,
        ship_time TEXT
    );

    CREATE TABLE IF NOT EXISTS ORDER_DETAIL (
        oID TEXT REFERENCES "ORDER" (oID) ON DELETE CASCADE ON UPDATE CASCADE,
        iID TEXT REFERENCES PRODUCT (iID) ON DELETE RESTRICT ON UPDATE CASCADE,
        size TEXT,
        quantity INTEGER
    );
    ''')

    if db.execute("SELECT COUNT(*) AS c FROM CUSTOMER").fetchone()["c"] == 0:
        db.executemany('''
            INSERT INTO CUSTOMER(phone_number, name, gender, age, platform, area)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', [
            ("0908123618", "傅*瑋", "女", 29, "Plurk", "高雄"),
            ("0937123125", "許*慧", "女", 22, "IG", "台南"),
        ])

    if db.execute("SELECT COUNT(*) AS c FROM PRODUCT WHERE TRIM(COALESCE(iID, '')) != ''").fetchone()["c"] == 0:
        db.execute("DELETE FROM PRODUCT WHERE TRIM(COALESCE(iID, '')) = ''")
        products = [
            ("1", "大", "旭日", "250", "450", "450", "200", "5"),
            ("2", "中", "旭日", "220", "450", "450", "230", "5"),
            ("3", "小", "旭日", "200", "450", "450", "250", "5"),
            ("4", "大", "莓果雪酪", "260", "450", "450", "190", "5"),
            ("5", "中", "莓果雪酪", "230", "450", "450", "220", "5"),
            ("6", "小", "莓果雪酪", "210", "450", "450", "240", "5"),
        ]
        db.executemany('''
            INSERT INTO PRODUCT(iID, size, i_name, cost, suggested_price, real_price, profits, available)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', products)

    if db.execute("SELECT COUNT(*) AS c FROM MATERIAL_INVENTORY WHERE TRIM(COALESCE(mID, '')) != ''").fetchone()["c"] == 0:
        db.execute("DELETE FROM MATERIAL_INVENTORY WHERE TRIM(COALESCE(mID, '')) = ''")
        materials = [
            ("1", "黃膠花", "8", "94", "阿源小舖", "2025-10-20", "3.76", "25", "5", ""),
            ("2", "黃水晶", "5", "104", "e.NA", "2025-03-03", "1.04", "100", "10", ""),
            ("3", "白水晶", "7", "80", "阿源小舖", "2025-07-17", "1.57", "51", "10", ""),
            ("4", "酒黃黃水晶", "7", "64", "阿源小舖", "2025-09-26", "2.56", "25", "5", ""),
            ("5", "星光粉晶", "7", "52", "阿源小舖", "2025-08-01", "2.00", "26", "5", ""),
        ]
        db.executemany('''
            INSERT INTO MATERIAL_INVENTORY
            (mID, m_name, m_size, wholesale_price, store, purchase_date, unit_price, stock, safe_stock, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', materials)

    db.commit()


@app.before_request
def setup_database():
    init_db()


# -----------------------------
# Dashboard
# -----------------------------
@app.route("/")
def dashboard():
    db = get_db()

    order_count = db.execute('SELECT COUNT(*) AS c FROM "ORDER"').fetchone()["c"]
    customer_count = db.execute("SELECT COUNT(*) AS c FROM CUSTOMER").fetchone()["c"]
    product_count = db.execute("SELECT COUNT(*) AS c FROM PRODUCT WHERE TRIM(COALESCE(iID, '')) != ''").fetchone()["c"]
    material_count = db.execute("SELECT COUNT(*) AS c FROM MATERIAL_INVENTORY WHERE TRIM(COALESCE(mID, '')) != ''").fetchone()["c"]

    low_materials = db.execute('''
        SELECT * FROM MATERIAL_INVENTORY
        WHERE TRIM(COALESCE(mID, '')) != ''
          AND CAST(COALESCE(NULLIF(stock, ''), '0') AS INTEGER) <= CAST(COALESCE(NULLIF(safe_stock, ''), '0') AS INTEGER)
        ORDER BY CAST(COALESCE(NULLIF(stock, ''), '0') AS INTEGER) ASC
    ''').fetchall()

    low_products = db.execute('''
        SELECT * FROM PRODUCT
        WHERE TRIM(COALESCE(iID, '')) != ''
          AND CAST(COALESCE(NULLIF(available, ''), '0') AS INTEGER) <= 1
        ORDER BY CAST(COALESCE(NULLIF(available, ''), '0') AS INTEGER) ASC
    ''').fetchall()

    recent_orders = db.execute('''
        SELECT o.*, c.name
        FROM "ORDER" o
        JOIN CUSTOMER c ON c.phone_number = o.phone_number
        ORDER BY CAST(o.oID AS INTEGER) DESC
        LIMIT 5
    ''').fetchall()

    return render_template(
        "dashboard.html",
        order_count=order_count,
        customer_count=customer_count,
        product_count=product_count,
        material_count=material_count,
        low_materials=low_materials,
        low_products=low_products,
        recent_orders=recent_orders,
    )


# -----------------------------
# Customer
# -----------------------------
@app.route("/customers")
def customers():
    q = request.args.get("q", "").strip()
    db = get_db()

    if q:
        rows = db.execute('''
            SELECT * FROM CUSTOMER
            WHERE phone_number LIKE ? OR name LIKE ? OR platform LIKE ? OR area LIKE ?
            ORDER BY name
        ''', [f"%{q}%"] * 4).fetchall()
    else:
        rows = db.execute("SELECT * FROM CUSTOMER ORDER BY name").fetchall()

    return render_template("customers.html", customers=rows, q=q)


@app.route("/customers/new", methods=["GET", "POST"])
def customer_new():
    if request.method == "POST":
        db = get_db()
        phone_number = normalize_phone(request.form.get("phone_number"))
        if len(phone_number) != 10:
            flash("電話必須是 10 碼數字", "danger")
            return render_template("customer_form.html", customer=None)
        try:
            db.execute('''
                INSERT INTO CUSTOMER(phone_number, name, gender, age, platform, area)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                phone_number,
                request.form["name"].strip(),
                request.form.get("gender"),
                to_int(request.form.get("age")),
                request.form.get("platform"),
                request.form.get("area"),
            ))
            db.commit()
            flash("客戶新增成功", "success")
            return redirect(url_for("customers"))
        except sqlite3.IntegrityError:
            flash("電話已存在，請確認資料", "danger")

    return render_template("customer_form.html", customer=None)


@app.route("/customers/<phone_number>/edit", methods=["GET", "POST"])
def customer_edit(phone_number):
    db = get_db()
    customer = db.execute("SELECT * FROM CUSTOMER WHERE phone_number = ?", (phone_number,)).fetchone()

    if customer is None:
        flash("找不到客戶", "danger")
        return redirect(url_for("customers"))

    if request.method == "POST":
        db.execute('''
            UPDATE CUSTOMER
            SET name = ?, gender = ?, age = ?, platform = ?, area = ?
            WHERE phone_number = ?
        ''', (
            request.form["name"].strip(),
            request.form.get("gender"),
            to_int(request.form.get("age")),
            request.form.get("platform"),
            request.form.get("area"),
            phone_number,
        ))
        db.commit()
        flash("客戶更新成功", "success")
        return redirect(url_for("customers"))

    return render_template("customer_form.html", customer=customer)


@app.route("/customers/<phone_number>/delete", methods=["POST"])
def customer_delete(phone_number):
    db = get_db()
    try:
        db.execute("DELETE FROM CUSTOMER WHERE phone_number = ?", (phone_number,))
        db.commit()
        flash("客戶刪除成功", "success")
    except sqlite3.IntegrityError:
        flash("此客戶已有訂單，不能刪除", "danger")
    except sqlite3.OperationalError as e:
        db.rollback()
        flash(f"刪除失敗：資料表關聯設定有問題，請重新啟動程式讓系統自動修正。{e}", "danger")
    return redirect(url_for("customers"))


# -----------------------------
# Product
# -----------------------------
@app.route("/products")
def products():
    q = request.args.get("q", "").strip()
    db = get_db()

    base_sql = '''
        SELECT *,
               CAST(COALESCE(NULLIF(real_price, ''), '0') AS REAL) - CAST(COALESCE(NULLIF(cost, ''), '0') AS REAL) AS profits_calc
        FROM PRODUCT
        WHERE TRIM(COALESCE(iID, '')) != ''
    '''

    if q:
        rows = db.execute(base_sql + " AND (i_name LIKE ? OR size LIKE ? OR iID LIKE ?) ORDER BY CAST(iID AS INTEGER), iID", (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
    else:
        rows = db.execute(base_sql + " ORDER BY CAST(iID AS INTEGER), iID").fetchall()

    return render_template("products.html", products=rows, q=q)


@app.route("/products/new", methods=["GET", "POST"])
def product_new():
    if request.method == "POST":
        db = get_db()
        iID = request.form.get("iID", "").strip()
        cost = to_money(request.form.get("cost"))
        real_price = to_money(request.form.get("real_price"))
        profits = real_price - cost
        try:
            db.execute('''
                INSERT INTO PRODUCT(iID, size, i_name, cost, suggested_price, real_price, profits, available)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                iID,
                request.form["size"].strip(),
                request.form["i_name"].strip(),
                str(cost),
                str(to_money(request.form.get("suggested_price"))),
                str(real_price),
                str(profits),
                str(to_int(request.form.get("available"))),
            ))
            db.commit()
            flash("商品新增成功", "success")
            return redirect(url_for("products"))
        except sqlite3.IntegrityError:
            flash("商品編號已存在", "danger")

    return render_template("product_form.html", product=None)


@app.route("/products/<iID>/edit", methods=["GET", "POST"])
def product_edit(iID):
    db = get_db()
    product = db.execute("SELECT * FROM PRODUCT WHERE iID = ?", (iID,)).fetchone()

    if product is None:
        flash("找不到商品", "danger")
        return redirect(url_for("products"))

    if request.method == "POST":
        cost = to_money(request.form.get("cost"))
        real_price = to_money(request.form.get("real_price"))
        profits = real_price - cost
        db.execute('''
            UPDATE PRODUCT
            SET size = ?, i_name = ?, cost = ?, suggested_price = ?, real_price = ?, profits = ?, available = ?
            WHERE iID = ?
        ''', (
            request.form["size"].strip(),
            request.form["i_name"].strip(),
            str(cost),
            str(to_money(request.form.get("suggested_price"))),
            str(real_price),
            str(profits),
            str(to_int(request.form.get("available"))),
            iID,
        ))
        db.commit()
        flash("商品更新成功", "success")
        return redirect(url_for("products"))

    return render_template("product_form.html", product=product)


@app.route("/products/<iID>/delete", methods=["POST"])
def product_delete(iID):
    db = get_db()
    try:
        db.execute("DELETE FROM PRODUCT WHERE iID = ?", (iID,))
        db.commit()
        flash("商品刪除成功", "success")
    except sqlite3.IntegrityError:
        flash("商品已被訂單或配方使用，不能刪除", "danger")
    return redirect(url_for("products"))


# -----------------------------
# Material
# -----------------------------
@app.route("/materials")
def materials():
    q = request.args.get("q", "").strip()
    db = get_db()

    if q:
        rows = db.execute('''
            SELECT * FROM MATERIAL_INVENTORY
            WHERE TRIM(COALESCE(mID, '')) != ''
              AND (m_name LIKE ? OR store LIKE ? OR note LIKE ? OR mID LIKE ?)
            ORDER BY CAST(mID AS INTEGER), mID
        ''', [f"%{q}%"] * 4).fetchall()
    else:
        rows = db.execute('''
            SELECT * FROM MATERIAL_INVENTORY
            WHERE TRIM(COALESCE(mID, '')) != ''
            ORDER BY CAST(mID AS INTEGER), mID
        ''').fetchall()

    return render_template("materials.html", materials=rows, q=q)


@app.route("/materials/new", methods=["GET", "POST"])
def material_new():
    if request.method == "POST":
        db = get_db()
        try:
            db.execute('''
                INSERT INTO MATERIAL_INVENTORY
                (mID, m_name, m_size, wholesale_price, store, purchase_date, unit_price, stock, safe_stock, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                request.form.get("mID", "").strip(),
                request.form["m_name"].strip(),
                request.form.get("m_size"),
                str(to_money(request.form.get("wholesale_price"))),
                request.form.get("store"),
                normalize_date(request.form.get("purchase_date")),
                request.form.get("unit_price") or "0",
                str(to_int(request.form.get("stock"))),
                str(to_int(request.form.get("safe_stock"))),
                request.form.get("note"),
            ))
            db.commit()
            flash("物料新增成功", "success")
            return redirect(url_for("materials"))
        except sqlite3.IntegrityError:
            flash("物料編號已存在", "danger")

    return render_template("material_form.html", material=None)


@app.route("/materials/<mID>/edit", methods=["GET", "POST"])
def material_edit(mID):
    db = get_db()
    material = db.execute("SELECT * FROM MATERIAL_INVENTORY WHERE mID = ?", (mID,)).fetchone()

    if material is None:
        flash("找不到物料", "danger")
        return redirect(url_for("materials"))

    if request.method == "POST":
        db.execute('''
            UPDATE MATERIAL_INVENTORY
            SET m_name = ?, m_size = ?, wholesale_price = ?, store = ?, purchase_date = ?,
                unit_price = ?, stock = ?, safe_stock = ?, note = ?
            WHERE mID = ?
        ''', (
            request.form["m_name"].strip(),
            request.form.get("m_size"),
            str(to_money(request.form.get("wholesale_price"))),
            request.form.get("store"),
            normalize_date(request.form.get("purchase_date")),
            request.form.get("unit_price") or "0",
            str(to_int(request.form.get("stock"))),
            str(to_int(request.form.get("safe_stock"))),
            request.form.get("note"),
            mID,
        ))
        db.commit()
        flash("物料更新成功", "success")
        return redirect(url_for("materials"))

    return render_template("material_form.html", material=material)


@app.route("/materials/<mID>/delete", methods=["POST"])
def material_delete(mID):
    db = get_db()
    try:
        db.execute("DELETE FROM MATERIAL_INVENTORY WHERE mID = ?", (mID,))
        db.commit()
        flash("物料刪除成功", "success")
    except sqlite3.IntegrityError:
        flash("物料已被 BOM 使用，不能刪除", "danger")
    return redirect(url_for("materials"))


# -----------------------------
# Recipe / BOM
# -----------------------------
@app.route("/recipes")
def recipes():
    db = get_db()
    product_filter = request.args.get("product_key", "")

    products = db.execute('''
        SELECT *,
               CAST(COALESCE(NULLIF(real_price, ''), '0') AS REAL) - CAST(COALESCE(NULLIF(cost, ''), '0') AS REAL) AS profits_calc
        FROM PRODUCT
        WHERE TRIM(COALESCE(iID, '')) != ''
        ORDER BY CAST(iID AS INTEGER), iID
    ''').fetchall()

    product_boms = []
    for p in products:
        key = p["iID"]
        if product_filter and key != product_filter:
            continue

        items = db.execute('''
            SELECT
                r.iID,
                r.size,
                r.mID,
                r.m_amount,
                m.m_name,
                m.m_size,
                m.store,
                CAST(COALESCE(NULLIF(m.unit_price, ''), '0') AS REAL) AS unit_price_num,
                CAST(COALESCE(NULLIF(m.stock, ''), '0') AS INTEGER) AS stock_num,
                CAST(COALESCE(NULLIF(m.safe_stock, ''), '0') AS INTEGER) AS safe_stock_num,
                ROUND(CAST(COALESCE(NULLIF(r.m_amount, ''), '0') AS REAL) * CAST(COALESCE(NULLIF(m.unit_price, ''), '0') AS REAL), 2) AS material_cost
            FROM RECIPE r
            JOIN MATERIAL_INVENTORY m ON m.mID = r.mID
            WHERE r.iID = ?
            ORDER BY m.m_name
        ''', (p["iID"],)).fetchall()

        estimated_material_cost = round(sum((row["material_cost"] or 0) for row in items), 2)
        product_boms.append({
            "product": p,
            "key": key,
            "items": items,
            "estimated_material_cost": estimated_material_cost,
        })

    materials = db.execute('''
        SELECT * FROM MATERIAL_INVENTORY
        WHERE TRIM(COALESCE(mID, '')) != ''
        ORDER BY CAST(mID AS INTEGER), mID
    ''').fetchall()

    return render_template(
        "recipes.html",
        products=products,
        materials=materials,
        product_boms=product_boms,
        product_filter=product_filter,
    )


@app.route("/recipes/new", methods=["POST"])
def recipe_new():
    db = get_db()
    iID = request.form.get("iID")
    product = db.execute("SELECT * FROM PRODUCT WHERE iID = ?", (iID,)).fetchone()
    size = product["size"] if product else request.form.get("size")
    try:
        db.execute('''
            INSERT INTO RECIPE(iID, mID, m_amount, size)
            VALUES (?, ?, ?, ?)
        ''', (
            iID,
            request.form.get("mID"),
            str(to_int(request.form.get("m_amount"))),
            size,
        ))
        db.commit()
        flash("BOM 項目新增成功", "success")
    except sqlite3.IntegrityError:
        flash("BOM 已存在，或商品 / 物料不存在", "danger")
    return redirect(url_for("recipes"))


@app.route("/recipes/<iID>/<mID>/delete", methods=["POST"])
def recipe_delete(iID, mID):
    db = get_db()
    db.execute("DELETE FROM RECIPE WHERE iID = ? AND mID = ?", (iID, mID))
    db.commit()
    flash("BOM 項目刪除成功", "success")
    return redirect(url_for("recipes"))


# -----------------------------
# Orders
# -----------------------------
@app.route("/orders")
def orders():
    db = get_db()
    rows = db.execute('''
        SELECT o.*, c.name
        FROM "ORDER" o
        JOIN CUSTOMER c ON c.phone_number = o.phone_number
        ORDER BY CAST(o.oID AS INTEGER) DESC, o.oID DESC
    ''').fetchall()

    return render_template("orders.html", orders=rows)


@app.route("/orders/new", methods=["GET", "POST"])
def order_new():
    db = get_db()
    customers = db.execute("SELECT * FROM CUSTOMER ORDER BY name").fetchall()
    products_rows = db.execute('''
        SELECT *,
               CAST(COALESCE(NULLIF(real_price, ''), '0') AS INTEGER) AS price_num,
               CAST(COALESCE(NULLIF(cost, ''), '0') AS INTEGER) AS cost_num,
               CAST(COALESCE(NULLIF(available, ''), '0') AS INTEGER) AS stock_num
        FROM PRODUCT
        WHERE TRIM(COALESCE(iID, '')) != ''
        ORDER BY CAST(iID AS INTEGER), iID
    ''').fetchall()

    products_json = [dict(row) for row in products_rows]

    if request.method == "POST":
        phone_number = request.form.get("phone_number")
        order_time = normalize_date(request.form.get("order_time")) or date.today().isoformat()
        state = request.form.get("state") or "未出貨"
        ship_time = normalize_date(request.form.get("ship_time"))
        product_keys = request.form.getlist("product_key[]")
        quantities = request.form.getlist("quantity[]")

        cart = {}
        for idx, product_key in enumerate(product_keys):
            qty = to_int(quantities[idx] if idx < len(quantities) else 0)
            if not product_key or qty <= 0:
                continue
            cart[product_key] = cart.get(product_key, 0) + qty

        if not cart:
            flash("請至少選擇一項商品", "danger")
            return redirect(url_for("order_new"))

        order_items = []
        total_amount = 0
        total_price = 0
        for iID, qty in cart.items():
            product = db.execute('''
                SELECT *,
                       CAST(COALESCE(NULLIF(real_price, ''), '0') AS INTEGER) AS price_num,
                       CAST(COALESCE(NULLIF(available, ''), '0') AS INTEGER) AS stock_num
                FROM PRODUCT
                WHERE iID = ?
            ''', (iID,)).fetchone()

            if product is None:
                flash("找不到商品", "danger")
                return redirect(url_for("order_new"))

            if product["stock_num"] < qty:
                flash(f"{product['i_name']} / {product['size']} 庫存不足，目前只剩 {product['stock_num']} 件", "danger")
                return redirect(url_for("order_new"))

            total_amount += qty
            total_price += product["price_num"] * qty
            order_items.append((iID, product["size"], qty))

        try:
            db.execute("BEGIN")
            oID = next_order_id(db)
            db.execute('''
                INSERT INTO "ORDER"(oID, phone_number, order_time, state, total_amount, price, ship_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (oID, phone_number, order_time, state, str(total_amount), str(total_price), ship_time))

            for iID, size, qty in order_items:
                db.execute('''
                    INSERT INTO ORDER_DETAIL(oID, iID, size, quantity)
                    VALUES (?, ?, ?, ?)
                ''', (oID, iID, size, qty))

                db.execute('''
                    UPDATE PRODUCT
                    SET available = CAST(COALESCE(NULLIF(available, ''), '0') AS INTEGER) - ?
                    WHERE iID = ?
                ''', (qty, iID))

            db.commit()
            flash("訂單建立成功，購物車商品庫存已扣除", "success")
            return redirect(url_for("order_detail", oID=oID))

        except sqlite3.Error as e:
            db.rollback()
            flash(f"訂單建立失敗：{e}", "danger")

    return render_template(
        "order_form.html",
        customers=customers,
        products=products_rows,
        products_json=products_json,
    )


@app.route("/orders/<oID>")
def order_detail(oID):
    db = get_db()
    order = db.execute('''
        SELECT o.*, c.name
        FROM "ORDER" o
        JOIN CUSTOMER c ON c.phone_number = o.phone_number
        WHERE o.oID = ?
    ''', (oID,)).fetchone()

    if order is None:
        flash("找不到訂單", "danger")
        return redirect(url_for("orders"))

    details = db.execute('''
        SELECT od.*, p.i_name, p.real_price, p.cost,
               CAST(COALESCE(NULLIF(p.real_price, ''), '0') AS INTEGER) - CAST(COALESCE(NULLIF(p.cost, ''), '0') AS INTEGER) AS profit
        FROM ORDER_DETAIL od
        JOIN PRODUCT p ON p.iID = od.iID
        WHERE od.oID = ?
        ORDER BY p.i_name, od.size
    ''', (oID,)).fetchall()

    return render_template("order_detail.html", order=order, details=details)


@app.route("/orders/<oID>/state", methods=["POST"])
def order_update_state(oID):
    db = get_db()
    db.execute('''
        UPDATE "ORDER"
        SET state = ?
        WHERE oID = ?
    ''', (request.form.get("state"), oID))
    db.commit()
    flash("訂單狀態已更新", "success")
    return redirect(url_for("order_detail", oID=oID))


# -----------------------------
# Reports
# -----------------------------
@app.route("/reports")
def reports():
    db = get_db()

    today = date.today().isoformat()
    start_date = request.args.get("start_date") or today[:8] + "01"
    end_date = request.args.get("end_date") or today

    summary = db.execute('''
        SELECT
            COUNT(DISTINCT o.oID) AS order_count,
            COALESCE(SUM(od.quantity), 0) AS item_count,
            COALESCE(SUM(od.quantity * CAST(COALESCE(NULLIF(p.real_price, ''), '0') AS INTEGER)), 0) AS revenue,
            COALESCE(SUM(od.quantity * CAST(COALESCE(NULLIF(p.cost, ''), '0') AS INTEGER)), 0) AS cost,
            COALESCE(SUM(od.quantity * (CAST(COALESCE(NULLIF(p.real_price, ''), '0') AS INTEGER) - CAST(COALESCE(NULLIF(p.cost, ''), '0') AS INTEGER))), 0) AS gross_profit
        FROM "ORDER" o
        JOIN ORDER_DETAIL od ON od.oID = o.oID
        JOIN PRODUCT p ON p.iID = od.iID
        WHERE o.order_time BETWEEN ? AND ?
          AND o.state != '已取消'
    ''', (start_date, end_date)).fetchone()

    product_sales = db.execute('''
        SELECT
            p.iID,
            p.i_name,
            p.size,
            SUM(od.quantity) AS quantity,
            SUM(od.quantity * CAST(COALESCE(NULLIF(p.real_price, ''), '0') AS INTEGER)) AS revenue,
            SUM(od.quantity * CAST(COALESCE(NULLIF(p.cost, ''), '0') AS INTEGER)) AS cost,
            SUM(od.quantity * (CAST(COALESCE(NULLIF(p.real_price, ''), '0') AS INTEGER) - CAST(COALESCE(NULLIF(p.cost, ''), '0') AS INTEGER))) AS gross_profit
        FROM "ORDER" o
        JOIN ORDER_DETAIL od ON od.oID = o.oID
        JOIN PRODUCT p ON p.iID = od.iID
        WHERE o.order_time BETWEEN ? AND ?
          AND o.state != '已取消'
        GROUP BY p.iID, p.i_name, p.size
        ORDER BY revenue DESC
    ''', (start_date, end_date)).fetchall()

    daily_sales = db.execute('''
        SELECT
            o.order_time,
            COUNT(DISTINCT o.oID) AS order_count,
            SUM(od.quantity) AS item_count,
            SUM(od.quantity * CAST(COALESCE(NULLIF(p.real_price, ''), '0') AS INTEGER)) AS revenue,
            SUM(od.quantity * (CAST(COALESCE(NULLIF(p.real_price, ''), '0') AS INTEGER) - CAST(COALESCE(NULLIF(p.cost, ''), '0') AS INTEGER))) AS gross_profit
        FROM "ORDER" o
        JOIN ORDER_DETAIL od ON od.oID = o.oID
        JOIN PRODUCT p ON p.iID = od.iID
        WHERE o.order_time BETWEEN ? AND ?
          AND o.state != '已取消'
        GROUP BY o.order_time
        ORDER BY o.order_time
    ''', (start_date, end_date)).fetchall()

    order_rows = db.execute('''
        SELECT
            o.oID,
            o.order_time,
            o.state,
            c.name,
            o.total_amount,
            o.price
        FROM "ORDER" o
        JOIN CUSTOMER c ON c.phone_number = o.phone_number
        WHERE o.order_time BETWEEN ? AND ?
          AND o.state != '已取消'
        ORDER BY o.order_time DESC, CAST(o.oID AS INTEGER) DESC
    ''', (start_date, end_date)).fetchall()

    return render_template(
        "reports.html",
        start_date=start_date,
        end_date=end_date,
        summary=summary,
        product_sales=product_sales,
        daily_sales=daily_sales,
        order_rows=order_rows,
    )


if __name__ == "__main__":
    app.run(debug=True)
