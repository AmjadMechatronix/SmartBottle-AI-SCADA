"""
=============================================================================
SmartBottle™ AI Vision SCADA - سكربت تدريب نموذج الذكاء الاصطناعي (Training Script)
=============================================================================
المعمارية التقنية والغرض:
  1. الاتصال بمنصة Roboflow السحابية لتنزيل مجموعة بيانات فحص الزجاجات المصنفة (Dataset).
  2. تدريب شبكة عصبية عميقة من نوع YOLOv8 Small (yolov8s.pt) لاكتشاف 6 فئات بدقة:
     - الفئات الطبيعية: bottle (جسم الزجاجة), cap (الغطاء), label (الملصق).
     - فئات العيوب: cap missing (غطاء مفقود), damaged plastic (بلاستيك تالف), label missing (ملصق مفقود).
  3. تقييم أداء النموذج واستخراج مقاييس الدقة القياسية (mAP50 و mAP50-95).
  4. تصدير النموذج النهائي بصيغة ONNX المفتوحة للتشغيل فائق السرعة على الحواف الصناعية (Edge AI).
=============================================================================
"""

import os
from roboflow import Roboflow
from ultralytics import YOLO

# =============================================================================
# 1. إعدادات منصة Roboflow وتنزيل مجموعة البيانات (Dataset Acquisition)
# =============================================================================
# مفتاح الـ API الخاص بحساب Roboflow لتنزيل الصور والتصنيفات بدقة YOLOv8
ROBOFLOW_API_KEY = "muZmUeqhLjfmSOjVFSfB"

print("🔄 جارٍ تحميل مجموعة البيانات المصنفة من منصة Roboflow...")

try:
    rf = Roboflow(api_key=ROBOFLOW_API_KEY)
    # مساحة العمل والمشروع المخصص لعيوب الزجاجات
    project = rf.workspace("-tvwhk").project("bottle-defect-detection-rkwwy-c9lmv")
    version = project.version(1)
    # تنزيل البيانات بالتنسيق المتوافق مع YOLOv8 (الصور وملف data.yaml)
    dataset = version.download("yolov8")
    data_yaml_path = f"{dataset.location}/data.yaml"
    print(f"✅ تم تحميل البيانات بنجاح في المسار: {dataset.location}")
except Exception as e:
    print(f"⚠️ تعذر الاتصال بـ Roboflow، سيتم استخدام المجلد المحلي إن وجد: {e}")
    data_yaml_path = "bottle-defect-detection-1/data.yaml"

# =============================================================================
# 2. بناء وتدريب نموذج YOLOv8 (Deep Learning Model Training)
# =============================================================================
print("\n🚀 بدء مرحلة تدريب الشبكة العصبية (YOLOv8 Training)...")

# نستخدم نموذج YOLOv8s (Small) الذي يوفر التوازن المثالي بين السرعة الفائقة والدقة العالية
model = YOLO("yolov8s.pt") 

# بدء جلسة التدريب وضبط المعاملات الفائقة (Hyperparameters):
results = model.train(
    data=data_yaml_path,   # مسار ملف تكوين البيانات والفئات
    epochs=50,             # عدد دورات التدريب (Epochs)
    imgsz=640,             # حجم أبعاد الصورة بالبكسل (640x640)
    batch=16,              # حجم الدفعة (Batch Size) لمعالجة 16 صورة معاً
    device="0" if os.getenv("CUDA_VISIBLE_DEVICES") else "cpu",  # استخدام بطاقة GPU (Nvidia CUDA) إن وجدت لتسريع التدريب
    patience=15,           # التوقف المبكر (Early Stopping) إذا لم يتحسن النموذج بعد 15 دورة لمنع فرط التخصيص (Overfitting)
    save=True,             # حفظ أفضل نموذج تلقائياً (best.pt)
    project="runs/bottle_defect",  # مجلد حفظ مخرجات التدريب
    name="yolov8_experiment"       # اسم التجربة
)

print("✅ اكتملت دورات التدريب بنجاح!")

# =============================================================================
# 3. تقييم جودة ودقة النموذج (Model Validation & Metrics)
# =============================================================================
print("\n📊 تقييم أداء النموذج المدرب على بيانات الاختبار (Validation)...")
best_model_path = "runs/bottle_defect/yolov8_experiment/weights/best.pt"

# إذا كان الملف موجوداً نقوم بتحميله لتقييم الدقة
if os.path.exists(best_model_path):
    trained_model = YOLO(best_model_path)
    metrics = trained_model.val()
    # طباعة مقياس متوسط الدقة الكلي (mAP50-95) ومقياس (mAP50)
    print(f"📈 Mean Average Precision (mAP50-95): {metrics.box.map}")
    print(f"📈 mAP50 (عند تقاطع 50%): {metrics.box.map50}")

    # =========================================================================
    # 4. تصدير النموذج للاستخدام الصناعي (Model Export to ONNX)
    # =========================================================================
    print("\n📦 تصدير النموذج إلى صيغة ONNX المفتوحة للإنتاج الصناعي...")
    trained_model.export(format="onnx")
    print("🎉 تم حفظ وتصدير النموذج، وأصبح جاهزاً للاستخدام الفوري في server.py!")
