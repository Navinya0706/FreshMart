"""FreshMart - grocery billing website (Python + Flask + SQLite).
Run:  python app.py   then open http://localhost:8080
"""
import os
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "freshmart.db")
app = Flask(__name__, static_folder="static", static_url_path="")

PRODUCTS = [
    (101, "Basmati Rice 1 kg", "Grains", 140, 40),
    (102, "Toor Dal 1 kg", "Pulses", 160, 30),
    (103, "Sunflower Oil 1 L", "Oil", 150, 25),
    (104, "Sugar 1 kg", "Essentials", 48, 50),
    (105, "Tea Powder 250 g", "Beverage", 120, 20),
    (106, "Wheat Flour 5 kg", "Grains", 260, 15),
]


def db():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def rows(sql, args=()):
    with db() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,name TEXT,category TEXT,price REAL,stock INTEGER,sold INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,token INTEGER,name TEXT,type TEXT,subtotal REAL,discount REAL,gst REAL,total REAL,created_at TEXT);
        CREATE TABLE IF NOT EXISTS order_items(order_id TEXT,product_id INTEGER,name TEXT,price REAL,quantity INTEGER);
        CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,rating INTEGER,comment TEXT,created_at TEXT);
        """)
        c.executemany("INSERT OR IGNORE INTO products(id,name,category,price,stock,sold) VALUES(?,?,?,?,?,0)", PRODUCTS)


def err(msg, code=400):
    return jsonify(error=msg), code


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/products")
def products():
    return jsonify(rows("SELECT * FROM products ORDER BY id"))


@app.get("/api/bills")
def bills():
    return jsonify(rows("SELECT * FROM orders ORDER BY token DESC"))


@app.get("/api/bills/<oid>")
def bill(oid):
    o = rows("SELECT * FROM orders WHERE id=?", (oid,))
    if not o:
        return err("Bill not found", 404)
    o[0]["items"] = rows("SELECT * FROM order_items WHERE order_id=?", (oid,))
    return jsonify(o[0])


@app.post("/api/orders")
def create_order():
    req = request.get_json(silent=True) or {}
    name = str(req.get("name", "")).strip()
    typ = str(req.get("type", "regular"))
    if not name:
        return err("Customer name is required")
    items = req.get("items")
    if not isinstance(items, list) or not items:
        return err("Cart is empty")
    qty = {}
    try:
        for it in items:
            q = int(it["qty"])
            if q <= 0:
                return err("Quantity must be positive")
            pid = int(it["id"])
            qty[pid] = qty.get(pid, 0) + q
    except (KeyError, TypeError, ValueError):
        return err("Invalid cart items")

    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")  # lock so tokens/stock can't race
        resolved, subtotal = [], 0.0
        for pid, q in qty.items():
            p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            if p is None:
                conn.rollback()
                return err(f"Unknown product ID {pid}")
            if q > p["stock"]:
                conn.rollback()
                return err(f"Insufficient stock for {p['name']}")
            subtotal += p["price"] * q
            r = dict(p)
            r["qty"] = q
            resolved.append(r)
        rate = 0.05 if typ.lower() == "member" else 0.0
        discount = subtotal * rate
        gst = (subtotal - discount) * 0.05
        total = subtotal - discount + gst
        token = conn.execute("SELECT COALESCE(MAX(token),0)+1 FROM orders").fetchone()[0]
        oid, created = f"ORD{token}", datetime.now().isoformat()
        conn.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?)",
                     (oid, token, name, typ, subtotal, discount, gst, total, created))
        for p in resolved:
            conn.execute("INSERT INTO order_items VALUES(?,?,?,?,?)",
                         (oid, p["id"], p["name"], p["price"], p["qty"]))
            conn.execute("UPDATE products SET stock=stock-?,sold=sold+? WHERE id=?",
                         (p["qty"], p["qty"], p["id"]))
        conn.commit()
        return jsonify(id=oid, token=token, name=name, type=typ, items=resolved,
                       subtotal=subtotal, discount=discount, gst=gst, total=total,
                       created_at=created)
    except Exception as e:
        conn.rollback()
        return err(str(e) or "Could not process order")
    finally:
        conn.close()


@app.get("/api/report")
def report():
    r = rows("SELECT COUNT(*) n, COALESCE(SUM(total),0) rev FROM orders")[0]
    pop = rows("SELECT name,sold FROM products ORDER BY sold DESC LIMIT 1")
    return jsonify(orders=r["n"], revenue=r["rev"], popular=pop[0] if pop else {},
                   products=rows("SELECT * FROM products ORDER BY id"))


@app.get("/api/report/full")
def full_report():
    return jsonify(
        daily=rows("SELECT substr(created_at,1,10) day,COUNT(*) orders,COALESCE(SUM(total),0) revenue FROM orders GROUP BY day ORDER BY day"),
        top=rows("SELECT name,SUM(quantity) units FROM order_items GROUP BY product_id,name ORDER BY units DESC LIMIT 10"),
        stockValue=rows("SELECT COALESCE(SUM(price*stock),0) v FROM products")[0]["v"],
        average=rows("SELECT COALESCE(AVG(total),0) a FROM orders")[0]["a"])


@app.get("/api/reviews")
def reviews():
    return jsonify(rows("SELECT * FROM reviews ORDER BY created_at DESC"))


@app.post("/api/reviews")
def add_review():
    req = request.get_json(silent=True) or {}
    name, comment = str(req.get("name", "")).strip(), str(req.get("comment", "")).strip()
    try:
        rating = int(req.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0
    if not name or not comment or not 1 <= rating <= 5:
        return err("Name, comment and rating from 1 to 5 are required")
    with db() as c:
        c.execute("INSERT INTO reviews(name,rating,comment,created_at) VALUES(?,?,?,?)",
                  (name, rating, comment, datetime.now().isoformat()))
    return jsonify(success=True)


init_db()
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
