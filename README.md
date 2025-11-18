# 🏢 HydePark Local Server - Face Recognition Sync System

> نظام محلي للمزامنة بين التطبيق الأونلاين و HikCentral Professional مع كشف تكرار الوجوه

---

## 📋 نظرة عامة

هذا النظام يعمل كهمزة وصل بين:
1. **التطبيق الأونلاين** (Supabase API) - حيث يتم إضافة بيانات العمال
2. **HikCentral Professional** - نظام التحكم في الدخول المحلي

### 🎯 المهام الرئيسية:
- ✅ جلب بيانات العمال الجدد من API كل دقيقة
- ✅ تحميل وحفظ صور البطاقات والوجوه محلياً
- ✅ كشف تكرار الوجوه باستخدام Face Recognition
- ✅ منع إضافة عمال محظورين أو مكررين
- ✅ إضافة/تحديث العمال في HikCentral تلقائياً
- ✅ تحديث حالة العمال في النظام الأونلاين

---

## 🚀 التثبيت السريع على Ubuntu

### المتطلبات:
- Ubuntu 18.04 أو أحدث
- Python 3.8 أو أحدث
- اتصال بالإنترنت
- صلاحيات sudo

### خطوات التثبيت:

```bash
# 1. حمّل المشروع
cd /home/your-username
# رفع الملفات أو استخدام git clone

# 2. اجعل السكريبت قابل للتنفيذ
chmod +x deploy.sh

# 3. شغّل سكريبت التثبيت
./deploy.sh
```

السكريبت سيقوم بـ:
- تحديث النظام
- تثبيت Python و dependencies
- إنشاء virtual environment
- تثبيت المكتبات المطلوبة
- إنشاء ملف .env
- (اختياري) إعداد systemd service للتشغيل التلقائي

---

## ⚙️ الإعداد

### 1. تعديل ملف .env

بعد تشغيل `deploy.sh`، عدّل ملف `.env` بالبيانات الصحيحة:

```bash
nano .env
```

```env
# Supabase API Configuration
SUPABASE_URL=https://xrkxxqhoglrimiljfnml.supabase.co/functions/v1/make-server-2c3121a9
SUPABASE_BEARER_TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhya3h4cWhvZ2xyaW1pbGpmbm1sIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI0MjIxMDEsImV4cCI6MjA3Nzk5ODEwMX0.3G20OL9ujCPyFOOMYc6UVbIv97v5LjsWbQLPZaqHRsk
SUPABASE_API_KEY=XyZ9k2LmN4pQ7rS8tU0vW1xA3bC5dE6f7gH8iJ9kL0mN1o==

# HikCentral Configuration
HIKCENTRAL_BASE_URL=https://10.127.0.2/artemis
HIKCENTRAL_APP_KEY=22452825
HIKCENTRAL_APP_SECRET=Q9bWogAziordVdIngfoa
HIKCENTRAL_PRIVILEGE_GROUP_ID=3

# Face Recognition Settings
FACE_MATCH_THRESHOLD=0.6

# Sync Settings
SYNC_INTERVAL_SECONDS=60

# SSL Verification
VERIFY_SSL=False
```

**احفظ الملف**: `Ctrl+X` ثم `Y` ثم `Enter`

---

## 🎮 التشغيل

### تشغيل يدوي (للاختبار):

```bash
# 1. تفعيل virtual environment
source venv/bin/activate

# 2. تشغيل البرنامج
python3 main.py

# 3. إيقاف البرنامج
# اضغط Ctrl+C
```

### تشغيل تلقائي (Systemd Service):

إذا لم تقم بإعداد الـ service أثناء التثبيت:

```bash
# إعداد systemd service
chmod +x setup_service.sh
./setup_service.sh
```

#### أوامر إدارة الـ Service:

