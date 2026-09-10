"""
=============================================================================
SmartBottle™ AI Vision SCADA - الخادم الرئيسي والمحرك المركزي (Main SCADA Server)
=============================================================================
المعمارية الهندسية والوظائف:
  1. خادم تطبيقات الويب RESTful المبني على إطار عمل Flask.
  2. محرك الاتصال اللحظي فائق السرعة عبر تقنية WebSockets (Flask-SocketIO) بتردد 20Hz.
  3. محرك معالجة بث الكاميرات (OpenCV Video Engine):
     - دعم كاميرات الويب المدمجة (Webcam).
     - دعم كاميرات الهواتف عبر منفذ USB Type-C (عبر برامج مثل DroidCam/Iriun).
     - دعم كاميرات الشبكة والـ IP Cam (RTSP / HTTP).
     - دعم وحدة ESP32-CAM بنمطين: البث المستمر (MJPEG Stream) واللقطة الفورية (Snapshot /capture).
  4. استدلال الذكاء الاصطناعي في الوقت الفعلي (Real-Time YOLOv8 Inference).
  5. بوابة التزامن المزدوجة بحساس الألتراسونيك (Ultrasonic Interlock Gate):
     تضمن فحص كل زجاجة مرة واحدة فقط (One-Shot Inspection) عند وصولها للمحطة.
  6. نقاط تكامل مخصصة لبرنامج التحكم الصناعي National Instruments LabVIEW:
     - مسار JSON المسطح لفك البيانات في LabVIEW (/api/labview/telemetry).
     - مسار استخراج الصور الخام المباشرة لبرامج الرؤية (/api/labview/snapshot.jpg).
     - تحديث دوري للصور على القرص الصلب (C:/SmartBottle/labview_live.jpg/.bmp) بحماية ذرية (Atomic).
=============================================================================
"""

import os
import time
import json
import csv
import io
import threading
from datetime import datetime
import cv2
import numpy as np
import base64
import urllib.request
from flask import Flask, render_template, Response, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from ultralytics import YOLO

# استيراد ملف الإعدادات ووحدات النظام الفرعية
import config
from hardware.esp32_controller import ESP32Controller
from ai.decision_engine import DecisionEngine
from database.inspection_log import InspectionLogger

# =============================================================================
# 1. تهيئة تطبيق Flask وخادم المقابس اللحظية (Flask & SocketIO Initialization)
# =============================================================================
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['SECRET_KEY'] = 'smartbottle_secret_key_2026!'
app.config['TEMPLATES_AUTO_RELOAD'] = True

# تفعيل SocketIO بنمط الخيوط المتعددة غير المتزامنة (Threading Mode)
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# إنشاء كائنات المتحكم، محرك القرار، وقاعدة البيانات
esp32 = ESP32Controller()
decision_engine = DecisionEngine()
inspection_db = InspectionLogger()


def normalize_digits(text):
    """
    تحويل الأرقام العربية/الفارسية (مثل: ١٩٢.١٦٨) إلى أرقام إنجليزية (192.168)
    لمنع أخطاء إدخال عناوين الـ IP من لوحات المفاتيح في الهواتف.
    """
    if not text:
        return ""
    arabic_digits = "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹"
    english_digits = "01234567890123456789"
    trans = str.maketrans(arabic_digits, english_digits)
    return text.translate(trans)


# =============================================================================
# 2. تحميل نموذج الذكاء الاصطناعي YOLOv8 (Model Loading)
# =============================================================================
MODEL_PATH = config.MODEL_PATH
if not os.path.exists(MODEL_PATH) and os.path.exists("best.pt"):
    MODEL_PATH = "best.pt"

print(f"🚀 جارٍ تحميل نموذج الذكاء الاصطناعي من: {MODEL_PATH}")
model = YOLO(MODEL_PATH)
class_names = model.names
print(f"✅ تم تحميل النموذج بنجاح! الفئات المعرفة: {class_names}")


# =============================================================================
# 3. إدارة الحالة العامة للنظام (System State Machine)
# =============================================================================
class SystemState:
    """
    مخزن الحالة المركزي لكافة متغيرات وإحصائيات النظام.
    محمي بقفل تزامني (Threading Lock) لضمان سلامة البيانات بين كافة الخيوط.
    """
    def __init__(self):
        # عتبات كشف YOLO
        self.conf_threshold = config.YOLO_CONFIDENCE_DEFAULT
        self.iou_threshold = config.YOLO_IOU_THRESHOLD
        
        # إعدادات الكاميرا الحالية
        self.camera_active = True
        self.camera_index = config.DEFAULT_CAMERA_INDEX
        self.current_source = config.DEFAULT_CAMERA_SOURCE  # webcam, ipcam, usb_typec, esp32cam, video
        self.ip_cam_url = config.DEFAULT_IP_CAM_URL
        self.video_file_path = None
        self.distance_threshold = 50.0  # عتبة مسافة رصد الزجاجة (بالسنتيمتر)
        
        # وضع التشغيل: True = آلي كامل (AUTO)، False = يدوي (MANUAL)
        self.auto_mode = config.AUTO_MODE
        
        # الإحصائيات الحيوية للإنتاج
        self.total_frames = 0
        self.fps = 0.0
        self.total_inspections = 0
        self.good_bottles = 0
        self.defective_bottles = 0
        self.review_bottles = 0
        self.defect_counts = {
            "cap missing": 0,       # عداد عيوب غياب الغطاء
            "damaged plastic": 0,   # عداد عيوب كسر/انبعاج البلاستيك
            "label missing": 0      # عداد عيوب غياب الملصق
        }
        
        # أحدث قرار استدلال تم التوصل إليه
        self.current_decision = "READY"
        self.current_confidence = 0.0
        self.current_defect = None
        self.processing_time_ms = 0.0
        
        # قفل التزامن ومتغيرات بوابة الفحص
        self.lock = threading.Lock()
        self.alert_active = False
        self.bottle_in_station = False  # هل توجد زجاجة في محطة الفحص حالياً
        self.bottle_inspected = False   # هل تم فحص الزجاجة الحالية بالفعل لمنع التكرار

    def reset_stats(self):
        """إعادة تصفير كافة عدادات الإنتاج وسجلات الفحص."""
        with self.lock:
            self.total_inspections = 0
            self.good_bottles = 0
            self.defective_bottles = 0
            self.review_bottles = 0
            self.defect_counts = {
                "cap missing": 0,
                "damaged plastic": 0,
                "label missing": 0
            }
            self.current_decision = "READY"
            self.bottle_inspected = False
            inspection_db.clear()


