# Sadsod Shoes — متجر أحذية (عربي / الجزائر / دفع عند الاستلام)

## التشغيل بسرعة
1) ثبّت بايثون 3.10+  
2) داخل المجلد:
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

pip install -r requirements.txt
python app/app.py
```

افتح:
- المتجر: http://127.0.0.1:5000
- لوحة التحكم: http://127.0.0.1:5000/admin

## بيانات دخول لوحة التحكم
- المستخدم: admin
- كلمة السر: admin123

## ملاحظات مهمة
- الدفع: عند الاستلام فقط ✅
- الجزائر فقط ✅
- اختيار الولاية جاهز (69 ولاية)
- الدوائر: قابلة للإضافة من لوحة التحكم (قسم الدوائر)، وبعدها تظهر تلقائياً في Checkout.
- أسعار التوصيل: قابلة للتحكم من لوحة التحكم (قسم الشحن)

## أين أغيّر الشعار والصور؟
- app/static/img/logo_round.png
- app/static/img/hero_shoes.png