```bash
# عرض حالة Service
sudo systemctl status hydepark-sync

# إيقاف مؤقت
sudo systemctl stop hydepark-sync

# تشغيل
sudo systemctl start hydepark-sync

# إعادة تشغيل
sudo systemctl restart hydepark-sync

# عرض الـ Logs مباشرة
sudo journalctl -u hydepark-sync -f

# عرض آخر 100 سطر من الـ logs
sudo journalctl -u hydepark-sync -n 100

# تعطيل التشغيل التلقائي
sudo systemctl disable hydepark-sync

# تفعيل التشغيل التلقائي
sudo systemctl enable hydepark-sync
```

---

## 📂 هيكل المشروع

```
hydepark-local-server/
├── main.py                 # التطبيق الرئيسي
├── requirements.txt        # المكتبات المطلوبة
├── .env                    # الإعدادات (لا ترفعه على Git)
├── .env.example           # مثال للإعدادات
├── deploy.sh              # سكريبت التثبيت
├── setup_service.sh       # إعداد systemd service
├── README.md              # هذا الملف
│
├── venv/                  # Virtual environment (يُنشأ تلقائياً)
│
├── images/                # الصور المحفوظة (يُنشأ تلقائياً)
│   ├── id_cards/         # صور البطاقات
│   └── faces/            # صور الوجوه
│
└── workers_data.json      # قاعدة البيانات المحلية (يُنشأ تلقائياً)
```

---

## 🔄 سير العمل (Workflow)

### 1. جلب البيانات (كل دقيقة)
```
[Supabase API] → جلب العمال الجدد + المحظورين + Pending
```

### 2. معالجة كل عامل
```
تحميل الصور → استخراج Face Encoding → فحص التكرار
     ↓
  مكرر؟
     ↓
    نعم → محظور سابقاً؟ → رفض وإبلاغ API
     │           ↓
     │          لا → تحديث البيانات في HikCentral
     ↓
    لا → إضافة جديد في HikCentral → حفظ محلياً → تحديث API
```

### 3. العمال المحظورين
```
[Supabase API] → عامل محظور → حذف من HikCentral → تحديث محلياً
```

---

## 🔍 كشف التكرار

النظام يستخدم **Face Recognition** لكشف الوجوه المكررة:

- **Threshold**: 0.6 (60% تشابه) - قابل للتعديل في `.env`
- **الخوارزمية**: face_recognition library (dlib)
- **المقارنة**: يتم مقارنة كل وجه جديد مع جميع الوجوه المحفوظة محلياً

### سيناريوهات التكرار:

1. **وجه مكرر + محظور** → رفض فوراً
2. **وجه مكرر + غير محظور** → تحديث البيانات فقط
3. **وجه جديد** → إضافة للنظام

---

## 📊 المتابعة والـ Logs

### عرض Logs مباشرة:

```bash
# Logs من systemd
sudo journalctl -u hydepark-sync -f

# تصفية حسب الوقت
sudo journalctl -u hydepark-sync --since "1 hour ago"
sudo journalctl -u hydepark-sync --since "today"

# حفظ الـ logs لملف
sudo journalctl -u hydepark-sync > logs.txt
```

### فهم الـ Output:

```
[Supabase] Fetching workers...           # جلب البيانات
[Supabase] Fetched 5 workers            # عدد العمال
[Worker] Processing: أحمد محمد         # معالجة عامل
[Image] Downloading...                   # تحميل صورة
[Face] Face detected                     # اكتشاف وجه
[Face] Comparing with 10 faces...       # المقارنة
[Face] No match found                    # لا يوجد تطابق
[HikCentral] POST /api/...              # إضافة لـ HikCentral
[HikCentral] Success                     # نجح
[Worker] ✓ Successfully processed       # تم بنجاح
```

---

## ⚠️ استكشاف الأخطاء

### مشكلة: "No face detected"
**السبب**: الصورة لا تحتوي على وجه واضح أو الجودة منخفضة

**الحل**:
- تأكد من جودة الصور المرفوعة
- قد يحتاج العامل لرفع صورة جديدة أوضح