state = SystemState()


# =============================================================================
# 4. مزامنة أحداث حساس الألتراسونيك (Ultrasonic Synchronization Callbacks)
# =============================================================================
def on_ultrasonic_bottle_detected():
    """تُستدعى فور رصد حساس المسافة لوصول زجاجة إلى حجرة الفحص."""
    print("🎯 [ULTRASONIC SYNC] وصلت زجاجة إلى محطة الفحص!")
    with state.lock:
        state.bottle_in_station = True
        state.bottle_inspected = False  # فتح بوابة الفحص لهذه الزجاجة الجديدة


def on_ultrasonic_bottle_cleared():
    """تُستدعى فور مغادرة الزجاجة لحجرة الفحص."""
    print("💨 [ULTRASONIC SYNC] غادرت الزجاجة محطة الفحص!")
    with state.lock:
        state.bottle_in_station = False
        state.bottle_inspected = False


# ربط الدوال التنبيهية بمدير الاتصال التسلسلي
esp32.serial_manager.on_bottle_detected_cb = on_ultrasonic_bottle_detected
esp32.serial_manager.on_bottle_cleared_cb = on_ultrasonic_bottle_cleared


# =============================================================================
# 5. خيط التليمتري اللحظي عبر المقابس (Real-time Telemetry WebSocket Thread)
# =============================================================================
def telemetry_thread():
    """
    خيط خلفي دائم يبث تحديثات الحساسات والـ KPIs عبر WebSockets بتردد 20Hz (كل 50ms)
    لتحديث راسم الإشارة، العدادات، والرسوم البيانية في لوحة التحكم بسلاسة تامة.
    """
    while True:
        try:
            with state.lock:
                total = state.good_bottles + state.defective_bottles + state.review_bottles
                pass_rate = round((state.good_bottles / total * 100), 1) if total > 0 else 100.0
                hw_status = esp32.get_status()
                
                data = {
                    "fps": state.fps,
                    "total_inspections": total,
                    "good_bottles": state.good_bottles,
                    "defective_bottles": state.defective_bottles,
                    "review_bottles": state.review_bottles,
                    "pass_rate": pass_rate,
                    "defect_counts": state.defect_counts,
                    "alert_active": state.alert_active,
                    "conf_threshold": state.conf_threshold,
                    "current_source": state.current_source,
                    "camera_index": state.camera_index,
                    "ip_cam_url": state.ip_cam_url,
                    "auto_mode": state.auto_mode,
                    "current_decision": state.current_decision,
                    "current_confidence": state.current_confidence,
                    "current_defect": state.current_defect,
                    "processing_time_ms": state.processing_time_ms,
                    "bottle_in_station": state.bottle_in_station,
                    "distance_threshold": state.distance_threshold,
                    "hardware": hw_status,
                }
            socketio.emit('telemetry_update', data)
        except Exception as e:
            print(f"Telemetry broadcast error: {e}")
        time.sleep(0.05)  # 20Hz refresh rate


threading.Thread(target=telemetry_thread, daemon=True).start()


