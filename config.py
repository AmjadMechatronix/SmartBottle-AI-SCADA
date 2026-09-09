"""
=============================================================================
Smart Bottle Inspection System - Global Configuration
=============================================================================
Centralized settings for AI, Camera, Decision Engine, and Hardware Integration.
"""

import os

# ==========================================
# 1. AI Vision & YOLO Settings
# ==========================================
MODEL_PATH = "best.pt"
YOLO_CONFIDENCE_DEFAULT = 0.35
YOLO_IOU_THRESHOLD = 0.45
YOLO_IMG_SIZE = 640

# Normal vs Defect Class Mapping
NORMAL_CLASSES = ["bottle", "cap", "label"]
DEFECT_CLASSES = ["cap missing", "damaged plastic", "label missing"]
CLASS_NAMES = {0: "bottle", 1: "cap", 2: "cap missing", 3: "damaged plastic", 4: "label", 5: "label missing"}

# Decision Engine Confidence Thresholds
CONFIDENCE_HIGH_THRESHOLD = 0.60   # >= 0.60 -> Definitive PASS / FAIL
CONFIDENCE_LOW_THRESHOLD = 0.30    # < 0.30 -> Discard as noise; between 0.30 and 0.60 -> REVIEW

# ==========================================
# 2. Camera Configuration
# ==========================================
# Supported sources: "webcam", "ipcam", "usb_typec", "esp32cam", "image"
DEFAULT_CAMERA_SOURCE = "esp32cam"
DEFAULT_CAMERA_INDEX = 0
DEFAULT_IP_CAM_URL = "http://192.168.0.133/stream"
ESP32_CAM_STREAM_URL = "http://192.168.0.133/stream"
ESP32_CAM_CAPTURE_URL = "http://192.168.0.133/capture"

# ==========================================
# 3. ESP32 Hardware & Serial Configuration
# ==========================================
SERIAL_PORT = "AUTO"             # "AUTO" to auto-detect ESP32 port, or "COM3", "COM4", etc.
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT = 1.0             # seconds
AUTO_RECONNECT_INTERVAL = 3.0   # seconds

# Wireless Network Controller Settings (MicroPython Wi-Fi REST API)
ESP32_CONTROLLER_IP = "http://192.168.0.134"  # Default IP for wireless controller
ESP32_COMM_MODE = "AUTO"                      # "WIFI", "SERIAL", or "AUTO"

# Conveyor & Servo Actuation Timing (in seconds)
SERVO_REJECT_ANGLE = 90        # Angle to push bottle to reject chute
SERVO_HOME_ANGLE = 0            # Normal conveyor pass position
REJECT_DURATION_SEC = 1.2       # Time servo stays in reject position
MOTOR_DEFAULT_RUNNING = True    # Keep conveyor running by default

# Ultrasonic Sensor Thresholds
BOTTLE_DETECT_DISTANCE_CM = 25.0 # Bottle considered present if distance <= 25.0 cm

# ==========================================
# 4. System Operating Modes
# ==========================================
AUTO_MODE = True                # In AUTO: Ultrasonic -> Capture -> YOLO -> Reject/Pass
