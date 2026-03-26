# نظام الكاشير - POS System

نظام كاشير كامل مبني بـ Django + SQLite مصمم لجهاز كاشير واحد متوصل بـ 3 طابعات.

---

## 📁 هيكل المشروع

```
pos_system/
├── pos_system/          ← إعدادات Django (settings, urls, wsgi)
├── pos/                 ← التطبيق الرئيسي
│   ├── models.py        ← Category, MenuItem, Table, Order, OrderItem
│   ├── views.py         ← كل الـ views
│   ├── urls.py          ← الـ routes
│   ├── admin.py         ← لوحة الإدارة
│   └── fixtures/        ← بيانات تجريبية
├── templates/pos/       ← كل الشاشات
│   ├── base.html        ← القالب الأساسي (sidebar + layout)
│   ├── login.html       ← شاشة الدخول
│   ├── dashboard.html   ← الرئيسية
│   ├── new_order.html   ← شاشة الطلب الجديد (POS)
│   ├── orders_list.html ← قائمة الطلبات
│   ├── order_detail.html← تفاصيل طلب
│   └── reports.html     ← التقارير
├── print_service/
│   └── print_service.py ← Flask server للطباعة
├── manage.py
├── requirements.txt
├── setup.bat            ← إعداد أول مرة
├── start.bat            ← تشغيل السيستم
└── backup.bat           ← نسخ احتياطي
```

---

## 🚀 إعداد وتشغيل (أول مرة)

### 1. تأكد إن Python مثبت
```
python --version   ← لازم 3.10 أو أحدث
```

### 2. شغّل setup.bat
```
setup.bat
```
ده هيعمل:
- بيئة افتراضية (venv)
- تثبيت المكتبات
- إنشاء قاعدة البيانات
- إنشاء حساب المدير

### 3. حمّل البيانات التجريبية (اختياري)
```
python manage.py loaddata pos/fixtures/initial_data.json
```
هيضيف: 3 تصنيفات + 10 منتجات + 6 طاولات

### 4. شغّل السيستم
```
start.bat
```

### 5. افتح المتصفح
```
http://localhost:8000
```

---

## 🖨️ إعداد الطابعات

### في Windows:
افتح: `الإعدادات → Bluetooth والأجهزة → الطابعات والماسحات الضوئية`

اعطي الطابعات الأسماء دي بالظبط:
- `Main Printer`    ← طابعة الكاشير (فاتورة كاملة)
- `Kitchen Printer` ← طابعة المطبخ
- `Bar Printer`     ← طابعة البار

### تحقق من الطابعات:
بعد تشغيل print_service.py افتح:
```
http://127.0.0.1:5000/printers
```
هيظهرلك كل الطابعات المتاحة.

---

## 🔗 الصفحات

| الصفحة | الرابط |
|--------|--------|
| الرئيسية | `http://localhost:8000/` |
| طلب جديد | `http://localhost:8000/order/new/` |
| الطلبات | `http://localhost:8000/orders/` |
| التقارير | `http://localhost:8000/reports/` |
| لوحة الإدارة | `http://localhost:8000/admin/` |

---

## ⚙️ الإعدادات المهمة في settings.py

```python
# URL خدمة الطباعة
PRINT_SERVICE_URL = 'http://127.0.0.1:5000/print'

# المنطقة الزمنية
TIME_ZONE = 'Africa/Cairo'
```

---

## 🔁 الـ Backup التلقائي

عشان يعمل backup يوميًا تلقائي:
1. افتح `Task Scheduler` في Windows
2. أنشئ مهمة جديدة
3. اضبطها تشغّل `backup.bat` كل يوم الفجر

---

## 📦 المكتبات المستخدمة

| المكتبة | الاستخدام |
|---------|-----------|
| Django | الـ framework الأساسي |
| Waitress | Production server بدل runserver |
| Flask | Print Service server |
| pywin32 | التحكم في طابعات Windows |
| requests | Django → Print Service |

---

## 🆕 إضافة منتجات وتصنيفات

من لوحة الإدارة: `http://localhost:8000/admin/`
- `Categories` ← ضيف تصنيف وحدد نوعه (أكل/مشروب)
- `Menu Items` ← ضيف المنتجات مع السعر
- `Tables` ← ضيف الطاولات

---

## 🐛 مشاكل شائعة

**السيستم مش بيفتح:**
```
netstat -an | find "8000"   ← تحقق إن البورت مش محجوز
```

**الطباعة مش شغالة:**
- تأكد إن print_service.py شغّال
- تأكد من اسم الطابعة في Windows
- افتح `http://127.0.0.1:5000/health`

**قاعدة البيانات فيها مشكلة:**
```
python manage.py migrate
```