# =============================================================================
# 6. فئة معالجة الفيديو والكاميرات (Video Processing & Camera Engine)
# =============================================================================
class VideoCamera:
    """
    محرك إدارة تدفق الفيديو وتحليل الإطارات بواسطة YOLOv8.
    يدعم التبديل اللحظي بين الكاميرات وتوليد شاشات بديلة أنيقة في حال انقطاع البث.
    """
    def __init__(self):
        self.cap = None
        self.is_running = False
        self.last_open_attempt = 0
        self.last_frame_bytes = None
        self.last_annotated_frame = None
        self.open_camera()

    def open_camera(self):
        """محاولة فتح مصدر الكاميرا المختار بدقة واحترافية."""
        self.last_open_attempt = time.time()
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            
        try:
            # 1. كاميرا الويب المحلية أو منفذ USB Type-C
            if state.current_source in ["webcam", "usb_typec"]:
                self.cap = cv2.VideoCapture(state.camera_index)
                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(state.camera_index, cv2.CAP_DSHOW)

            # 2. كاميرا الشبكة IP-Cam أو وحدة ESP32-CAM
            elif state.current_source in ["ipcam", "esp32cam"] and state.ip_cam_url:
                url = normalize_digits(state.ip_cam_url.strip())
                if not url.startswith(('http://', 'https://', 'rtsp://')):
                    url = 'http://' + url
                if state.current_source == "esp32cam":
                    if not any(url.endswith(p) for p in ["/stream", "/capture", "/video", ":81/stream"]):
                        url = url.rstrip('/') + "/stream"
                elif ":8080" in url and not url.endswith(("/video", "/shot.jpg", "/videofeed")):
                    url = url.rstrip('/') + "/video"
                state.ip_cam_url = url
                src_name = "ESP32-CAM" if state.current_source == "esp32cam" else "كاميرا الهاتف"
                print(f"📡 محاولة الاتصال بـ {src_name}: {url}")

                # إذا كانت ESP32-CAM تعمل بنمط اللقطة الفورية (/capture)
                if state.current_source == "esp32cam" and "/capture" in url:
                    if self.cap is not None:
                        try:
                            self.cap.release()
                        except Exception:
                            pass
                    self.cap = None
                    self.is_running = True
                else:
                    # نمط البث الحي المتدفق MJPEG
                    if self.cap is not None:
                        try:
                            self.cap.release()
                        except Exception:
                            pass
                    self.cap = cv2.VideoCapture(url)
                    try:
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # تقليل التخزين المؤقت لتجنب التأخير
                    except Exception:
                        pass
                    self.is_running = self.cap.isOpened()

            # 3. نمط ملف فيديو مسجل
            elif state.current_source == "video" and state.video_file_path:
                self.cap = cv2.VideoCapture(state.video_file_path)
        except Exception as e:
            print(f"⚠️ خطأ أثناء فتح الكاميرا: {e}")
            self.cap = None
            
        if not (state.current_source == "esp32cam" and "/capture" in (state.ip_cam_url or "")):
            self.is_running = self.cap.isOpened() if self.cap is not None else False
        print(f"📷 حالة الكاميرا ({state.current_source} - index {state.camera_index}): {'متصلة ✅' if self.is_running else 'غير متصلة ❌'}")

    def create_placeholder_frame(self, title, subtitle):
        """توليد كادر رسومي أنيق عند انقطاع الكاميرا أو محاولة إعادة الاتصال."""
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        blank[:] = (20, 24, 35)  # خلفية داكنة صناعية
        cv2.rectangle(blank, (20, 20), (620, 460), (45, 55, 75), 2)
        cv2.putText(blank, title, (50, 220), cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 200, 255), 2)
        cv2.putText(blank, subtitle, (50, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (160, 180, 200), 1)
        _, jpeg = cv2.imencode('.jpg', blank)
        raw_b = jpeg.tobytes()
        self.last_frame_bytes = raw_b
        return raw_b

    def get_frame(self):
        """
        قلب معالجة الرؤية الحاسوبية:
          1. التقاط الإطار من الكاميرا النشطة.
          2. تشغيل استدلال YOLOv8 لاكتشاف الزجاجات وعيوبها.
          3. مطابقة المسافة عبر حساس الألتراسونيك (Ultrasonic Interlock Gate).
          4. تسجيل عملية الفحص واتخاذ قرار الرفض أو القبول الآلي.
          5. رسم مربعات الكشف وشريط الحالة الصناعي وتحويل الإطار إلى JPEG.
        """
        if state.current_source == "phone_stream":
            time.sleep(0.05)
            return self.create_placeholder_frame("Phone Browser Mode Active", "Streaming directly from Phone Browser")

        start_time = time.time()
        success = False
        frame = None

        # ---------------------------------------------------------------------
        # نمط التقاط الصور الفورية لوحدة ESP32-CAM عبر مسار (/capture)
        # ---------------------------------------------------------------------
        if state.current_source == "esp32cam" and "/capture" in (state.ip_cam_url or ""):
            if not self.is_running and (time.time() - self.last_open_attempt < 3.5):
                time.sleep(0.08)
                return self.create_placeholder_frame("Connecting to ESP32-CAM Snapshot...", f"URL: {state.ip_cam_url}")
            try:
                self.last_open_attempt = time.time()
                req = urllib.request.Request(
                    state.ip_cam_url,
                    headers={'User-Agent': 'Mozilla/5.0', 'Connection': 'close'}
                )
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    arr = np.asarray(bytearray(resp.read()), dtype=np.uint8)
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    success = frame is not None
                    self.is_running = success
            except Exception as e:
                success = False
                frame = None
                self.is_running = False

        # ---------------------------------------------------------------------
        # نمط تدفق الفيديو القياسي (OpenCV VideoCapture)
        # ---------------------------------------------------------------------
        else:
            if not self.is_running or self.cap is None or not self.cap.isOpened():
                if time.time() - self.last_open_attempt > 4.5:
                    self.open_camera()
                if not self.is_running:
                    time.sleep(0.08)
                    if state.current_source == "ipcam":
                        return self.create_placeholder_frame("Connecting to IP Camera...", f"URL: {state.ip_cam_url or 'Not set'}")
                    elif state.current_source == "esp32cam":
                        return self.create_placeholder_frame("Connecting to ESP32-CAM Stream...", f"URL: {state.ip_cam_url or 'Not set'}")
                    elif state.current_source == "usb_typec":
                        return self.create_placeholder_frame("USB Type-C Camera Offline", "Please connect phone via Type-C and select port")
                    else:
                        return self.create_placeholder_frame("No PC Webcam Connected", "Switch to (IP Cam) or (USB Type-C) tab above")

            try:
                success, frame = self.cap.read()
                if not success or frame is None:
                    if self.cap is not None:
                        try:
                            self.cap.release()
                        except Exception:
                            pass
                    self.cap = None
                    self.is_running = False
            except Exception as e:
                if self.cap is not None:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                self.cap = None
                self.is_running = False
                success = False
                frame = None

        # في حال عدم التمكن من قراءة الإطار
        if not success or frame is None:
            time.sleep(0.05)
            if state.current_source == "ipcam":
                return self.create_placeholder_frame("Connecting to Phone IP Stream...", f"URL: {state.ip_cam_url}")
            elif state.current_source == "esp32cam":
                return self.create_placeholder_frame("Waiting for ESP32-CAM Stream...", f"URL: {state.ip_cam_url}")
            elif state.current_source == "usb_typec":
                return self.create_placeholder_frame("Waiting for USB Type-C Stream...", "Check if DroidCam/Iriun is active on phone")
            else:
                return self.create_placeholder_frame("Camera Disconnected", "Please check camera connection")

        # ---------------------------------------------------------------------
        # 1. تشغيل استدلال YOLOv8 على الإطار (AI Vision Inference)
        # ---------------------------------------------------------------------
        inference_start = time.time()
        results = model.predict(
            source=frame,
            conf=state.conf_threshold,
            iou=state.iou_threshold,
            verbose=False
        )
        proc_time_ms = (time.time() - inference_start) * 1000.0
        state.processing_time_ms = round(proc_time_ms, 1)

        # ---------------------------------------------------------------------
        # 2. التحقق من وجود الزجاجة عبر حساس الألتراسونيك (Ultrasonic Interlock Gate)
        # ---------------------------------------------------------------------
        current_hw_dist = esp32.get_distance()
        is_bottle_present = state.bottle_in_station or (1.0 < current_hw_dist <= state.distance_threshold)

        boxes = results[0].boxes
        inspection = decision_engine.evaluate(boxes, class_names, processing_time_ms=proc_time_ms)
        
        if not is_bottle_present:
            # لا توجد زجاجة في المحطة أمام الحساس -> وضع الاستعداد وتصفير الفحص
            state.bottle_inspected = False
            state.current_decision = "STANDBY"
            state.current_confidence = 0.0
            state.current_defect = None
        else:
            # توجد زجاجة داخل محطة الفحص!
            state.current_decision = inspection.decision
            state.current_confidence = round(float(inspection.confidence) * 100, 1)
            state.current_defect = inspection.defect_type

            # -----------------------------------------------------------------
            # 3. فحص لمرة واحدة فقط لكل زجاجة قادمة (One-Shot Inspection per Bottle)
            # -----------------------------------------------------------------
            if not state.bottle_inspected and inspection.decision in ["PASS", "FAIL", "REVIEW"]:
                state.bottle_inspected = True  # إغلاق البوابة حتى تعبر الزجاجة الحالية

                # تسجيل العملية في قاعدة البيانات
                inspection_db.log(
                    decision=inspection.decision,
                    confidence=inspection.confidence,
                    primary_class=inspection.primary_class,
                    defect_type=inspection.defect_type,
                    camera_source=state.current_source,
                    processing_time_ms=proc_time_ms
                )
                
                with state.lock:
                    if inspection.decision == "PASS":
                        state.good_bottles += 1
                        state.alert_active = False
                    elif inspection.decision == "FAIL":
                        state.defective_bottles += 1
                        state.alert_active = True
                        if inspection.defect_type in state.defect_counts:
                            state.defect_counts[inspection.defect_type] += 1
                    elif inspection.decision == "REVIEW":
                        state.review_bottles += 1
                        state.alert_active = False

                    state.total_inspections = state.good_bottles + state.defective_bottles + state.review_bottles

                # إرسال إشارة التحكم للعتاد في الوضع الآلي (Auto Mode Actuation)
                if state.auto_mode:
                    if inspection.decision == "PASS":
                        esp32.actuate_pass()
                    elif inspection.decision == "FAIL":
                        esp32.actuate_fail()
                    elif inspection.decision == "REVIEW":
                        esp32.actuate_review()

        # ---------------------------------------------------------------------
        # 4. رسم مربعات التحديد والشريط الإرشادي العلوي على الصورة
        # ---------------------------------------------------------------------
        annotated_frame = results[0].plot()

        process_time = time.time() - start_time
        current_fps = 1.0 / process_time if process_time > 0 else 30.0
        state.fps = round(current_fps, 1)

        # تحديد لون ونصوص شريط الحالة
        if not is_bottle_present:
            status_text = "STANDBY: WAITING FOR BOTTLE"
            status_color = (180, 180, 180)
        elif state.current_decision == "FAIL":
            status_text = f"DECISION: FAIL ({state.current_defect})"
            status_color = (0, 0, 255)
        elif state.current_decision == "PASS":
            status_text = "DECISION: PASS (COMPLIANT)"
            status_color = (0, 255, 0)
        elif state.current_decision == "REVIEW":
            status_text = "DECISION: REVIEW (LOW CONFIDENCE)"
            status_color = (255, 180, 0)
        else:
            status_text = "STATUS: STANDBY / READY"
            status_color = (180, 180, 180)
        
        cv2.rectangle(annotated_frame, (10, 10), (370, 60), (20, 20, 20), -1)
        cv2.rectangle(annotated_frame, (10, 10), (370, 60), status_color, 2)
        cv2.putText(annotated_frame, status_text, (18, 33), 
                    cv2.FONT_HERSHEY_DUPLEX, 0.52, status_color, 1)
        src_label = "USB Type-C" if state.current_source == "usb_typec" else (
            "Phone IP Cam" if state.current_source == "ipcam" else (
                "ESP32-CAM [Snapshot]" if (state.current_source == "esp32cam" and "/capture" in (state.ip_cam_url or "")) else (
                    "ESP32-CAM [Stream]" if state.current_source == "esp32cam" else "PC Webcam"
                )
            )
        )
        cv2.putText(annotated_frame, f"FPS: {state.fps} | {src_label} | {state.processing_time_ms}ms", 
                    (18, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 220, 220), 1)

        # ضغط الصورة بتنسيق JPEG لإرسالها عبر الشبكة
        _, jpeg = cv2.imencode('.jpg', annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        frame_bytes = jpeg.tobytes()
        self.last_frame_bytes = frame_bytes
        self.last_annotated_frame = annotated_frame
        return frame_bytes


camera = VideoCamera()


# =============================================================================
# 7. محرك البث المباشر لبرنامج LabVIEW (LabVIEW Picture & Vision Bridge)
# =============================================================================
def _create_initial_labview_frame():
    """إنشاء صورة بدائية في مسار C:/SmartBottle حتى لا يظهر الخطأ Error 7 في LabVIEW عند أول تشغيل."""
    try:
        os.makedirs("C:/SmartBottle", exist_ok=True)
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        blank[:] = (20, 24, 35)
        cv2.putText(blank, "SmartBottle SCADA - Initializing...", (40, 240),
                    cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 200, 255), 2)
        _, jpeg = cv2.imencode('.jpg', blank)
        with open("C:/SmartBottle/labview_live.jpg", "wb") as f:
            f.write(jpeg.tobytes())
        _, bmp = cv2.imencode('.bmp', blank)
        with open("C:/SmartBottle/labview_live.bmp", "wb") as f_bmp:
            f_bmp.write(bmp.tobytes())
    except Exception:
        pass


_create_initial_labview_frame()


def _labview_streamer():
    """
    خيط خلفي دائم لتحديث ملف الصورة المشترك لـ LabVIEW:
    يستخدم تقنية الاستبدال الذري (Atomic Replacement via Temp File)
    لمنع حدوث تعارض في قفل الملفات (File Lock Collision) مع حلقات LabVIEW.
    """
    time.sleep(1.0)
    temp_p = "C:/SmartBottle/.temp_frame.jpg"
    final_p = "C:/SmartBottle/labview_live.jpg"
    temp_bmp = "C:/SmartBottle/.temp_frame.bmp"
    final_bmp = "C:/SmartBottle/labview_live.bmp"
    
    while True:
        try:
            raw = camera.last_frame_bytes
            if not raw:
                raw = camera.get_frame()
            if raw:
                # تحديث ملف JPEG
                with open(temp_p, "wb") as f_tmp:
                    f_tmp.write(raw)
                try:
                    os.replace(temp_p, final_p)
                except PermissionError:
                    pass
                except Exception:
                    pass

            # تحديث ملف BMP غير المضغوط المتوافق مع بلوك (Read BMP File.vi) في LabVIEW
            ann = getattr(camera, 'last_annotated_frame', None)
            if ann is not None:
                _, bmp_bytes = cv2.imencode('.bmp', ann)
                with open(temp_bmp, "wb") as f_b:
                    f_b.write(bmp_bytes.tobytes())
                try:
                    os.replace(temp_bmp, final_bmp)
                except PermissionError:
                    pass
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.10)  # تحديث كل 100ms ليطابق مؤقت حلقة LabVIEW


