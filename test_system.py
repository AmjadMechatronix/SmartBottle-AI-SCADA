"""
=============================================================================
SmartBottle™ AI Vision SCADA - Unified System Diagnostics & Test Suite
=============================================================================
الاختبار الموحد الشامل لكافة أجزاء النظام:
  1. الإعدادات والنموذج (Configuration & Model Check)
  2. محرك اتخاذ القرار بالذكاء الاصطناعي (AI Decision Engine)
  3. الهاردوير والمحاكاة الافتراضية (Hardware Controller & Simulation Fallback)
  4. قاعدة البيانات وسجلات الفحص وتقارير الـ CSV (Database & KPI Metrics)
  5. مسارات الويب وخادم الفحص (Flask Server & SCADA REST APIs)
  6. مسارات برنامج التحكم الصناعي (LabVIEW Integration Endpoints)
=============================================================================
"""

import sys
import os
import json
import time

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("\n" + "=" * 70)
print("🚀 SMARTBOTTLE™ AI SCADA - الاختبار التشخيصي الشامل للنظام")
print("=" * 70)

# =============================================================================
# [TEST 1] التحقق من ملف الإعدادات والنموذج
# =============================================================================
print("\n[TEST 1/6] ⚙️  فحص الإعدادات وتكوين النموذج (Configuration Check)...")
try:
    import config
    print(f"   🔹 مسار نموذج الذكاء الاصطناعي: {config.MODEL_PATH}")
    print(f"   🔹 فئات الفحص المعرفة: {len(config.CLASS_NAMES)} فئات")
    print(f"   🔹 فئات العيوب: {config.DEFECT_CLASSES}")
    print(f"   🔹 مصدر الكاميرا الافتراضي: {config.DEFAULT_CAMERA_SOURCE}")
    print(f"   🔹 عتبات الثقة: High={config.CONFIDENCE_HIGH_THRESHOLD} | Low={config.CONFIDENCE_LOW_THRESHOLD}")
    assert os.path.exists(config.MODEL_PATH), f"الملف {config.MODEL_PATH} غير موجود!"
    assert len(config.CLASS_NAMES) == 6, "يجب أن يحتوي النموذج على 6 فئات بدقة!"
    print("   ✅ نجح اختبار الإعدادات ووجود النموذج!")
except Exception as e:
    print(f"   ❌ فشل في اختبار الإعدادات: {e}")
    sys.exit(1)

# =============================================================================
# [TEST 2] فحص محرك اتخاذ القرار (AI Decision Engine)
# =============================================================================
print("\n[TEST 2/6] 🧠 فحص محرك اتخاذ القرار (Decision Engine Test)...")
try:
    from ai.decision_engine import DecisionEngine
    engine = DecisionEngine()

    class MockItem:
        def __init__(self, val): self.val = val
        def item(self): return self.val

    class MockTensor:
        def __init__(self, val): self.items = [MockItem(val)]
        def __getitem__(self, idx): return self.items[idx]

    class MockBox:
        def __init__(self, cls_id, conf):
            self.cls = MockTensor(cls_id)
            self.conf = MockTensor(conf)

    # 1. اختبار زجاجة سليمة (PASS)
    boxes_pass = [MockBox(0, 0.88), MockBox(1, 0.92), MockBox(4, 0.85)]
    res_pass = engine.evaluate(boxes_pass, config.CLASS_NAMES)
    print(f"   🔹 اختبار زجاجة سليمة: القرار={res_pass.decision} (ثقة: {res_pass.confidence:.2f})")
    assert res_pass.decision == "PASS", f"المتوقع PASS لكن النتيجة: {res_pass.decision}"

    # 2. اختبار زجاجة معيبة (FAIL - غطاء مفقود)
    boxes_fail = [MockBox(0, 0.85), MockBox(2, 0.78)]
    res_fail = engine.evaluate(boxes_fail, config.CLASS_NAMES)
    print(f"   🔹 اختبار زجاجة معيبة: القرار={res_fail.decision} (العيب: {res_fail.defect_type})")
    assert res_fail.decision == "FAIL", f"المتوقع FAIL لكن النتيجة: {res_fail.decision}"
    assert res_fail.defect_type == "cap missing"

    # 3. اختبار زجاجة بثقة منخفضة (REVIEW)
    boxes_rev = [MockBox(0, 0.42)]
    res_rev = engine.evaluate(boxes_rev, config.CLASS_NAMES)
    print(f"   🔹 اختبار حالة غير مؤكدة: القرار={res_rev.decision}")
    assert res_rev.decision == "REVIEW", f"المتوقع REVIEW لكن النتيجة: {res_rev.decision}"

    print("   ✅ نجح اختبار محرك اتخاذ القرار بجميع الحالات!")