---

### مشكلة: HikCentral API يرجع خطأ
**الأسباب المحتملة**:
1. بيانات المصادقة غير صحيحة
2. HikCentral Server غير متاح
3. مشكلة في الشبكة

**الحل**:
```bash
# تحقق من الاتصال
ping 10.127.0.2

# تحقق من بيانات المصادقة في .env
cat .env | grep HIKCENTRAL

# تحقق من الـ logs
sudo journalctl -u hydepark-sync -n 50
```

---

### مشكلة: "Failed to download image"
**السبب**: رابط الصورة منتهي أو الإنترنت غير متاح

**الحل**:
- تحقق من اتصال الإنترنت
- روابط الصور من Supabase signed URLs لها مدة صلاحية
- النظام سيحاول مجدداً في المزامنة القادمة

---

### مشكلة: Service لا يعمل بعد إعادة التشغيل

```bash
# تحقق من حالة الـ service
sudo systemctl status hydepark-sync

# إذا كان معطل:
sudo systemctl enable hydepark-sync
sudo systemctl start hydepark-sync

# عرض آخر الأخطاء
sudo journalctl -u hydepark-sync -n 50 --no-pager
```

---

## 🔧 الإعدادات المتقدمة

### تغيير معدل المزامنة:

في ملف `.env`:
```env
SYNC_INTERVAL_SECONDS=120  # كل دقيقتين بدلاً من دقيقة
```

ثم:
```bash
sudo systemctl restart hydepark-sync
```

### تغيير Face Match Threshold:

```env
FACE_MATCH_THRESHOLD=0.7  # زيادة الدقة (70% تشابه)
```

**ملاحظة**: كلما زاد الـ threshold، كلما قلت حساسية كشف التكرار

---

## 🔒 الأمان

### حماية ملف .env:

```bash
# تأكد من الصلاحيات الصحيحة
chmod 600 .env
```

### الـ Credentials:
- **لا ترفع** ملف `.env` على Git أبداً
- غيّر المفاتيح بشكل دوري
- استخدم مستخدم محدود الصلاحيات لتشغيل الـ service

---

## 📱 التواصل مع APIs

### Supabase API:
- **Endpoint**: `/admin/workers/all-data`
- **Authentication**: Bearer Token + API Key
- **Rate Limit**: 100 req/15min

### HikCentral API:
- **Authentication**: AK/SK (APPkey + APPsecret)
- **SSL**: Self-signed certificate (يتم تعطيل التحقق)

---

## 🆘 الدعم والمساعدة

### التحقق من صحة التثبيت:

```bash
# 1. تحقق من Python
python3 --version

# 2. تحقق من المكتبات
source venv/bin/activate
pip list | grep face-recognition

# 3. اختبار الاتصال بـ Supabase
curl -H "X-API-Key: YOUR_KEY" https://xrkxxqhoglrimiljfnml.supabase.co/functions/v1/make-server-2c3121a9/admin/workers/all-data

# 4. اختبار الاتصال بـ HikCentral
ping 10.127.0.2
```

### معلومات النظام:

```bash
# معلومات Ubuntu
lsb_release -a

# معلومات Python
python3 --version

# معلومات الذاكرة
free -h

# مساحة القرص
df -h
```

---

## 📝 الترخيص

هذا المشروع ملك لـ Smart Stations Solutions

---

## 🎉 تم بنجاح!

النظام الآن يعمل ويقوم بـ:
- ✅ المزامنة التلقائية كل دقيقة
- ✅ كشف الوجوه المكررة
- ✅ الإضافة التلقائية لـ HikCentral
- ✅ التحديث التلقائي للحالات

**للمتابعة المباشرة:**
```bash
sudo journalctl -u hydepark-sync -f
```

---

**تم بناؤه بواسطة**: Smart Stations Solutions  
**التاريخ**: نوفمبر 2025  
**النسخة**: 1.0.0 (Proof of Concept)
