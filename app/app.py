
import os, json, hashlib, time
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")

UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_IMAGE_EXTENSIONS = {"png","jpg","jpeg","webp","gif"}
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SADSOD_SECRET", "change-me-please")
# Use DATABASE_URL if provided (Render/Postgres), otherwise local SQLite
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url or ("sqlite:///" + os.path.join(os.path.dirname(BASE_DIR), "sadsod.db"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

ORDER_STATUSES = [
  ("new","جديد"),
  ("confirmed","مؤكد"),
  ("preparing","قيد التحضير"),
  ("shipped","تم الشحن"),
  ("delivered","تم التسليم"),
  ("cancelled","ملغي"),
  ("returned","راجع"),
]

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def allowed_image_file(filename: str) -> bool:
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS

def save_image_upload(file_storage):
    """Save an uploaded image into /static/uploads and return a public URL path.
    Returns None if no file is provided.
    """
    if not file_storage or not getattr(file_storage, 'filename', ''):
        return None
    filename = secure_filename(file_storage.filename)
    if not allowed_image_file(filename):
        return None
    # unique name: timestamp + random hash
    ext = filename.rsplit('.', 1)[1].lower()
    unique = hashlib.sha1(f"{filename}-{time.time()}".encode('utf-8')).hexdigest()[:12]
    new_name = f"p_{int(time.time())}_{unique}.{ext}"
    save_path = os.path.join(UPLOAD_DIR, new_name)
    file_storage.save(save_path)
    return f"/static/uploads/{new_name}"

class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    slug = db.Column(db.String(160), unique=True, nullable=False)
    category = db.Column(db.String(80), nullable=False, default="نسائي")
    price = db.Column(db.Integer, nullable=False, default=0)
    old_price = db.Column(db.Integer, nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    description = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(255), nullable=True)  # static path or URL
    is_featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ShippingRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wilaya = db.Column(db.String(80), nullable=False)
    daira = db.Column(db.String(120), nullable=True)
    price = db.Column(db.Integer, nullable=False, default=0)
    eta = db.Column(db.String(80), nullable=True)

class Daira(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wilaya = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(120), nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(20), unique=True, nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    wilaya = db.Column(db.String(80), nullable=False)
    daira = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(250), nullable=False)
    notes = db.Column(db.String(250), nullable=True)
    delivery_price = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(20), nullable=False, default="new")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    product_name = db.Column(db.String(140), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)
    price = db.Column(db.Integer, nullable=False, default=0)

def get_cart():
    return session.get("cart", {})

def cart_count():
    return sum(int(v) for v in get_cart().values())

def cart_items():
    cart = get_cart()
    if not cart:
        return []
    ids = [int(k) for k in cart.keys()]
    products = Product.query.filter(Product.id.in_(ids)).all()
    by_id = {p.id: p for p in products}
    out = []
    for k, v in cart.items():
        pid = int(k)
        if pid in by_id:
            p = by_id[pid]
            qty = int(v)
            out.append({"product": p, "qty": qty, "line_total": qty * p.price})
    return out

def cart_subtotal():
    return sum(i["line_total"] for i in cart_items())

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def gen_order_no():
    # SADSOD-YYMMDD-XXXX
    today = datetime.utcnow().strftime("%y%m%d")
    base = f"SADSOD-{today}-"
    n = Order.query.filter(Order.order_no.like(base + "%")).count() + 1
    return base + str(n).zfill(4)

@app.context_processor
def inject_globals():
    return dict(cart_count=cart_count(), year=datetime.utcnow().year)

@app.get("/")
def home():
    featured = Product.query.filter_by(is_featured=True).order_by(Product.created_at.desc()).limit(8).all()
    latest = Product.query.order_by(Product.created_at.desc()).limit(8).all()
    return render_template("home.html", featured=featured, latest=latest)

@app.get("/shop")
def shop():
    q = request.args.get("q", "").strip()
    cat = request.args.get("cat", "").strip()
    query = Product.query
    if q:
        query = query.filter(Product.name.contains(q))
    if cat:
        query = query.filter_by(category=cat)
    products = query.order_by(Product.created_at.desc()).all()
    cats = [c[0] for c in db.session.query(Product.category).distinct().all()]
    return render_template("shop.html", products=products, q=q, cat=cat, cats=cats)

@app.get("/product/<slug>")
def product(slug):
    p = Product.query.filter_by(slug=slug).first_or_404()
    return render_template("product.html", p=p)

@app.post("/cart/add/<int:pid>")
def cart_add(pid):
    p = Product.query.get_or_404(pid)
    cart = get_cart()
    cart[str(pid)] = int(cart.get(str(pid), 0)) + 1
    session["cart"] = cart
    flash("تمت إضافة المنتج إلى السلة ✅", "ok")
    return redirect(request.referrer or url_for("shop"))

@app.post("/cart/update")
def cart_update():
    cart = {}
    for k, v in request.form.items():
        if not k.startswith("qty_"): 
            continue
        pid = k.replace("qty_", "")
        try:
            qty = max(0, int(v))
        except:
            qty = 0
        if qty > 0:
            cart[pid] = qty
    session["cart"] = cart
    flash("تم تحديث السلة ✅", "ok")
    return redirect(url_for("cart"))

@app.get("/cart")
def cart():
    items = cart_items()
    subtotal = cart_subtotal()
    return render_template("cart.html", items=items, subtotal=subtotal)

def compute_delivery_price(wilaya, daira):
    # exact match wilaya+daira, then wilaya only
    if daira:
        r = ShippingRate.query.filter_by(wilaya=wilaya, daira=daira).first()
        if r:
            return r.price
    r = ShippingRate.query.filter_by(wilaya=wilaya, daira=None).first()
    return r.price if r else 0

@app.get("/checkout")
def checkout():
    if cart_count() == 0:
        flash("السلة فارغة. أضف منتجات أولاً.", "warn")
        return redirect(url_for("shop"))
    with open(os.path.join(DATA_DIR, "wilayas.json"), "r", encoding="utf-8") as f:
        wilayas = json.load(f)
    return render_template("checkout.html", wilayas=wilayas)

@app.post("/checkout")
def checkout_post():
    if cart_count() == 0:
        flash("السلة فارغة.", "warn")
        return redirect(url_for("shop"))

    name = request.form.get("name","").strip()
    phone = request.form.get("phone","").strip()
    wilaya = request.form.get("wilaya","").strip()
    daira = request.form.get("daira_select","").strip() or request.form.get("daira","").strip()
    address = request.form.get("address","").strip()
    notes = request.form.get("notes","").strip()

    if not (name and phone and wilaya and address):
        flash("رجاءً املأ المعلومات الأساسية.", "warn")
        return redirect(url_for("checkout"))

    delivery = compute_delivery_price(wilaya, daira if daira else None)
    subtotal = cart_subtotal()
    total = subtotal + delivery

    order = Order(
        order_no=gen_order_no(),
        customer_name=name,
        phone=phone,
        wilaya=wilaya,
        daira=daira if daira else None,
        address=address,
        notes=notes if notes else None,
        delivery_price=delivery,
        total=total,
        status="new",
    )
    db.session.add(order)
    db.session.flush()

    for i in cart_items():
        p = i["product"]
        qty = i["qty"]
        item = OrderItem(order_id=order.id, product_id=p.id, product_name=p.name, qty=qty, price=p.price)
        db.session.add(item)
        # reduce stock (best-effort)
        if p.stock is not None:
            p.stock = max(0, (p.stock or 0) - qty)

    db.session.commit()
    session["cart"] = {}
    return redirect(url_for("checkout_success", order_no=order.order_no))

@app.get("/success/<order_no>")
def checkout_success(order_no):
    order = Order.query.filter_by(order_no=order_no).first_or_404()
    return render_template("success.html", order=order)

@app.get("/track")
def track():
    return render_template("track.html")

@app.get("/track/result")
def track_result():
    order_no = request.args.get("order_no","").strip()
    phone = request.args.get("phone","").strip()
    if not (order_no and phone):
        flash("أدخل رقم الطلب والهاتف.", "warn")
        return redirect(url_for("track"))
    order = Order.query.filter_by(order_no=order_no, phone=phone).first()
    if not order:
        flash("لم نجد طلباً بهذه المعلومات.", "warn")
        return redirect(url_for("track"))
    items = OrderItem.query.filter_by(order_id=order.id).all()
    status_map = dict(ORDER_STATUSES)
    return render_template("track_result.html", order=order, items=items, status_label=status_map.get(order.status, order.status))

# APIs
@app.get("/api/wilayas")
def api_wilayas():
    with open(os.path.join(DATA_DIR, "wilayas.json"), "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.get("/api/dairas")
def api_dairas():
    wilaya = request.args.get("wilaya","").strip()
    if not wilaya:
        return jsonify([])
    rows = Daira.query.filter_by(wilaya=wilaya).order_by(Daira.name.asc()).all()
    return jsonify([r.name for r in rows])

# Admin
@app.get("/admin/login")
def admin_login():
    return render_template("admin/login.html")

@app.post("/admin/login")
def admin_login_post():
    username = request.form.get("username","").strip()
    password = request.form.get("password","").strip()
    u = AdminUser.query.filter_by(username=username).first()
    if not u or u.password_hash != hash_password(password):
        flash("بيانات الدخول غير صحيحة.", "warn")
        return redirect(url_for("admin_login"))
    session["admin"] = True
    return redirect(url_for("admin_dashboard"))

@app.get("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("home"))

@app.get("/admin")
@admin_required
def admin_dashboard():
    today = datetime.utcnow().date()
    orders_today = Order.query.filter(func.date(Order.created_at)==today).count()
    revenue_today = db.session.query(func.sum(Order.total)).filter(func.date(Order.created_at)==today).scalar() or 0
    total_orders = Order.query.count()
    total_products = Product.query.count()
    recent = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    return render_template("admin/dashboard.html",
        orders_today=orders_today, revenue_today=revenue_today,
        total_orders=total_orders, total_products=total_products,
        recent=recent, statuses=ORDER_STATUSES)

@app.get("/admin/products")
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin/products.html", products=products)

@app.route("/admin/products/new", methods=["GET","POST"])
@admin_required
def admin_products_new():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        slug = request.form.get("slug","").strip()
        category = request.form.get("category","").strip() or "نسائي"
        price = int(request.form.get("price","0") or 0)
        old_price = request.form.get("old_price","").strip()
        old_price = int(old_price) if old_price else None
        stock = int(request.form.get("stock","0") or 0)
        image = request.form.get("image","").strip() or None
        # Optional: upload an image file from the admin panel
        file_obj = request.files.get("image_file")
        if file_obj and getattr(file_obj, "filename", ""):
            uploaded_url = save_image_upload(file_obj)
            if not uploaded_url:
                flash("صيغة الصورة غير مدعومة. استعمل PNG/JPG/JPEG/WEBP/GIF.", "warn")
                return redirect(url_for("admin_products_new"))
            image = uploaded_url
        desc = request.form.get("description","").strip() or None
        is_featured = True if request.form.get("is_featured") else False
        if not (name and slug):
            flash("الاسم والـ slug ضروريان.", "warn")
            return redirect(url_for("admin_products_new"))
        if Product.query.filter_by(slug=slug).first():
            flash("Slug موجود مسبقاً.", "warn")
            return redirect(url_for("admin_products_new"))
        p = Product(name=name, slug=slug, category=category, price=price, old_price=old_price, stock=stock, image=image, description=desc, is_featured=is_featured)
        db.session.add(p); db.session.commit()
        flash("تم إضافة المنتج ✅", "ok")
        return redirect(url_for("admin_products"))
    return render_template("admin/product_form.html", mode="new", p=None)

@app.route("/admin/products/<int:pid>/edit", methods=["GET","POST"])
@admin_required
def admin_products_edit(pid):
    p = Product.query.get_or_404(pid)
    if request.method == "POST":
        p.name = request.form.get("name","").strip()
        p.slug = request.form.get("slug","").strip()
        p.category = request.form.get("category","").strip() or "نسائي"
        p.price = int(request.form.get("price","0") or 0)
        old_price = request.form.get("old_price","").strip()
        p.old_price = int(old_price) if old_price else None
        p.stock = int(request.form.get("stock","0") or 0)
        p.image = request.form.get("image","").strip() or None
        # Optional: replace image with uploaded file
        file_obj = request.files.get("image_file")
        if file_obj and getattr(file_obj, "filename", ""):
            uploaded_url = save_image_upload(file_obj)
            if not uploaded_url:
                flash("صيغة الصورة غير مدعومة. استعمل PNG/JPG/JPEG/WEBP/GIF.", "warn")
                return redirect(url_for("admin_products_edit", pid=pid))
            p.image = uploaded_url
        p.description = request.form.get("description","").strip() or None
        p.is_featured = True if request.form.get("is_featured") else False
        db.session.commit()
        flash("تم حفظ التغييرات ✅", "ok")
        return redirect(url_for("admin_products"))
    return render_template("admin/product_form.html", mode="edit", p=p)

@app.post("/admin/products/<int:pid>/delete")
@admin_required
def admin_products_delete(pid):
    p = Product.query.get_or_404(pid)
    db.session.delete(p); db.session.commit()
    flash("تم حذف المنتج.", "ok")
    return redirect(url_for("admin_products"))

@app.get("/admin/orders")
@admin_required
def admin_orders():
    status = request.args.get("status","").strip()
    wilaya = request.args.get("wilaya","").strip()
    q = Order.query
    if status:
        q = q.filter_by(status=status)
    if wilaya:
        q = q.filter_by(wilaya=wilaya)
    orders = q.order_by(Order.created_at.desc()).all()
    with open(os.path.join(DATA_DIR, "wilayas.json"), "r", encoding="utf-8") as f:
        wilayas = json.load(f)
    return render_template("admin/orders.html", orders=orders, statuses=ORDER_STATUSES, wilayas=wilayas, status=status, wilaya=wilaya)

@app.route("/admin/orders/<int:oid>", methods=["GET","POST"])
@admin_required
def admin_order_view(oid):
    order = Order.query.get_or_404(oid)
    items = OrderItem.query.filter_by(order_id=order.id).all()
    if request.method == "POST":
        st = request.form.get("status","").strip()
        if st in [s for s,_ in ORDER_STATUSES]:
            order.status = st
            db.session.commit()
            flash("تم تحديث الحالة ✅", "ok")
        return redirect(url_for("admin_order_view", oid=oid))
    return render_template("admin/order_view.html", order=order, items=items, statuses=ORDER_STATUSES)

@app.get("/admin/shipping")
@admin_required
def admin_shipping():
    rates = ShippingRate.query.order_by(ShippingRate.wilaya.asc(), ShippingRate.daira.asc()).all()
    with open(os.path.join(DATA_DIR, "wilayas.json"), "r", encoding="utf-8") as f:
        wilayas = json.load(f)
    return render_template("admin/shipping.html", rates=rates, wilayas=wilayas)

@app.post("/admin/shipping/add")
@admin_required
def admin_shipping_add():
    wilaya = request.form.get("wilaya","").strip()
    daira = request.form.get("daira","").strip() or None
    price = int(request.form.get("price","0") or 0)
    eta = request.form.get("eta","").strip() or None
    if not wilaya:
        flash("اختر الولاية.", "warn"); return redirect(url_for("admin_shipping"))
    r = ShippingRate(wilaya=wilaya, daira=daira, price=price, eta=eta)
    db.session.add(r); db.session.commit()
    flash("تمت إضافة سعر توصيل ✅", "ok")
    return redirect(url_for("admin_shipping"))

@app.post("/admin/shipping/<int:rid>/delete")
@admin_required
def admin_shipping_delete(rid):
    r = ShippingRate.query.get_or_404(rid)
    db.session.delete(r); db.session.commit()
    flash("تم الحذف.", "ok")
    return redirect(url_for("admin_shipping"))

@app.get("/admin/dairas")
@admin_required
def admin_dairas():
    with open(os.path.join(DATA_DIR, "wilayas.json"), "r", encoding="utf-8") as f:
        wilayas = json.load(f)
    dairas = Daira.query.order_by(Daira.wilaya.asc(), Daira.name.asc()).all()
    return render_template("admin/dairas.html", wilayas=wilayas, dairas=dairas)

@app.post("/admin/dairas/add")
@admin_required
def admin_dairas_add():
    wilaya = request.form.get("wilaya","").strip()
    name = request.form.get("name","").strip()
    if not (wilaya and name):
        flash("اختر الولاية واسم الدائرة.", "warn")
        return redirect(url_for("admin_dairas"))
    db.session.add(Daira(wilaya=wilaya, name=name))
    db.session.commit()
    flash("تمت إضافة الدائرة ✅", "ok")
    return redirect(url_for("admin_dairas"))

@app.post("/admin/dairas/<int:did>/delete")
@admin_required
def admin_dairas_delete(did):
    d = Daira.query.get_or_404(did)
    db.session.delete(d); db.session.commit()
    flash("تم الحذف.", "ok")
    return redirect(url_for("admin_dairas"))

def seed():
    # Create default admin and demo products if empty
    if AdminUser.query.count() == 0:
        db.session.add(AdminUser(username="admin", password_hash=hash_password("admin123")))
    if Product.query.count() == 0:
        demo = [
          dict(name="حذاء نسائي جلد طبيعي - Sadsod 01", slug="sadsod-01", category="نسائي", price=4800, old_price=5600, stock=12, is_featured=True),
          dict(name="حذاء نسائي بكعب أنيق - Sadsod 02", slug="sadsod-02", category="نسائي", price=5200, old_price=None, stock=8, is_featured=True),
          dict(name="بابوش تقليدي جلد - Sadsod 03", slug="sadsod-03", category="تقليدي", price=3900, old_price=4500, stock=20, is_featured=False),
          dict(name="حذاء رجالي جلد - Sadsod 04", slug="sadsod-04", category="رجالي", price=6100, old_price=6900, stock=6, is_featured=True),
        ]
        for d in demo:
            db.session.add(Product(**d, description="منتج مصنوع بعناية يعكس الأناقة واللمسة الجزائرية التقليدية."))
    # Default shipping base: set a generic price per wilaya if empty
    if ShippingRate.query.count() == 0:
        with open(os.path.join(DATA_DIR, "wilayas.json"), "r", encoding="utf-8") as f:
            wilayas = json.load(f)
        for w in wilayas:
            db.session.add(ShippingRate(wilaya=w, daira=None, price=600, eta="24-72 ساعة"))
    db.session.commit()

_DB_INITIALIZED = False


@app.before_request
def init_db_once():
    """Initialize the database on the first incoming request.

    Flask 3 removed `before_first_request`, so we do a safe one-time init here.
    """
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    with app.app_context():
        db.create_all()
        seed()
    _DB_INITIALIZED = True

if __name__ == "__main__":
    # Local dev only. Render/Gunicorn will run the WSGI app via `wsgi.py`.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=True)