except Exception as e:
    print(f"   ❌ فشل في محرك اتخاذ القرار: {e}")
    sys.exit(1)

# =============================================================================
# [TEST 3] فحص متحكم الهاردوير والمحاكاة الافتراضية
# =============================================================================
print("\n[TEST 3/6] 🔌 فحص متحكم الهاردوير ونظام المحاكاة الذكي (Hardware Controller)...")
try:
    from hardware.esp32_controller import ESP32Controller
    hw = ESP32Controller()
    st = hw.get_status()
    mode_str = "محاكاة افتراضية (Virtual)" if st.get("is_simulated") else f"جهاز حقيقي ({st.get('port')})"
    print(f"   🔹 وضع التشغيل الحالي: {mode_str}")

    # اختبار إشارة النجاح (PASS)
    hw.actuate_pass()
    st = hw.get_status()
    assert st["led"] == "GREEN", "يجب أن يضيء الليد الأخضر عند PASS"
    assert st["motor"] == "ON", "يجب أن يعمل السير عند PASS"
    assert st["servo"] == "HOME", "يجب أن يكون السيرفو في وضع HOME"
    print("   🔹 اختبار إشارة PASS (ليد أخضر + سيرفو وضع البداية): سليم")

    # اختبار إشارة العيب (FAIL)
    hw.actuate_fail()
    st = hw.get_status()
    assert st["led"] == "RED", "يجب أن يضيء الليد الأحمر عند FAIL"
    assert "REJECT" in str(st["servo"]), "يجب أن يتحرك السيرفو لطرد العيب"
    print("   🔹 اختبار إشارة FAIL (ليد أحمر + حركة السيرفو لطرد العيب): سليم")

    # اختبار ريليه إضاءة الصندوق (Relay Box Light)
    hw.relay_on()
    st = hw.get_status()
    assert st["relay"] is True
    hw.relay_off()
    st = hw.get_status()
    assert st["relay"] is False
    print("   🔹 اختبار ريليه الإضاءة (Relay ON / OFF): سليم")

    # إعادة التعيين
    hw.reset()
    print("   ✅ نجح اختبار الهاردوير واستجابة الأوامر بالكامل!")
except Exception as e:
    print(f"   ❌ فشل في اختبار الهاردوير: {e}")
    sys.exit(1)

# =============================================================================
# [TEST 4] فحص قاعدة البيانات وتصدير الـ CSV
# =============================================================================
print("\n[TEST 4/6] 📊 فحص سجل عمليات الفحص وإحصائيات KPIs (Database & CSV)...")
try:
    from database.inspection_log import InspectionLogger
    db = InspectionLogger()
    db.clear()

    # تسجيل عمليات تجريبية
    db.log("PASS", 0.94, "bottle", None, "test_cam", 20.5)
    db.log("FAIL", 0.89, "cap missing", "cap missing", "test_cam", 19.2)
    db.log("REVIEW", 0.45, "damaged plastic", "damaged plastic", "test_cam", 22.0)

    logs = db.get_recent(10)
    assert len(logs) == 3, f"المتوقع 3 سجلات، وُجد {len(logs)}"

    kpi = db.get_summary_stats()
    print(f"   🔹 إجمالي الفحوصات: {kpi['total']} | نسبة الجودة: {kpi['yield_rate']}% | نسبة العيوب: {kpi['defect_rate']}%")
    assert kpi["passed"] == 1 and kpi["defects"] == 1 and kpi["review"] == 1

    csv_data = db.export_csv_stream()
    assert "Inspection ID" in csv_data
    assert "cap missing" in csv_data
    print("   🔹 اختبار توليد ملف CSV: تم التحقق من الأعمدة والبيانات")
    print("   ✅ نجح اختبار قاعدة البيانات وتوليد التقارير!")
