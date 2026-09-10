"""
=============================================================================
SmartBottle™ AI Vision SCADA - محرك اتخاذ القرار (AI Decision Engine)
=============================================================================
الوظيفة البرمجية والهندسية:
  يقوم هذا الموديول بتحويل النتائج الخام (Bounding Boxes & Probabilities)
  القادمة من نموذج الذكاء الاصطناعي YOLOv8 إلى قرارات صناعية قطعية واضحة:
  
  1. قرار المطابقة (PASS):
     الزجاجة سليمة 100% ومستوفية للشروط (وجود جسم الزجاجة، الغطاء، والملصق).
     -> الإجراء: إضاءة مؤشر أخضر، استمرار دوران السير، ومرور الزجاجة بأمان.

  2. قرار الرفض والعيب (FAIL):
     رصد عيب صناعي مؤكد (غطاء مفقود cap missing، بلاستيك تالف damaged plastic،
     أو ملصق مفقود label missing).
     -> الإجراء: إضاءة مؤشر أحمر، إطلاق صافرة الإنذار، وتفعيل ذراع السيرفو لرفض الزجاجة.

  3. قرار المراجعة والشك (REVIEW):
     في حال كانت نسبة ثقة النموذج متوسطة أو الصورة غير واضحة.
     -> الإجراء: إضاءة مؤشر أزرق وتنبيه المشغل البشري لفحصها يدوياً دون توقف مفاجئ.

كما يتضمن المحرك آلية منع التكرار (Debouncing) لمنع إطلاق إشارات الرفض أكثر
من مرة لنفس الزجاجة الواحدة أثناء مرورها.
=============================================================================
"""

import time
import logging
import config

# إعداد مسجل الأحداث الخاص بمحرك اتخاذ القرار
logger = logging.getLogger("DecisionEngine")


class InspectionResult:
    """
    هيكل بيانات متكامل يمثل نتيجة فحص زجاجة واحدة.
    يحتوي على القرار النهائي، نسبة التأكد، نوع العيب، ووقت المعالجة.
    """
    def __init__(self, decision, confidence, primary_class, defect_type=None, all_detections=None, processing_time_ms=0.0):
        # القرار النهائي: "PASS", "FAIL", "REVIEW", "NONE"
        self.decision = decision            
        # نسبة الثقة (من 0.0 إلى 1.0)
        self.confidence = confidence        
        # التصنيف الأساسي الظاهر
        self.primary_class = primary_class  
        # اسم العيب إن وجد (مثل "cap missing") أو None
        self.defect_type = defect_type      
        # قائمة تفصيلية بكافة الأجسام المكتشفة في الكادر
        self.all_detections = all_detections or []
        # زمن معالجة الاستدلال بالمللي ثانية
        self.processing_time_ms = processing_time_ms
        # الطابع الزمني لعملية الفحص
        self.timestamp = time.strftime("%H:%M:%S")

    def to_dict(self):
        """
        تحويل نتيجة الفحص إلى قاموس JSON لسهولة إرساله عبر WebSockets
        وواجهات الـ REST API وعرضه على لوحة التحكم SCADA.
        """
        return {
            "decision": self.decision,
            "confidence": round(float(self.confidence) * 100, 1),
            "primary_class": self.primary_class,
            "defect_type": self.defect_type,
            "all_detections": self.all_detections,
            "processing_time_ms": round(self.processing_time_ms, 1),
            "timestamp": self.timestamp
        }


