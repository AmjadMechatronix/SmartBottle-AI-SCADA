"""
=============================================================================
Smart Bottle Inspection System - Decision Engine
=============================================================================
Evaluates raw YOLOv8 detections and produces clean three-state industrial decisions:
  - PASS: Bottle is fully compliant (bottle, cap, label present and intact)
  - FAIL: Defect detected (cap missing, damaged plastic, label missing)
  - REVIEW: Low confidence / ambiguous detection requiring operator verification

Includes inspection debouncing to prevent multi-triggering on the same passing bottle.
=============================================================================
"""

import time
import logging
import config

logger = logging.getLogger("DecisionEngine")

class InspectionResult:
    def __init__(self, decision, confidence, primary_class, defect_type=None, all_detections=None, processing_time_ms=0.0):
        self.decision = decision            # "PASS", "FAIL", "REVIEW"
        self.confidence = confidence        # 0.0 to 1.0
        self.primary_class = primary_class  # Main detected label
        self.defect_type = defect_type      # Name of defect if FAIL, else None
        self.all_detections = all_detections or []
        self.processing_time_ms = processing_time_ms
        self.timestamp = time.strftime("%H:%M:%S")

    def to_dict(self):
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
    def __init__(self):
        self.high_threshold = config.CONFIDENCE_HIGH_THRESHOLD
        self.low_threshold = config.CONFIDENCE_LOW_THRESHOLD
        self.normal_classes = set(config.NORMAL_CLASSES)
        self.defect_classes = set(config.DEFECT_CLASSES)
        
        # Debounce tracking (avoid duplicate rapid inspection triggers)
        self.last_decision_time = 0.0
        self.last_decision = None
        self.debounce_interval_sec = 0.8  # Minimum time between consecutive bottle decisions

    def evaluate(self, yolo_boxes, class_names, processing_time_ms=0.0):
        """
        Evaluate bounding boxes from YOLOv8 inference.
        Returns an InspectionResult instance.
        """
        start_eval = time.time()
        
        if yolo_boxes is None or len(yolo_boxes) == 0:
            # No objects detected in frame
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

            if cls_name in self.defect_classes:
                detected_defects.append((cls_name, conf))
            elif cls_name in self.normal_classes:
                detected_normals.append((cls_name, conf))

        # 1. Defect Priority Check -> FAIL
        if detected_defects:
            # Sort by highest confidence defect
            detected_defects.sort(key=lambda x: x[1], reverse=True)
            top_defect_name, top_defect_conf = detected_defects[0]

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
                # Defect detected but confidence is very low -> REVIEW
                return InspectionResult(
                    decision="REVIEW",
                    confidence=top_defect_conf,
                    primary_class=top_defect_name,
                    defect_type=f"Possible {top_defect_name}",
                    all_detections=parsed_detections,
                    processing_time_ms=processing_time_ms
                )

        # 2. Normal Bottles Check -> PASS or REVIEW
        if detected_normals:
            detected_normals.sort(key=lambda x: x[1], reverse=True)
            top_normal_name, top_normal_conf = detected_normals[0]

            if top_normal_conf >= self.high_threshold:
                return InspectionResult(
                    decision="PASS",
                    confidence=top_normal_conf,
                    primary_class=top_normal_name,
                    defect_type=None,
                    all_detections=parsed_detections,
                    processing_time_ms=processing_time_ms
                )
            elif top_normal_conf >= self.low_threshold:
                return InspectionResult(
                    decision="REVIEW",
                    confidence=top_normal_conf,
                    primary_class=top_normal_name,
                    defect_type=None,
                    all_detections=parsed_detections,
                    processing_time_ms=processing_time_ms
                )

        # 3. Low confidence / Ambiguous
        return InspectionResult(
            decision="REVIEW",
            confidence=0.0,
            primary_class="Unknown",
            defect_type=None,
            all_detections=parsed_detections,
            processing_time_ms=processing_time_ms
        )

    def should_actuate(self, decision):
        """Debounce actuator triggers so we don't spam servo/buzzer repeatedly for 1 bottle."""
        if decision not in ["PASS", "FAIL", "REVIEW"]:
            return False

        now = time.time()
        if now - self.last_decision_time >= self.debounce_interval_sec:
            self.last_decision_time = now
            self.last_decision = decision
            return True
        return False