threading.Thread(target=_labview_streamer, daemon=True).start()


def gen(cam):
    """مولد تدفق الفيديو بصيغة MJPEG لمتصفحات الويب."""
    while True:
        frame = cam.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        time.sleep(0.01)


# =============================================================================
# 8. مسارات واجهات برمجة التطبيقات (Flask HTTP REST Endpoints)
# =============================================================================
@app.after_request
def add_cache_headers(response):
    """إلغاء التخزين المؤقت (Cache) لضمان وصول أحدث البيانات اللحظية دائماً."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/labview_cam')
def labview_cam():
    """صفحة كاميرا فائقة الخفة مخصصة لمتصفح LabVIEW الداخلي (WebBrowser / IWebBrowser2)."""
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; background: #0b0f19; overflow: hidden; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
  img { max-width: 100%; max-height: 100%; object-fit: contain; }
</style>
</head>
<body>
<img id="lv" src="/api/labview/snapshot.jpg" alt="SmartBottle Live Feed">
<script>
  var img = document.getElementById('lv');
  setInterval(function() {
    img.src = '/api/labview/snapshot.jpg?t=' + (new Date()).getTime();
  }, 90);
</script>
</body>
</html>
"""


@app.route('/')
def index():
    """الصفحة الرئيسية للوحة تحكم SCADA الصناعية المتكاملة."""
    return render_template('index.html')


