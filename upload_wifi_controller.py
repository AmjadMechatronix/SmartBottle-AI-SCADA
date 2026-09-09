"""
=============================================================================
Smart Bottle Inspection - Dedicated Wi-Fi Controller Firmware Uploader
=============================================================================
Uploads esp32_wifi_controller/main.py directly to ESP32 board using mpremote.
=============================================================================
"""

import sys
import os
import subprocess
import time
import serial.tools.list_ports

sys.stdout.reconfigure(encoding='utf-8')

print("=============================================================")
print("🌐 ESP32 WIRELESS NETWORK CONTROLLER UPLOADER")
print("=============================================================")

# 1. Detect connected serial ports
ports = [p.device for p in serial.tools.list_ports.comports()]
print(f"🔍 Detected Serial Ports: {ports}")

if not ports:
    print("❌ No serial ports found. Please connect your ESP32 controller board via USB.")
    sys.exit(1)

# Pick target port (or ask / detect)
target_port = ports[0] if len(ports) == 1 else None
if not target_port:
    print("\n⚠️ Multiple COM ports detected:")
    for i, p in enumerate(ports):
        print(f"   [{i+1}] {p}")
    print(f"👉 Target port defaulted to: {ports[0]}")
    target_port = ports[0]

firmware_file = os.path.join("esp32_wifi_controller", "main.py")
if not os.path.exists(firmware_file):
    print(f"❌ Firmware file not found: {firmware_file}")
    sys.exit(1)

print(f"🎯 Target Port: {target_port}")
print(f"📄 Firmware file: {firmware_file}")
print("🚀 Uploading wireless firmware to ESP32 (:main.py)...")
print("⚠️ Reminder: Please make sure Thonny IDE is closed.")

cmd = [sys.executable, "-m", "mpremote", "connect", target_port, "fs", "cp", firmware_file, ":main.py"]
try:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if res.returncode == 0:
        print("✅ Firmware uploaded successfully to ESP32!")
        print("🔄 Resetting ESP32 to boot into Wi-Fi mode...")
        subprocess.run([sys.executable, "-m", "mpremote", "connect", target_port, "reset"], capture_output=True)
        print("🎉 ESP32 is now booting! Watch Thonny or console to see its allocated Wi-Fi IP address.")
    else:
        print(f"⚠️ Upload returned code {res.returncode}:")
        print(res.stderr or res.stdout)
        if "could not open port" in (res.stderr or "").lower() or "permissionerror" in (res.stderr or "").lower():
            print("💡 Reminder: Please close Thonny IDE or any serial monitor, then re-run this script.")
except Exception as e:
    print(f"❌ Error during upload: {e}")
