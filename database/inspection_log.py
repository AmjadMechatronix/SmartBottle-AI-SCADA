"""
=============================================================================
SmartBottle™ AI Vision SCADA - سجل الفحص وقاعدة البيانات (Inspection Database)
=============================================================================
الوظيفة البرمجية والهندسية:
  1. إدارة وتخزين كافة عمليات فحص الزجاجات في سجل زمني منظم (Audit Trail).
  2. الحفاظ على أمان الخيوط البرمجية (Thread-Safety) عبر أقفال التزامن (Threading Lock)
     لتجنب تعارض العمليات بين خيوط خادم Flask وخيوط التليمتري.
  3. تطبيق نمط التصميم الأحادي (Singleton Pattern) لضمان وجود نسخة واحدة موحدة
     من قاعدة البيانات تشترك فيها جميع مسارات النظام.
  4. حساب مؤشرات الأداء الصناعية الرئيسية (Key Performance Indicators - KPIs)
     مثل: معدل الإنتاجية السليمة (Yield Rate)، ومعدل العيوب (Defect Rate).
  5. تصدير التقارير الصناعية الرسمية بصيغة CSV لحظياً وبدون إجهاد للقرص الصلب (In-Memory).
=============================================================================
"""

import os
import csv
import io
import time
from datetime import datetime
import threading


class InspectionLogger:
    """
    فئة إدارة السجلات وقاعدة البيانات اللحظية (Thread-Safe In-Memory Database).
    تستخدم نمط Singleton لضمان مشاركة السجلات بين كافة أجزاء المشروع.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """
        تطبيق نمط Singleton:
        إذا كانت الفئة قد أُنشئت مسبقاً، يتم إرجاع نفس النسخة لتفادي تكرار السجلات في الذاكرة.
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InspectionLogger, cls).__new__(cls)
                cls._instance.records = []
                cls._instance.counter = 0
            return cls._instance

    def log(self, decision, confidence, primary_class, defect_type=None, camera_source="webcam", processing_time_ms=0.0):
        """
        تسجيل عملية فحص جديدة لزجاجة مرت في المحطة.
        
        المعاملات:
          - decision: نتيجة الفحص ("PASS", "FAIL", "REVIEW").
          - confidence: نسبة الثقة من 0.0 إلى 1.0.
          - primary_class: الفئة الأساسية المكتشفة.
          - defect_type: نوع العيب إن وجد (مثل "cap missing").
          - camera_source: مصدر الكاميرا المستخدمة في الفحص.
          - processing_time_ms: زمن معالجة الذكاء الاصطناعي بالمللي ثانية.
        """
        with self._lock:
            self.counter += 1
            now = datetime.now()
            entry = {
                "inspection_id": self.counter,                       # رقم العملية التسلسلي
                "date": now.strftime("%Y-%m-%d"),                    # التاريخ
                "time": now.strftime("%H:%M:%S"),                    # الوقت الدقيق
                "result": decision,                                  # القرار
                "confidence": round(float(confidence) * 100, 1),     # نسبة الثقة كنسبة مئوية
                "primary_class": primary_class,                      # الصنف الأساسي
                "defect_type": defect_type or "-",                   # تفصيل العيب
                "camera_source": camera_source,                      # مصدر الكاميرا
                "processing_time_ms": round(float(processing_time_ms), 1) # زمن المعالجة
            }
            # إدراج السجل في البداية ليكون الأحدث دائماً في القمة
            self.records.insert(0, entry)
            
            # حماية الذاكرة: الإبقاء على آخر 500 عملية فحص فقط لمنع امتلاء RAM
            if len(self.records) > 500:
                self.records.pop()
            return entry

    def get_recent(self, limit=20):
        """
        استرجاع أحدث عدد محدد من عمليات الفحص لعرضها في جدول لوحة التحكم SCADA.
        """
        with self._lock:
            return list(self.records[:limit])

    def get_summary_stats(self):
        """
        حساب وتلخيص مؤشرات الأداء الصناعية (Production KPIs):
          - إجمالي الإنتاج الكلي (Total Inspected)
          - عدد الزجاجات المطابقة (Passed Bottles)
          - عدد الزجاجات المعيبة المرفوضة (Defects)
          - عدد الزجاجات المحالة للمراجعة (Review)
          - نسبة الجودة السليمة (Yield Rate %)
          - نسبة العيوب (Defect Rate %)
          - متوسط ثقة النموذج ومتوسط زمن الاستدلال
        """
        with self._lock:
            total = len(self.records)
            if total == 0:
                return {
                    "total": 0, "passed": 0, "defects": 0, "review": 0,
                    "yield_rate": 100.0, "defect_rate": 0.0, 
                    "avg_confidence": 0.0, "avg_time_ms": 0.0
                }

            passed = sum(1 for r in self.records if r["result"] == "PASS")
            defects = sum(1 for r in self.records if r["result"] == "FAIL")
            review = sum(1 for r in self.records if r["result"] == "REVIEW")
            avg_conf = sum(r["confidence"] for r in self.records) / total
            avg_time = sum(r["processing_time_ms"] for r in self.records) / total

            return {
                "total": total,
                "passed": passed,
                "defects": defects,
                "review": review,
                "yield_rate": round((passed / total) * 100, 1),
                "defect_rate": round((defects / total) * 100, 1),
                "avg_confidence": round(avg_conf, 1),
                "avg_time_ms": round(avg_time, 1)
            }

    def get_kpi_summary(self):
        """دالة بديلة مختصرة لاسترجاع مؤشرات الـ KPIs."""
        return self.get_summary_stats()

    def export_csv_stream(self):
        """
        توليد تقرير بصيغة CSV في الذاكرة مباشرة دون الحاجة لإنشاء ملفات مؤقتة على القرص.
        يتيح للمستخدمين تنزيل التقارير عبر المتصفح فوراً.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # ترويسة الأعمدة الرسمية للتقرير الصناعي
        writer.writerow([
            "Inspection ID", "Date", "Time", "Result", 
            "Defect Type", "Confidence (%)", "Camera Source", "Processing Time (ms)"
        ])
        
        with self._lock:
            for r in self.records:
                writer.writerow([
                    r["inspection_id"], r["date"], r["time"], r["result"],
                    r["defect_type"], r["confidence"], r["camera_source"], r["processing_time_ms"]
                ])
        output.seek(0)
        return output.getvalue()

    def clear(self):
        """إعادة تصفير قاعدة البيانات وسجلات الفحص."""
        with self._lock:
            self.records.clear()
            self.counter = 0