@app.route('/inspector')
def inspector():
    """استوديو الفحص والتحليل اليدوي واللقطات الفورية."""
    return render_template('inspector.html')


@app.route('/video_feed')
def video_feed():
    """مسار تدفق الفيديو المباشر للكاميرا بصيغة MJPEG."""
    return Response(gen(camera),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/api/stats')
def get_stats():
    """استرجاع لقطة JSON شاملة لكافة إحصائيات الإنتاج، الحساسات، والعتاد."""
    with state.lock:
        total = state.good_bottles + state.defective_bottles + state.review_bottles
        pass_rate = round((state.good_bottles / total * 100), 1) if total > 0 else 100.0
        hw_status = esp32.get_status()
        recent_logs = inspection_db.get_recent(15)
        
        return jsonify({
            "fps": state.fps,
            "total_inspections": total,
            "good_bottles": state.good_bottles,
            "defective_bottles": state.defective_bottles,
            "review_bottles": state.review_bottles,
            "pass_rate": pass_rate,
            "defect_counts": state.defect_counts,
            "alert_active": state.alert_active,
            "conf_threshold": state.conf_threshold,
            "current_source": state.current_source,
            "camera_index": state.camera_index,
            "ip_cam_url": state.ip_cam_url,
            "auto_mode": state.auto_mode,
            "current_decision": state.current_decision,
            "current_confidence": state.current_confidence,
            "current_defect": state.current_defect,
            "processing_time_ms": state.processing_time_ms,
            "bottle_in_station": state.bottle_in_station,
            "distance_threshold": state.distance_threshold,
            "hardware": hw_status,
            "logs": recent_logs
        })


@app.route('/api/scan_cameras')
def scan_cameras():
    """فحص منافذ كاميرات الويب المتاحة محلياً في نظام التشغيل (من 0 إلى 4)."""
    available = []
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                label = f"منفذ الكاميرا {i}"
                if i == 0: label += " (الأساسية / المدمجة)"
                elif i == 1: label += " (كاميرا Type-C الأولى)"
                elif i == 2: label += " (كاميرا Type-C الثانية)"
                available.append({"index": i, "label": label})
            cap.release()
    return jsonify({"cameras": available, "count": len(available)})


@app.route('/api/update_settings', methods=['POST'])
def update_settings():
    """تحديث إعدادات النظام الحية (عتبات الثقة، الكاميرا، وضع التشغيل)."""
    data = request.json or {}
    if 'conf_threshold' in data:
        state.conf_threshold = float(data['conf_threshold'])
    if 'auto_mode' in data:
        state.auto_mode = bool(data['auto_mode'])
    if 'distance_threshold' in data:
        try:
            val = float(data['distance_threshold'])
            if 5.0 <= val <= 200.0:
                state.distance_threshold = val
                esp32.send_command(f"THRESHOLD:{val}")
        except Exception:
            pass
    if 'source_type' in data:
        state.current_source = data['source_type']
        if data['source_type'] in ['ipcam', 'esp32cam'] and 'ip_url' in data:
            clean_url = normalize_digits(data['ip_url'].strip())
            state.ip_cam_url = clean_url
        elif data['source_type'] in ['webcam', 'usb_typec'] and 'camera_index' in data:
            state.camera_index = int(data['camera_index'])
        camera.open_camera()
    return jsonify({
        "status": "success",
        "source": state.current_source,
        "ip_url": state.ip_cam_url,
        "camera_index": state.camera_index,
        "auto_mode": state.auto_mode,
        "distance_threshold": state.distance_threshold
    })


@app.route('/api/mode', methods=['POST', 'GET'])
def toggle_mode():
    """التبديل بين وضع التشغيل الآلي (AUTO) واليدوي (MANUAL)."""
    if request.method == 'POST':
        data = request.json or {}
        if 'auto_mode' in data:
            state.auto_mode = bool(data['auto_mode'])
        else:
            state.auto_mode = not state.auto_mode
    return jsonify({
        "status": "success",
        "auto_mode": state.auto_mode,
        "mode_label": "AUTO" if state.auto_mode else "MANUAL"
    })


# =============================================================================
# 9. مسارات التحكم بالعتاد عبر الويب (ESP32 Hardware APIs)
# =============================================================================
@app.route('/api/hardware/status', methods=['GET'])
def get_hardware_status():
    """استرجاع حالة كافة عناصر العتاد الموصلة."""
    status = esp32.get_status()
    return jsonify(status)


@app.route('/api/hardware/distance', methods=['GET'])
def get_hardware_distance():
    """استرجاع قراءة المسافة اللحظية من حساس الألتراسونيك."""
    dist = esp32.get_distance()
    return jsonify({"distance_cm": dist, "unit": "cm"})


@app.route('/api/hardware/command', methods=['POST'])
def send_hardware_command():
    """إرسال أمر نصي مباشر إلى متحكم ESP32."""
    data = request.json or {}
    cmd = data.get("command", "")
    if not cmd:
        return jsonify({"error": "No command provided"}), 400
    res = esp32.serial_manager.send_command(cmd)
    return jsonify(res)


@app.route('/api/hardware/motor', methods=['POST', 'GET'])
def control_motor():
    """التحكم بتشغيل وإيقاف محرك السير الناقل."""
    data = request.json if request.is_json else {}
    action = request.args.get("action", data.get("action", "")).lower()
    state_val = data.get("state", None)

    if action == "on" or state_val is True:
        res = esp32.motor_on()
    elif action == "off" or state_val is False:
        res = esp32.motor_off()
    else:
        return jsonify({"error": "Invalid motor action. Use 'on' or 'off'"}), 400
    return jsonify(res)


@app.route('/api/hardware/servo', methods=['POST', 'GET'])
def control_servo():
    """التحكم بذراع محرك السيرفو لطرد الزجاجات أو فتح المسار."""
    data = request.json if request.is_json else {}
    action = request.args.get("action", data.get("action", "")).lower()
    custom_angle = request.args.get("angle", data.get("angle", None))
    if custom_angle is not None:
        try:
            custom_angle = int(custom_angle)
        except Exception:
            custom_angle = getattr(config, "SERVO_REJECT_ANGLE", 90)

    if action in ["reject", "fail"]:
        res = esp32.servo_reject(angle=custom_angle)
    elif action in ["home", "pass"]:
        res = esp32.servo_home()
    elif action in ["set", "angle"] and custom_angle is not None:
        res = esp32.set_servo_angle(custom_angle)
    else:
        return jsonify({"error": "Invalid servo action. Use 'reject', 'home', or 'set'"}), 400
    return jsonify(res)


@app.route('/api/hardware/led', methods=['POST', 'GET'])
def control_led():
    """التحكم بليدات الحالة الصناعية (Green, Red, Blue, Off)."""
    data = request.json if request.is_json else {}
    color = request.args.get("color", data.get("color", "off")).lower()
    res = esp32.set_led(color)
    return jsonify(res)


@app.route('/api/hardware/buzzer', methods=['POST', 'GET'])
def control_buzzer():
    """إطلاق نغمة الإنذار الصوتي عبر صافرة التنبيه."""
    data = request.json if request.is_json else {}
    duration = int(request.args.get("duration_ms", data.get("duration_ms", 200)))
    res = esp32.trigger_buzzer(duration)
    return jsonify(res)


@app.route('/api/hardware/relay', methods=['POST', 'GET'])
def control_relay():
    """التحكم بريليه إضاءة صندوق الفحص الصناعي (GPIO 25)."""
    data = request.json if request.is_json else {}
    action = request.args.get("action", data.get("action", "")).lower()
    if action == "on":
        res = esp32.relay_on()
    elif action == "off":
        res = esp32.relay_off()
    else:
        return jsonify({"error": "Invalid relay action. Use 'on' or 'off'"}), 400
    return jsonify(res)


@app.route('/api/hardware/reset', methods=['POST', 'GET'])
def reset_hardware():
    """إعادة تعيين كافة مشغلات العتاد إلى وضع الجاهزية الافتراضي."""
    res = esp32.reset()
    return jsonify(res)


# =============================================================================
# 10. نقاط تكامل برنامج LabVIEW الصناعي (LabVIEW Dedicated Endpoints)
# =============================================================================
@app.route('/api/labview/telemetry', methods=['GET'])
def get_labview_telemetry():
    """
    مسار مخصص لبرنامج LabVIEW يرجع كائن JSON مسطح تماماً (Flat JSON)،
    مصمم خصيصاً ليتطابق مع بلوك (Unflatten From JSON.vi) بدون مصفوفات معقدة.
    """
    with state.lock:
        total = state.good_bottles + state.defective_bottles + state.review_bottles
        pass_rate = round((state.good_bottles / total * 100), 1) if total > 0 else 100.0
        hw = esp32.get_status()
        raw_dist = hw.get("distance_cm")
        dist = float(raw_dist) if (raw_dist is not None and raw_dist != "") else 999.0

        cap_m = int(state.defect_counts.get("cap missing", 0))
        dmg_p = int(state.defect_counts.get("damaged plastic", 0))
        lbl_m = int(state.defect_counts.get("label missing", 0))
        is_bot = bool(state.bottle_in_station or (dist <= state.distance_threshold and dist > 1.0))
        is_esp = hw.get("esp32") == "ONLINE"

        return jsonify({
            "fps": round(float(state.fps), 1),
            "total": int(total),
            "good": int(state.good_bottles),
            "defective": int(state.defective_bottles),
            "pass_rate": float(pass_rate),
            "quality_rate": float(pass_rate),
            "cap_missing": cap_m,
            "cap missing": cap_m,
            "damaged_plastic": dmg_p,
            "damaged plastic": dmg_p,
            "damaged_body": dmg_p,
            "damaged body": dmg_p,
            "label_missing": lbl_m,
            "label missing": lbl_m,
            "distance_cm": round(dist, 1),
            "distance": round(dist, 1),
            "confidence": round(float(state.current_confidence), 1),
            "is_pass": state.current_decision == "PASS",
            "is_fail": state.current_decision == "FAIL",
            "esp32_online": is_esp,
            "bottle_present": is_bot,
            "bottle_in_station": is_bot
        })


@app.route('/api/labview/snapshot.jpg', methods=['GET'])
def get_labview_snapshot():
    """
    استرجاع أحدث إطار معالج كصورة JPEG ثنائية خام مباشرة
    لتغذية بلوكات الرؤية في LabVIEW Vision / Picture Control.
    """
    try:
        frame_bytes = camera.last_frame_bytes
        if not frame_bytes:
            frame_bytes = camera.get_frame()
        resp = Response(frame_bytes, mimetype='image/jpeg')
        resp.headers['Content-Disposition'] = 'inline; filename="snapshot.jpg"'
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return resp
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
# 11. مسارات استوديو الفحص وتصدير التقارير (Reports & Image Uploads)
# =============================================================================
@app.route('/api/upload_image', methods=['POST'])
def upload_image():
    """فحص صورة زجاجة يدوية مرفوعة من المستخدم وتطبيق استدلال YOLO عليها."""
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400
    file = request.files['image']
    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    t0 = time.time()
    results = model.predict(source=img, conf=state.conf_threshold)
    proc_time_ms = (time.time() - t0) * 1000.0
    annotated = results[0].plot()
    
    boxes = results[0].boxes
    inspection = decision_engine.evaluate(boxes, class_names, processing_time_ms=proc_time_ms)
    
    # تسجيل في السجل
    if inspection.decision in ["PASS", "FAIL", "REVIEW"]:
        inspection_db.log(
            decision=inspection.decision,
            confidence=inspection.confidence,
            primary_class=inspection.primary_class,
            defect_type=inspection.defect_type,
            camera_source="image_upload",
            processing_time_ms=proc_time_ms
        )
        if state.auto_mode:
            if inspection.decision == "PASS": esp32.actuate_pass()
            elif inspection.decision == "FAIL": esp32.actuate_fail()
            elif inspection.decision == "REVIEW": esp32.actuate_review()

    _, jpeg = cv2.imencode('.jpg', annotated)
    b64_img = base64.b64encode(jpeg).decode('utf-8')
    
    return jsonify({
        "image_base64": f"data:image/jpeg;base64,{b64_img}",
        "decision": inspection.decision,
        "confidence": round(float(inspection.confidence) * 100, 1),
        "defect_type": inspection.defect_type,
        "detections": inspection.all_detections,
        "total_detected": len(inspection.all_detections)
    })


@app.route('/api/capture_and_inspect', methods=['POST'])
def capture_and_inspect():
    """التقاط إطار فوري مفرد من الكاميرا النشطة وفحصه بالذكاء الاصطناعي."""
    frame = None
    # محاولة الالتقاط من ESP32-CAM إن كانت مختارة
    if state.current_source == "esp32cam":
        try:
            capture_url = state.ip_cam_url.replace("/stream", "/capture") if "/stream" in (state.ip_cam_url or "") else state.ip_cam_url
            req = urllib.request.Request(capture_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                arr = np.asarray(bytearray(resp.read()), dtype=np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"ESP32-CAM capture failed: {e}")
            pass
            
    # بديل: القراءة من الكاميرا المحلية
    if frame is None and camera.cap is not None and camera.cap.isOpened():
        ret, frame = camera.cap.read()
        if not ret: frame = None
            
    if frame is None:
        return jsonify({"error": "Could not capture a frame from the current camera source."}), 500

    t0 = time.time()
    results = model.predict(source=frame, conf=state.conf_threshold)
    proc_time_ms = (time.time() - t0) * 1000.0
    annotated = results[0].plot()
    
    boxes = results[0].boxes
    inspection = decision_engine.evaluate(boxes, class_names, processing_time_ms=proc_time_ms)
    
    if inspection.decision in ["PASS", "FAIL", "REVIEW"]:
        inspection_db.log(
            decision=inspection.decision,
            confidence=inspection.confidence,
            primary_class=inspection.primary_class,
            defect_type=inspection.defect_type,
            camera_source="esp32cam_capture" if state.current_source == "esp32cam" else state.current_source,
            processing_time_ms=proc_time_ms
        )
        if state.auto_mode:
            if inspection.decision == "PASS": esp32.actuate_pass()
            elif inspection.decision == "FAIL": esp32.actuate_fail()
            elif inspection.decision == "REVIEW": esp32.actuate_review()

    _, jpeg = cv2.imencode('.jpg', annotated)
    b64_img = base64.b64encode(jpeg).decode('utf-8')
    
    return jsonify({
        "image_base64": f"data:image/jpeg;base64,{b64_img}",
        "decision": inspection.decision,
        "confidence": round(float(inspection.confidence) * 100, 1),
        "defect_type": inspection.defect_type,
        "detections": inspection.all_detections,
        "total_detected": len(inspection.all_detections),
        "processing_time_ms": round(proc_time_ms, 1)
    })


@app.route('/api/reset_stats', methods=['POST'])
def reset_stats():
    """مسار إعادة تعيين العدادات الإحصائية."""
    state.reset_stats()
    return jsonify({"status": "success"})


@app.route('/api/export_csv')
def export_csv():
    """تنزيل تقرير الفحص الشامل بصيغة CSV."""
    csv_content = inspection_db.export_csv_stream()
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=smart_bottle_inspection_report.csv"}
    )


# =============================================================================
# 12. نقطة انطلاق التطبيق الرئيسية (Main Application Entrypoint)
# =============================================================================
if __name__ == '__main__':
    print("=============================================================")
    print("🍾 نظام الفحص الذكي للزجاجات SmartBottle™ AI SCADA يعمل الآن!")
    print("🌐 الواجهة المحلية: http://127.0.0.1:5000")
    print("📱 الشبكة المحلية: http://0.0.0.0:5000")
    print("=============================================================")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
