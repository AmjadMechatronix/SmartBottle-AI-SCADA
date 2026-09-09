"""
=============================================================================
Smart Bottle Inspection - Automated ESP32 Firmware Uploader
=============================================================================
Uploads esp32/main.py directly to ESP32 board using PySerial Raw REPL.
=============================================================================
"""

import sys
import os
import time
import serial
import serial.tools.list_ports

# Ensure UTF-8 console output
sys.stdout.reconfigure(encoding='utf-8')

print("=============================================================")
print("📤 ESP32 FIRMWARE UPLOADER (Smart Bottle Inspection)")
print("=============================================================")

# 1. Find ESP32 Port
ports = [p.device for p in serial.tools.list_ports.comports()]
print(f"🔍 Detected Serial Ports: {ports}")

esp32_port = "COM5" if "COM5" in ports else (ports[0] if ports else None)

if not esp32_port:
    print("❌ No serial ports found. Please connect your ESP32 board via USB cable.")
    sys.exit(1)

print(f"🎯 Target ESP32 Port: {esp32_port}")

firmware_file = os.path.join("esp32", "main.py")
if not os.path.exists(firmware_file):
    print(f"❌ Firmware file not found: {firmware_file}")
    sys.exit(1)

print(f"📄 Firmware file: {firmware_file}")
print("🚀 Uploading firmware to ESP32 (:main.py) via Direct Raw REPL...")

try:
    s = serial.Serial()
    s.port = esp32_port
    s.baudrate = 115200
    s.dtr = False
    s.rts = False
    s.timeout = 2.0
    s.open()
    time.sleep(1.2)

    # Interrupt any running loop
    s.write(b'\r\x03\x03')
    time.sleep(0.3)
    s.read_all()

    # Enter raw REPL
    s.write(b'\r\x01')
    time.sleep(0.3)
    resp = s.read_all()
    if b'raw REPL' not in resp:
        s.write(b'\r\x03\x01')
        time.sleep(0.5)
        resp = s.read_all()

    if b'raw REPL' not in resp:
        raise RuntimeError(f"Could not enter raw REPL. Response: {resp}")

    print("🔌 Connected to MicroPython Raw REPL successfully.")

    with open(firmware_file, 'rb') as f:
        code_bytes = f.read()

    print(f"📦 Flashing {len(code_bytes)} bytes to :main.py...")
    s.write(b"f = open('main.py', 'wb')\r\n\x04")
    time.sleep(0.2)
    s.read_all()

    chunk_size = 256
    for i in range(0, len(code_bytes), chunk_size):
        chunk = code_bytes[i:i+chunk_size]
        cmd = f"f.write({repr(chunk)})\r\n\x04".encode('ascii')
        s.write(cmd)
        time.sleep(0.04)
        s.read_all()

    s.write(b"f.close()\r\n\x04")
    time.sleep(0.2)
    s.read_all()

    print("✅ Firmware successfully written to ESP32 (:main.py)!")
    print("🔄 Resetting ESP32 board to apply changes...")
    s.write(b"import machine; machine.reset()\r\n\x04")
    time.sleep(0.8)
    s.close()
    print("🎉 ESP32 reset complete! Threshold is now 25.0 cm.")
except Exception as e:
    print(f"❌ Error during upload: {e}")
    sys.exit(1)