class DecisionEngine:
    """
    محرك تقييم القرارات الصناعي الذكي.
    يطبق معايير الجودة الصارمة ومبدأ أولوية العيب (Defect Priority Principle).
    """
    def __init__(self):
        # تحميل العتبات وفئات الفحص من ملف الإعدادات المركزي
        self.high_threshold = config.CONFIDENCE_HIGH_THRESHOLD
        self.low_threshold = config.CONFIDENCE_LOW_THRESHOLD
        self.normal_classes = set(config.NORMAL_CLASSES)
        self.defect_classes = set(config.DEFECT_CLASSES)
        
        # متغيرات منع التكرار (Debounce Mechanism)
        self.last_decision_time = 0.0
        self.last_decision = None
        # الفاصل الزمني الأدنى المسموح به بين فحصين متتاليين (بالثواني)
        self.debounce_interval_sec = 0.8  

    def evaluate(self, yolo_boxes, class_names, processing_time_ms=0.0):
        """
        تقييم مربعات الكشف القادمة من استدلال YOLOv8.
        
        المعاملات (Parameters):
          - yolo_boxes: كائنات المربعات المحيطة المكتشفة بواسطة YOLO.
          - class_names: قاموس أسماء الفئات المقابلة للأرقام.
          - processing_time_ms: زمن المعالجة بالمللي ثانية.
          
        العائد (Returns):
          - كائن من نوع InspectionResult يحدد القرار النهائي بدقة.
        """
        start_eval = time.time()
        
        # في حال عدم وجود أي جسم داخل الكادر
        if yolo_boxes is None or len(yolo_boxes) == 0:
            return InspectionResult(
                decision="NONE",
                confidence=0.0,
                primary_class="None",
                defect_type=None,
                all_detections=[],
                processing_time_ms=processing_time_ms
            )

        detected_defects = []
        detected_normals = []
        parsed_detections = []

        # قراءة وتصنيف كل مربع مكتشف في الإطار
        for box in yolo_boxes:
            cls_id = int(box.cls[0].item())
            cls_name = class_names.get(cls_id, f"Class {cls_id}")
            conf = float(box.conf[0].item())

            item = {
                "name": cls_name,
                "confidence": round(conf * 100, 1),
                "is_defect": cls_name in self.defect_classes
            }
            parsed_detections.append(item)

            # فرز المكتشفات: هل هو عيب أم مكوّن سليم؟
            if cls_name in self.defect_classes:
                detected_defects.append((cls_name, conf))
            elif cls_name in self.normal_classes:
                detected_normals.append((cls_name, conf))

        # =====================================================================
        # الأولوية الأولى: فحص العيوب (Defect Priority Principle)
        # إذا تم اكتشاف أي عيب مؤكد، يتم اتخاذ قرار الرفض FAIL فوراً حماية للجودة
        # =====================================================================
        if detected_defects:
            # ترتيب العيوب تنازلياً حسب أعلى نسبة ثقة
            detected_defects.sort(key=lambda x: x[1], reverse=True)
            top_defect_name, top_defect_conf = detected_defects[0]

            # إذا كانت ثقة العيب أعلى من العتبة الدنيا -> رفض قطعي (FAIL)
            if top_defect_conf >= self.low_threshold:
                return InspectionResult(
                    decision="FAIL",
                    confidence=top_defect_conf,
                    primary_class=top_defect_name,
                    defect_type=top_defect_name,
                    all_detections=parsed_detections,
                    processing_time_ms=processing_time_ms
                )
            else:
                # العيب موجود ولكن نسبة التأكد ضعيفة جداً -> إحالة للمراجعة (REVIEW)
                return InspectionResult(
                    decision="REVIEW",
                    confidence=top_defect_conf,
                    primary_class=top_defect_name,
                    defect_type=f"Possible {top_defect_name}",
                    all_detections=parsed_detections,
                    processing_time_ms=processing_time_ms
                )

        # =====================================================================
        # الأولوية الثانية: فحص الزجاجة السليمة (Normal Bottle Check)
        # =====================================================================
        if detected_normals:
            detected_normals.sort(key=lambda x: x[1], reverse=True)
            top_normal_name, top_normal_conf = detected_normals[0]

            # ثقة عالية -> مطابقة ممتازة وموافقة كاملة (PASS)
            if top_normal_conf >= self.high_threshold:
                return InspectionResult(
                    decision="PASS",
                    confidence=top_normal_conf,
                    primary_class=top_normal_name,
                    defect_type=None,
                    all_detections=parsed_detections,
                    processing_time_ms=processing_time_ms
                )
            # ثقة متوسطة -> مراجعة (REVIEW)
            elif top_normal_conf >= self.low_threshold:
                return InspectionResult(
                    decision="REVIEW",
                    confidence=top_normal_conf,
                    primary_class=top_normal_name,
                    defect_type=None,
                    all_detections=parsed_detections,
                    processing_time_ms=processing_time_ms
                )

        # =====================================================================
        # الأولوية الثالثة: حالة غامضة أو غير محددة بدقة
        # =====================================================================
        return InspectionResult(
            decision="REVIEW",
            confidence=0.0,
            primary_class="Unknown",
            defect_type=None,
            all_detections=parsed_detections,
            processing_time_ms=processing_time_ms
        )

    def should_actuate(self, decision):
        """
        آلية منع الاهتزاز والتكرار (Actuation Debouncing):
        تضمن عدم إرسال أوامر متكررة لنفس الزجاجة إلى محرك السيرفو أو الصافرة.
        
        العائد: True إذا مضى وقت كافٍ يسمح بتفعيل الأجهزة الميكانيكية، و False عدا ذلك.
        """
        if decision not in ["PASS", "FAIL", "REVIEW"]:
            return False

        now = time.time()
        if now - self.last_decision_time >= self.debounce_interval_sec:
            self.last_decision_time = now
            self.last_decision = decision
            return True
        return False
