# 🏢 HydePark Local Server - Simple Sync System

## نظرة عامة
- مزامنة ذكية بين Supabase و HikCentral لإضافة/تحديث/حذف الأشخاص تلقائياً.
- إدارة حالات العمال الجديدة والموقوفين (Blocked) مع منطق تجنّب العمليات المتكررة.
- تشغيل إنتاجي مستمر بخدمة systemd عبر سكريبت `deploy.sh`.

## المزايا
- إضافة شخص جديد مع صورة الوجه وتعيينه لمجموعة صلاحيات.
- تحديث شخص موجود ودمج فترات الصلاحية بأخذ الأقدم للبداية والأطول للنهاية.
- حذف شخص عند حظر العامل وتسجيل أنه تم الحذف لتجنّب إعادة المحاولة.
- سجّل محلي بسيط JSON لتتبع المعالجة وحالة الحذف في HikCentral.

## إعداد `.env`
ضع القيم التالية في ملف `.env` في جذر المشروع:

```
# Supabase
SUPABASE_URL=...
SUPABASE_BEARER_TOKEN=...
SUPABASE_API_KEY=...
SUPABASE_EVENTS_PREFIX=make-server-2c3121a9

# HikCentral
HIKCENTRAL_BASE_URL=https://<ip-or-host>/artemis
HIKCENTRAL_APP_KEY=...
HIKCENTRAL_APP_SECRET=...
HIKCENTRAL_PRIVILEGE_GROUP_ID=3
HIKCENTRAL_ORG_INDEX_CODE=<org-index-code>
HIKCENTRAL_USER_ID=admin
HIKCENTRAL_TIMEZONE_OFFSET=+02:00

# Runtime
SYNC_INTERVAL_SECONDS=60
VERIFY_SSL=False
HIKCENTRAL_DEBUG=False
HIKCENTRAL_INCLUDE_PORT_IN_URI=False
```

ملاحظات:
- `HIKCENTRAL_ORG_INDEX_CODE` يجب أن يكون IndexCode صحيح من شجرة المنظمات في HikCentral.
- لو التوقيت عندك +08:00 غيّر `HIKCENTRAL_TIMEZONE_OFFSET`.

## النشر على لينكس (إنتاج)
استخدم سكريبت `deploy.sh` لتثبيت بيئة التشغيل والخدمة:

1. جهّز ملف `.env` كما بالأعلى.
   - لو `.env` غير موجود وملف `.env.example` موجود، السكريبت سينسخه تلقائياً إلى `.env`.
2. نفّذ السكريبت كـ root:
   - `sudo bash deploy.sh`
3. تحقق من حالة الخدمة:
   - `systemctl status hydepark-sync --no-pager -l`
4. الاطلاع على السجلات:
   - `journalctl -u hydepark-sync -f`

تحديث الكود وإعادة التشغيل:
- `sudo systemctl restart hydepark-sync`

إيقاف/تشغيل الخدمة:
- إيقاف: `sudo systemctl stop hydepark-sync`
- تشغيل: `sudo systemctl start hydepark-sync`
- تفعيل على الإقلاع: `sudo systemctl enable hydepark-sync`

## التشغيل اليدوي (اختبار)
- `python3 main.py`

## استخدام Events API
- النظام الآن يعتمد Polling لـ Events:
  - يجلب الأحداث عبر `GET /{SUPABASE_EVENTS_PREFIX}/admin/events/pending?limit=100` مع رأس `X-API-Key`.
  - السيرفر يعلِّم الأحداث كـ consumed قبل الإرجاع، لذا لن تُعاد نفس الأحداث.
- المعالجة لكل نوع:
  - `worker.created` و`workers.bulk_created`: إضافة/تحديث في HikCentral.
  - `worker.blocked` و`unit.workers_blocked`: حذف مرة واحدة من HikCentral مع فلاغ محلي يمنع إعادة الحذف.
  - `worker.unblocked` و`unit.workers_unblocked`: إعادة تفعيل أو تحديث.
  - `worker.deleted` و`user.*_workers_deleted` و`worker.revoked`: حذف.
- المصادقة:
  - استخدم `SUPABASE_API_KEY` كرأس `X-API-Key`.
  - يمكن استخدام `SUPABASE_BEARER_TOKEN` لأغراض الأدمن إن لزم.