except Exception as e:
    print(f"   ❌ فشل في فحص قاعدة البيانات: {e}")
    sys.exit(1)

# =============================================================================
# [TEST 5] فحص مسارات خادم Flask وواجهة SCADA
# =============================================================================
print("\n[TEST 5/6] 🌐 فحص مسارات خادم الويب وواجهة SCADA (Flask REST APIs)...")
try:
    from server import app
    client = app.test_client()

    # 1. الصفحة الرئيسية
    r = client.get('/')
    assert r.status_code == 200, f"خطأ في الصفحة الرئيسية: {r.status_code}"
    assert b"SmartBottle" in r.data
    print("   🔹 مسار الواجهة الرئيسية [/]: متصل (200 OK)")

    # 2. مسار الإحصائيات الحية
    r = client.get('/api/stats')
    assert r.status_code == 200
    data = json.loads(r.data)
    assert "total_inspections" in data and "hardware" in data
    print("   🔹 مسار الإحصائيات التليمترية [/api/stats]: متصل ومرجع للبيانات")

    # 3. مسار تغيير وضع التشغيل
    r = client.post('/api/mode', json={"auto_mode": True})
    assert r.status_code == 200
    print("   🔹 مسار وضع التشغيل الآلي [/api/mode]: يعمل بنجاح")

    # 4. مسارات التحكم بالعتاد عبر الـ Web
    r_motor = client.post('/api/hardware/motor', json={"action": "on"})
    r_servo = client.post('/api/hardware/servo', json={"action": "home"})
    r_led = client.post('/api/hardware/led', json={"color": "green"})
    assert r_motor.status_code == 200 and r_servo.status_code == 200 and r_led.status_code == 200
    print("   🔹 مسارات التحكم بالعتاد [/api/hardware/*]: تستقبل وتنفذ الأوامر")

    # 5. مسار تصدير CSV
    r_csv = client.get('/api/export_csv')
    assert r_csv.status_code == 200
    assert r_csv.mimetype == "text/csv"
    print("   🔹 مسار تحميل التقرير [/api/export_csv]: جاهز للتحميل")

    print("   ✅ نجح اختبار مسارات خادم الويب بالكامل!")
except Exception as e:
    print(f"   ❌ فشل في مسارات الخادم: {e}")
    sys.exit(1)

# =============================================================================
# [TEST 6] فحص نقاط تكامل LabVIEW
# =============================================================================
print("\n[TEST 6/6] 🏭 فحص نقاط تكامل برنامج التحكم الصناعي (LabVIEW Endpoints)...")
try:
    # 1. مسار تليمتري LabVIEW بتنسيق JSON المسطح
    r_lv = client.get('/api/labview/telemetry')
    assert r_lv.status_code == 200
    lv_data = json.loads(r_lv.data)
    expected_keys = ["total", "good", "defective", "pass_rate", "distance_cm", "is_pass", "is_fail"]
    for k in expected_keys:
        assert k in lv_data, f"المفتاح {k} مفقود في استجابة LabVIEW!"
    print(f"   🔹 مسار بيانات LabVIEW [/api/labview/telemetry]: يحتوي على {len(lv_data)} حقل جاهز للفك")

    # 2. مسار لقطة الكاميرا المباشرة لـ LabVIEW Vision
    r_snap = client.get('/api/labview/snapshot.jpg')
    assert r_snap.status_code == 200
    assert r_snap.mimetype == "image/jpeg"
    print(f"   🔹 مسار لقطة الكاميرا [/api/labview/snapshot.jpg]: متدفق بصيغة JPEG ({len(r_snap.data)} بايت)")

    print("   ✅ نجح اختبار تكامل LabVIEW الصناعي 100%!")
except Exception as e:
    print(f"   ❌ فشل في نقاط تكامل LabVIEW: {e}")
    sys.exit(1)

# =============================================================================
# خلاصة النتيجة
# =============================================================================
print("\n" + "=" * 70)
print("🎉 اكتمل الفحص الشامل بنجاح 100%! جميع مكونات النظام تعمل بتناغم تام.")
print("=" * 70 + "\n")
