## الهدف
- التحول من جلب العمال مباشرةً إلى آلية Polling عبر Events API.
- معالجة كل أنواع الأحداث لتحويلها إلى عمليات مناسبة على HikCentral (إضافة/تحديث/حظر/فك حظر/حذف) مع سجل محلي ذكي يمنع التكرار.

## إعدادات البيئة
- إضافة:
  - `SUPABASE_URL`: قاعدة الـ Functions، مثل `https://<project>.supabase.co/functions/v1`
  - `SUPABASE_EVENTS_PREFIX`: البادئة لمسار الأحداث، مثل `make-server-<id>`
  - `SUPABASE_API_KEY`: للمصادقة عبر `X-API-Key`
- استخدام القيم الحالية لـ HikCentral (`HIKCENTRAL_*`) كما هي.

## تدفق البيانات
- جدولة دورية: كل `SYNC_INTERVAL_SECONDS`، يستدعي `GET /{prefix}/admin/events/pending?limit=100` مع `X-API-Key`.
- السيرفر يُعلِم الأحداث كـ consumed قبل الإرجاع؛ جانبنا يعالجها مرة واحدة.
- لكل حدث، نحول كائنات العمال داخل `event.workers` إلى صيغة داخلية موحّدة، ثم ننفذ العملية المناسبة على HikCentral ونحدّث السجل المحلي وSupabase.

## تحويل عامل الحدث
- الحقول المستخدمة:
  - `workerId`, `nationalIdNumber`, `fullName`, `status`, `blocked`, `blockedReason`
  - صور: `facePhoto`, `nationalIdImage`
  - بيانات إضافية: `delegatedUser.mobileNumber` → هاتف، `delegatedUser.email` → بريد، `unit.unitNumber` → رقم الوحدة
- تنزيل الصور، تحويل صورة الوجه إلى Base64.

## معالجة أنواع الأحداث
- `worker.created`, `workers.bulk_created`:
  - إضافة الشخص في HikCentral (إن لم يكن موجوداً محلياً)، تعيين للمجموعة، حفظ محلي، تحديث Supabase Approved.
  - إن كان موجوداً بهوية قومية مطابقة: تحديث فقط مع دمج صلاحية الزمن.
- `worker.unblocked`, `unit.workers_unblocked`:
  - إعادة تفعيل: لو كان محذوفاً في HikCentral (`hikcentral_deleted=True`) نضيفه مجدداً؛ وإلا تحدّث بياناته.
- `worker.blocked`, `unit.workers_blocked`:
  - حذف من HikCentral مرة واحدة، تعيين `hikcentral_deleted=True` محلياً، تحديث Supabase Blocked.
  - التكرارات لاحقاً: لا نحذف ثانيةً؛ فقط تسجيل الحالة.
- `worker.deleted`, `user.deleted_workers_deleted`, `user.expired_workers_deleted`, `worker.revoked`:
  - حذف من HikCentral (إن وُجد)، تعليم محلي بالحذف.

## عمليات HikCentral
- إضافة: `/api/resource/v1/person/single/add` مع `faces.faceData` Base64، وحقول الوقت بصيغة `YYYY-MM-DDTHH:mm:ss+TZ`.
- تحديث: `/api/resource/v1/person/single/update` باستخدام `personId` (المحفوظ محلياً كـ `hikcentral_id`) ودمج نطاقي الصلاحية.
- حذف: `/api/resource/v1/person/single/delete` باستخدام `personId`.
- مجموعة الصلاحيات: إضافة/إزالة حسب الحاجة.

## السجل المحلي (JSON)
- مفاتيح محلية لكل عامل:
  - `hikcentral_id`, `hikcentral_deleted` (فلاغ يمنع إعادة الحذف)، `validFrom`, `validTo`، مسارات الصور.
- تحديثات ذكية:
  - عند التحديث/الإضافة: `hikcentral_deleted=False`، دمج صلاحية الزمن.
  - عند الحذف: `hikcentral_deleted=True`.

## لوحة المتابعة (Dashboard)
- عرض حالة أحدث مزامنة وعدد العمال.
- يمكن إضافة صفحة لعرض آخر Events المعالجة وإحصائيات عبر `GET /{prefix}/admin/events/stats` لاحقاً.

## الأخطاء والاسترداد
- مصادقة: استخدام `X-API-Key`؛ إن لم يتوفر، دعم `Authorization: Bearer` لاختبارات الأدمن.
- التفريغ (Backoff) عند أخطاء الشبكة، وطباعة الأسباب.
- تحكم في معدل الطلبات: الالتزام بتوصيات 2–5 دقائق، أو حسب `SYNC_INTERVAL_SECONDS` الحالي.

## النشر
- تحديث `.env.example` لإضافة `SUPABASE_EVENTS_PREFIX` وشرح القيم.
- لا حاجة لتغييرات إضافية في `deploy.sh` عدا التأكد من وجود القيم الجديدة.

## أسئلة توضيحية
- ما قيمة `SUPABASE_EVENTS_PREFIX` الدقيقة لديك (مثال: `make-server-2c3121a9`)؟
- ما سياسة تعيين `validFrom`/`validTo` عند غيابها في الـ Events؟ هل نستخدم نطاق افتراضي (اليوم → +10 سنوات) أم نكتفي بالقيم الموجودة محلياً؟
- هل تريد إضافة صفحة Dashboard لعرض آخر 100 حدث مُعالَج؟
- هل يوجد Rate Limit خاص يجب الالتزام به غير الموصى به (2–5 دقائق)؟