## منطق المعالجة الذكي
- جديد: إضافة الشخص في HikCentral + إضافة للمجموعة + تحديث Supabase Approved + حفظ محلي.
- موجود وغير محظور: تحديث بياناته في HikCentral مع دمج صلاحيات الزمن + تحديث Supabase + تحديث محلي.
- محظور:
  - أول مرة: حذف الشخص من HikCentral وتسجيل `hikcentral_deleted=True` في السجل المحلي.
  - المرات التالية: لا نحاول الحذف مرة أخرى؛ نحدّث الحالة محلياً وسحابياً فقط.
- إعادة التفعيل: لو العامل كان Blocked وجاء كجديد، نعدّل السجل المحلي ونضيفه مجدداً في HikCentral ونحدّث Supabase.

## تنسيقات الحقول
- الوقت: `YYYY-MM-DDTHH:mm:ss+TZ` بدون milliseconds.
- `residentRoomNo` و `residentFloorNo`: افتراضياً `1`.
- يتم إرسال `faces` مع `faceData` Base64 عند الإضافة.
- يتم تضمين رأس `userId` في الطلبات.

## مشاكل شائعة
- "Incorrect request parameter": تأكد من صحة `orgIndexCode` وصيغة الوقت.
- توقيع المصادقة: لا تغيّر ترتيب رؤوس التوقيع، واضبط `HIKCENTRAL_INCLUDE_PORT_IN_URI` حسب إعداد السيرفر.

## ملاحظات
- لا توجد حاجة لملف `requirements.txt`؛ السكريبت يُثبّت الحزم المطلوبة تلقائياً داخل `venv`.
- يفضّل تشغيل الإنتاج بخدمة systemd؛ يمكن تجهيز `pm2` عند الحاجة.

> نظام محلي للمزامنة التلقائية بين التطبيق الأونلاين و HikCentral Professional

---

## 📋 نظرة عامة

هذا النظام يعمل كهمزة وصل بين:
1. **التطبيق الأونلاين** (Supabase API) - حيث يتم إضافة بيانات العمال
2. **HikCentral Professional** - نظام التحكم في الدخول المحلي

### 🎯 المهام الرئيسية:
- ✅ جلب بيانات العمال الجدد من API كل دقيقة
- ✅ تحميل وحفظ صور البطاقات والوجوه محلياً
- ✅ إضافة العمال الجدد في HikCentral تلقائياً
- ✅ إضافة العمال لـ Privilege Group (Blue Collars)
- ✅ تحديث حالة العمال في النظام الأونلاين
- ✅ منع إضافة عمال محظورين

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
- تثبيت Python و pip
- إنشاء virtual environment
- تثبيت المكتبات المطلوبة (requests, Pillow, schedule, dotenv)
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
فحص: هل تم معالجته من قبل؟
     ↓
    نعم → تجاهل
     ↓
    لا → تحميل الصور
     ↓
    تحويل صورة الوجه لـ base64
     ↓
    إضافة في HikCentral
     ↓
    إضافة لـ Privilege Group (Blue Collars)
     ↓
    حفظ في قاعدة البيانات المحلية
     ↓
    تحديث الحالة في Supabase API → approved
```

### 3. العمال المحظورين
```
[Supabase API] → عامل محظور → حذف من HikCentral Privilege Group
```

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
[Worker] Already processed - skipping    # تم معالجته من قبل
[Image] Downloading...                   # تحميل صورة
[Image] Saved to ...                     # حفظ الصورة
[Worker] Adding to HikCentral...        # إضافة للنظام
[HikCentral] POST /api/...              # طلب API
[HikCentral] Success                     # نجح
[HikCentral] Person added with ID: 123  # تم الإضافة
[Worker] Added to privilege group       # تمت الإضافة للمجموعة
[Supabase] Updating worker ... to approved  # تحديث الحالة
[Worker] ✓ Successfully processed       # تم بنجاح
```

---

## ⚠️ استكشاف الأخطاء

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
pip list

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
- ✅ جلب العمال الجدد من Supabase
- ✅ الإضافة التلقائية لـ HikCentral
- ✅ حفظ نسخة احتياطية محلية
- ✅ التحديث التلقائي للحالات

**للمتابعة المباشرة:**
```bash
sudo journalctl -u hydepark-sync -f
```

---

**تم بناؤه بواسطة**: Smart Stations Solutions  
**التاريخ**: نوفمبر 2025  
**النسخة**: 1.0.0 (Proof of Concept)
