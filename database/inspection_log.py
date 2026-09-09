"""
=============================================================================
Smart Bottle Inspection System - Inspection Log & Database
=============================================================================
Provides persistent structured logging for every bottle inspection event.
Supports in-memory querying, statistics aggregation, and CSV export.
=============================================================================
"""

import os
import csv
import io
import time
from datetime import datetime
import threading

class InspectionLogger:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(InspectionLogger, cls).__new__(cls)
                cls._instance.records = []
                cls._instance.counter = 0
            return cls._instance

    def log(self, decision, confidence, primary_class, defect_type=None, camera_source="webcam", processing_time_ms=0.0):
        """Log a new inspection record."""
        with self._lock:
            self.counter += 1
            now = datetime.now()
            entry = {
                "inspection_id": self.counter,
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "result": decision,
                "confidence": round(float(confidence) * 100, 1),
                "primary_class": primary_class,
                "defect_type": defect_type or "-",
                "camera_source": camera_source,
                "processing_time_ms": round(float(processing_time_ms), 1)
            }
            self.records.insert(0, entry)
            if len(self.records) > 500:
                self.records.pop()
            return entry

    def get_recent(self, limit=20):
        with self._lock:
            return list(self.records[:limit])

    def get_summary_stats(self):
        """Calculate production KPIs."""
        with self._lock:
            total = len(self.records)
            if total == 0:
                return {
                    "total": 0, "passed": 0, "defects": 0, "review": 0,
                    "yield_rate": 100.0, "defect_rate": 0.0, "avg_confidence": 0.0, "avg_time_ms": 0.0
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
        """Alias for get_summary_stats."""
        return self.get_summary_stats()

    def export_csv_stream(self):
        """Generate CSV data stream for download."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Inspection ID", "Date", "Time", "Result", "Defect Type", "Confidence (%)", "Camera Source", "Processing Time (ms)"])
        with self._lock:
            for r in self.records:
                writer.writerow([
                    r["inspection_id"], r["date"], r["time"], r["result"],
                    r["defect_type"], r["confidence"], r["camera_source"], r["processing_time_ms"]
                ])
        output.seek(0)
        return output.getvalue()

    def clear(self):
        with self._lock:
            self.records.clear()
            self.counter = 0
