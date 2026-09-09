"""
سكربت تدريب نموذج كشف عيوب الزجاجات (Bottle Defect Detection) باستخدام YOLOv8/YOLO11 و Roboflow
"""

import os
from roboflow import Roboflow
from ultralytics import YOLO

# ==========================================
# 1. إعدادات Roboflow وتنزيل البيانات
# ==========================================
ROBOFLOW_API_KEY = "muZmUeqhLjfmSOjVFSfB"

print("🔄 جارٍ تحميل مجموعة البيانات من Roboflow...")

try:
    rf = Roboflow(api_key=ROBOFLOW_API_KEY)
    project = rf.workspace("-tvwhk").project("bottle-defect-detection-rkwwy-c9lmv")
    version = project.version(1)
    dataset = version.download("yolov8")
    data_yaml_path = f"{dataset.location}/data.yaml"
    print(f"✅ تم تحميل البيانات بنجاح في: {dataset.location}")
except Exception as e:
    print(f"⚠️ خطأ أثناء تحميل البيانات من Roboflow: {e}")
    data_yaml_path = "bottle-defect-detection-1/data.yaml"

# ==========================================
# 2. بناء وتدريب نموذج YOLO
# ==========================================
print("\n🚀 بدء مرحلة التدريب (Training)...")

# نستخدم YOLOv8 Nano أو Small لنقطة بداية ممتازة ودقيقة
model = YOLO("yolov8s.pt") 

# بدء التدريب
results = model.train(
    data=data_yaml_path,   # مسار ملف تكوين البيانات
    epochs=50,             # عدد دورات التدريب (يمكن زيادتها لـ 100 لتحسين الدقة)
    imgsz=640,             # حجم أبعاد الصورة
    batch=16,              # حجم الدفعة (يمكن تقليله لـ 8 إذا كانت الذاكرة ممتلئة)
    device="0" if os.getenv("CUDA_VISIBLE_DEVICES") else "cpu", # استخدام GPU إن وجد
    patience=15,           # إيقاف التدريب مبكراً إذا لم يتحسن النموذج بعد 15 دورة
    save=True,             # حفظ أفضل نموذج تلقائياً
    project="runs/bottle_defect",
    name="yolov8_experiment"
)

print("✅ اكتمل التدريب بنجاح!")

# ==========================================
# 3. تقييم أداء النموذج (Validation)
# ==========================================
print("\n📊 تقييم أداء النموذج على بيانات الاختبار...")
best_model_path = "runs/bottle_defect/yolov8_experiment/weights/best.pt"
trained_model = YOLO(best_model_path)

metrics = trained_model.val()
print(f"📈 Mean Average Precision (mAP50-95): {metrics.box.map}")
print(f"📈 mAP50: {metrics.box.map50}")

# ==========================================
# 4. تجربة النموذج على صور جديدة (Inference)
# ==========================================
print("\n🔍 إجراء اختبار واستدلال (Inference)...")
# يمكنك تمرير صورة أو مجلد صور لاختباره
# results = trained_model.predict(source="path/to/test/image.jpg", save=True, conf=0.25)

# ==========================================
# 5. تصدير النموذج للاستخدام في تطبيقات الإنتاج (Export)
# ==========================================
print("\n📦 تصدير النموذج إلى صيغة ONNX...")
trained_model.export(format="onnx")
print("🎉 جاهز للاستخدام في المشاريع والتطبيقات!")
