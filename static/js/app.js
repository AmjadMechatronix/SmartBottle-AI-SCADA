/**
 * =============================================================================
 * SmartBottle™ AI Vision SCADA — المتحكم البرمجي لواجهة التحكم الصناعية (Frontend Controller)
 * =============================================================================
 * المعمارية البرمجية والوظائف:
 *   1. الاتصال اللحظي فائق السرعة عبر تقنية WebSockets (Socket.IO) مع آلية استرجاع تلقائي (Fallback REST Polling).
 *   2. راسم إشارة تفاعلي على لوحة Canvas لمراقبة موجات المسافة لحساس الألتراسونيك في الوقت الحقيقي (Oscilloscope).
 *   3. مؤشر دائري تناظري دقيق (Radial Distance Gauge) لمراقبة وصول ومغادرة الزجاجات.
 *   4. تكامل رسومي بياني متقدم عبر مكتبة Chart.js (Donut Chart) لتحليل وتوزيع نسب العيوب.
 *   5. تخليق صوتي فوري لصافرات الإنذار (Web Audio API Synthesizer) بدون الحاجة لملفات صوت خارجية.
 *   6. محرك تعريب وترجمة فوري متكامل ثنائي اللغة (العربية / English) مع دعم اتجاهات RTL و LTR.
 *   7. تحكم لمسي فوري بمحرك السير، ريليه الإضاءة، ذراع السيرفو، وتصدير تقارير CSV.
 * =============================================================================
 */

// ==========================================
// 1. Global State & Configuration
// ==========================================
const AppConfig = {
  POLL_INTERVAL_MS: 600,
  WAVEFORM_POINTS: 60,
  MAX_DISTANCE_CM: 80,
  CIRCUMFERENCE: 377 // 2 * PI * 60 (r=60 on radial gauge)
};

const AppState = {
  lang: localStorage.getItem('sb_lang') || 'ar',
  isAudioEnabled: true,
  autoMode: true,
  conveyorRunning: false,
  lightOn: false,
  lastAlertState: false,
  activeFilter: 'all',
  
  // Metrics Cache for Smooth Counting
  currentMetrics: {
    total: 0,
    good: 0,
    defective: 0,
    passRate: 100,
    fps: 0,
    latency: 0,
    distance: 0,
    threshold: 25.0
  },
  
  // Waveform History Buffer
  distanceHistory: Array(AppConfig.WAVEFORM_POINTS).fill(40),
  
  // Logs cache
  cachedLogs: []
};

// ==========================================
// 2. Bilingual Dictionary (AR / EN)
// ==========================================
const I18N = {
  ar: {
    brandSubtitle: "نظام الفحص الصناعي الذكي لخطوط الإنتاج",
    systemOnline: "النظام متصل",
    systemOffline: "انقطع الاتصال",
    espConnected: "ESP32 متصل",
    espDisconnected: "ESP32 غير متصل",
    kpiTotal: "إجمالي المفحوص",
    kpiGood: "الزجاجات السليمة",
    kpiDefective: "العيوب المرصودة",
    kpiPassRate: "نسبة الجودة",
    kpiFpsLatency: "معدل الإطارات والزمن",
    cameraTitle: "كاميرا الفحص البصري المباشر",
    sourceWebcam: "كاميرا USB / الحاسوب",
    sourceEsp32Cam: "ESP32-CAM (Wi-Fi)",
    sourceIpCam: "كاميرا الشبكة (IP)",
    statusPass: "مطابق للمواصفات",
    statusFail: "زجاجة معيبة",
    statusReview: "مراجعة / غير مؤكد",
    statusStandby: "في الانتظار...",
    confidence: "نسبة الثقة",
    inference: "زمن الاستنتاج",
    distanceTitle: "حساس المسافة بالموجات فوق الصوتية",
    thresholdLabel: "حد التحفيز",
    statusInStation: "زجاجة في المحطة",
    statusStationClear: "المحطة شاغرة",
    waveformTitle: "المخطط الزمني للمسافة (آخر 60 ثانية)",
    controlsTitle: "لوحة التحكم الصناعية SCADA",
    conveyorLabel: "حزام النقل الرئيسي",
    conveyorSub: "محرك السير الناقل للمحطة",
    lightLabel: "إضاءة الفحص المركزية",
    lightSub: "مرحل الإضاءة الصناعية (Relay)",
    autoModeLabel: "وضع التشغيل الآلي (Auto Mode)",
    autoModeSub: "فرز آلي تلقائي بالذكاء الاصطناعي",
    btnRejectSweep: "طرد يدوي (Servo)",
    btnResetStats: "تصفير العدادات",
    defectDistTitle: "توزيع تصنيفات العيوب",
    capMissing: "غطاء مفقود (Cap Missing)",
    damagedPlastic: "بلاستيك متضرر (Damaged Body)",
    labelMissing: "ملصق مفقود (Label Missing)",
    timelineTitle: "سجل عمليات الفحص الحية",
    filterAll: "الكل",
    filterPass: "السليم فقط",
    filterDefect: "المعيب فقط",
    exportCsv: "تصدير تقرير CSV",
    colTime: "الوقت",
    colStatus: "الحالة",
    colDefect: "نوع العيب / التصنيف",
    colConfidence: "الثقة",
    colLatency: "الزمن",
    footerUptime: "مدة تشغيل النظام",
    footerSerial: "منفذ الاتصال التسلسلي",
    footerDatabase: "سجلات قاعدة البيانات",
    toastSweepSent: "تم تفعيل ذراع الطرد بنجاح",
    toastResetSuccess: "تم تصفير جميع العدادات",
    toastDefectAlert: "تحذير: تم رصد زجاجة معيبة!",
    toastLangSwitched: "تم تغيير لغة الواجهة"
  },
  en: {
    brandSubtitle: "Industrial AI Quality Inspection SCADA",
    systemOnline: "System Online",
    systemOffline: "System Disconnected",
    espConnected: "ESP32 Online",
    espDisconnected: "ESP32 Offline",
    kpiTotal: "Total Inspected",
    kpiGood: "Compliant Bottles",
    kpiDefective: "Defects Found",
    kpiPassRate: "Quality Pass Rate",
    kpiFpsLatency: "Inference & Latency",
    cameraTitle: "Live Vision Inspection Viewport",
    sourceWebcam: "USB / Integrated Cam",
    sourceEsp32Cam: "ESP32-CAM (Wi-Fi)",
    sourceIpCam: "IP Network Stream",
    statusPass: "COMPLIANT PASS",
    statusFail: "DEFECTIVE FAIL",
    statusReview: "REVIEW / UNCERTAIN",
    statusStandby: "STANDBY...",
    confidence: "Confidence",
    inference: "Latency",
    distanceTitle: "Ultrasonic Distance Sensor",
    thresholdLabel: "Trigger Limit",
    statusInStation: "Bottle in Station",
    statusStationClear: "Station Clear",
    waveformTitle: "Distance Telemetry Oscilloscope (60s)",
    controlsTitle: "SCADA Hardware Actuation Panel",
    conveyorLabel: "Conveyor Belt Drive",
    conveyorSub: "Production line transport motor",
    lightLabel: "Inspection Illuminator",
    lightSub: "Solid-state relay light module",
    autoModeLabel: "Autonomous Mode (AI Direct)",
    autoModeSub: "Automatic sorting triggered by YOLO",
    btnRejectSweep: "Manual Reject Sweep",
    btnResetStats: "Reset Counters",
    defectDistTitle: "Defect Classification Breakdown",
    capMissing: "Cap Missing",
    damagedPlastic: "Damaged Body",
    labelMissing: "Label Missing",
    timelineTitle: "Real-time Inspection Telemetry Log",
    filterAll: "All Logs",
    filterPass: "Pass Only",
    filterDefect: "Defects Only",
    exportCsv: "Export CSV Report",
    colTime: "Timestamp",
    colStatus: "Verdict",
    colDefect: "Defect Category",
    colConfidence: "Confidence",
    colLatency: "Latency",
    footerUptime: "System Uptime",
    footerSerial: "Serial COM Bus",
    footerDatabase: "Database Records",
    toastSweepSent: "Reject sweep servo actuated",
    toastResetSuccess: "Statistical counters reset",
    toastDefectAlert: "Defect Alert: Non-compliant bottle detected!",
    toastLangSwitched: "Interface language updated"
  }
};

// ==========================================
// 3. Audio Defect Buzzer
// ==========================================
let audioContext = null;

function playAudioAlert() {
  if (!AppState.isAudioEnabled) return;
  try {
    if (!audioContext) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      audioContext = new AudioCtx();
    }
    if (audioContext.state === 'suspended') {
      audioContext.resume();
    }
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(880, audioContext.currentTime); // A5 note
    osc.frequency.exponentialRampToValueAtTime(440, audioContext.currentTime + 0.25);
    gain.gain.setValueAtTime(0.2, audioContext.currentTime);
    gain.gain.linearRampToValueAtTime(0.01, audioContext.currentTime + 0.25);
    osc.connect(gain);
    gain.connect(audioContext.destination);
    osc.start();
    osc.stop(audioContext.currentTime + 0.26);
  } catch (err) {
    console.warn("Audio synthesis error:", err);
  }
}

// ==========================================
// 4. Chart.js Donut Setup
// ==========================================
let defectChart = null;

function initDonutChart() {
  const ctx = document.getElementById('defectChartCanvas');
  if (!ctx) return;
  
  defectChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['غطاء مفقود (Cap)', 'بلاستيك متضرر (Damaged)', 'ملصق مفقود (Label)'],
      datasets: [{
        data: [0, 0, 0],
        backgroundColor: ['#06b6d4', '#ef4444', '#f59e0b'],
        borderColor: '#0f172a',
        borderWidth: 3,
        hoverOffset: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '72%',
      animation: {
        animateScale: true,
        duration: 600
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.9)',
          titleFont: { family: 'Inter', size: 12 },
          bodyFont: { family: 'Inter', size: 12 },
          padding: 10,
          boxPadding: 6,
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1
        }
      }
    }
  });
}

function updateDonutChart(counts) {
  if (!defectChart) return;
  const cap = counts['cap missing'] || 0;
  const dmg = counts['damaged plastic'] || counts['damaged body'] || 0;
  const lbl = counts['label missing'] || 0;

  // Update DOM numeric legends
  const cEl = document.getElementById('cntCap');
  const dEl = document.getElementById('cntDamaged');
  const lEl = document.getElementById('cntLabel');
  if (cEl) cEl.innerText = cap;
  if (dEl) dEl.innerText = dmg;
  if (lEl) lEl.innerText = lbl;

  const dataset = defectChart.data.datasets[0];
  if (dataset.data[0] !== cap || dataset.data[1] !== dmg || dataset.data[2] !== lbl) {
    dataset.data = [cap, dmg, lbl];
    defectChart.update('none');
  }
}

// ==========================================
// 5. Ultrasonic Waveform Plotter
// ==========================================
function initWaveformCanvas() {
  const canvas = document.getElementById('distanceWaveformCanvas');
  if (!canvas) return;
  
  // Set real resolution based on CSS width/height
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * window.devicePixelRatio || 500;
  canvas.height = (rect.height || 95) * window.devicePixelRatio || 190;
  drawWaveform();
}

function pushDistanceToWaveform(val) {
  AppState.distanceHistory.push(val);
  if (AppState.distanceHistory.length > AppConfig.WAVEFORM_POINTS) {
    AppState.distanceHistory.shift();
  }
  drawWaveform();
}

function drawWaveform() {
  const canvas = document.getElementById('distanceWaveformCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const padding = 10;
  
  ctx.clearRect(0, 0, w, h);
  
  // 1. Draw subtle grid
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let y = 0; y <= h; y += h / 4) {
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
  }
  ctx.stroke();

  // 2. Draw Threshold Line (Amber dashed)
  const threshold = AppState.currentMetrics.threshold || 25.0;
  const threshY = h - ((threshold / AppConfig.MAX_DISTANCE_CM) * (h - padding * 2) + padding);
  
  ctx.save();
  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = 'rgba(245, 158, 11, 0.6)';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(0, threshY);
  ctx.lineTo(w, threshY);
  ctx.stroke();
  
  // Threshold label
  ctx.fillStyle = 'rgba(245, 158, 11, 0.9)';
  ctx.font = `${10 * (window.devicePixelRatio || 1)}px Inter, sans-serif`;
  ctx.fillText(`${threshold.toFixed(0)}cm Limit`, 8, threshY - 4);
  ctx.restore();

  // 3. Draw Distance Line
  const data = AppState.distanceHistory;
  const step = w / (AppConfig.WAVEFORM_POINTS - 1);
  
  ctx.beginPath();
  const points = [];
  for (let i = 0; i < data.length; i++) {
    const val = Math.min(Math.max(data[i], 0), AppConfig.MAX_DISTANCE_CM);
    const x = i * step;
    const y = h - ((val / AppConfig.MAX_DISTANCE_CM) * (h - padding * 2) + padding);
    points.push({ x, y });
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }

  // Stroke line with glowing cyan
  ctx.strokeStyle = '#06b6d4';
  ctx.lineWidth = 2.5 * (window.devicePixelRatio || 1);
  ctx.shadowColor = 'rgba(6, 182, 212, 0.6)';
  ctx.shadowBlur = 10;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // Gradient fill under waveform
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, 'rgba(6, 182, 212, 0.25)');
  grad.addColorStop(1, 'rgba(6, 182, 212, 0.0)');
  ctx.fillStyle = grad;
  ctx.fill();
}

// ==========================================
// 6. Radial Distance Gauge Controller
// ==========================================
function updateRadialDistanceGauge(distance, threshold) {
  const circle = document.getElementById('radialGaugeCircle');
  const numEl = document.getElementById('distanceVal');
  const threshEl = document.getElementById('thresholdVal');
  const badgeEl = document.getElementById('stationStatusBadge');
  
  if (!circle || !numEl) return;

  const validDist = (distance !== null && distance !== undefined && distance >= 0 && distance < 500) ? distance : 0;
  numEl.innerText = validDist > 0 ? validDist.toFixed(1) : '--';
  if (threshEl) threshEl.innerText = `${threshold.toFixed(1)} cm`;

  // Calculate Dashoffset: 0 cm -> full (377), 80 cm -> empty (0)
  const ratio = Math.min(Math.max(validDist / AppConfig.MAX_DISTANCE_CM, 0), 1);
  const offset = AppConfig.CIRCUMFERENCE - (ratio * AppConfig.CIRCUMFERENCE);
  circle.style.strokeDashoffset = offset;

  // Bottle presence detection logic
  const isPresent = validDist > 0.5 && validDist <= threshold;
  if (isPresent) {
    circle.style.stroke = 'var(--accent-amber)';
    circle.style.filter = 'drop-shadow(0 0 8px rgba(245, 158, 11, 0.7))';
    if (badgeEl) {
      badgeEl.className = 'status-pill';
      badgeEl.style.color = 'var(--accent-amber)';
      badgeEl.style.borderColor = 'rgba(245, 158, 11, 0.35)';
      badgeEl.innerHTML = `<span class="pulse-dot pulse-amber"></span> <span>${I18N[AppState.lang].statusInStation}</span>`;
    }
  } else {
    circle.style.stroke = 'var(--accent-cyan)';
    circle.style.filter = 'drop-shadow(0 0 6px rgba(6, 182, 212, 0.5))';
    if (badgeEl) {
      badgeEl.className = 'status-pill';
      badgeEl.style.color = 'var(--text-secondary)';
      badgeEl.style.borderColor = 'var(--border-subtle)';
      badgeEl.innerHTML = `<span class="pulse-dot pulse-green"></span> <span>${I18N[AppState.lang].statusStationClear}</span>`;
    }
  }
}

// ==========================================
// 7. Smooth Count-Up Animation
// ==========================================
function animateCount(elemId, target, suffix = '', decimals = 0) {
  const el = document.getElementById(elemId);
  if (!el) return;
  const startVal = parseFloat(el.getAttribute('data-val') || 0);
  if (startVal === target) return;
  
  el.setAttribute('data-val', target);
  const duration = 400;
  const startTime = performance.now();

  function tick(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const easeProgress = 1 - Math.pow(1 - progress, 3); // Cubic ease out
    const current = startVal + (target - startVal) * easeProgress;
    el.innerText = `${current.toFixed(decimals)}${suffix}`;
    if (progress < 1) requestAnimationFrame(tick);
    else el.innerText = `${target.toFixed(decimals)}${suffix}`;
  }
  requestAnimationFrame(tick);
}

// ==========================================
// 8. Main Dashboard Telemetry Updater
// ==========================================
function updateDashboardData(data) {
  if (!data) return;

  // 1. KPI Counts
  animateCount('totalCount', data.total_inspections || 0);
  animateCount('goodCount', data.good_bottles || 0);
  animateCount('defectCount', data.defective_bottles || 0);
  
  const passRate = data.pass_rate !== undefined ? data.pass_rate : 100.0;
  animateCount('passRate', passRate, '%', 1);

  // Update Pass Rate Progress Bar
  const pBar = document.getElementById('passRateProgressBar');
  if (pBar) {
    pBar.style.width = `${Math.min(Math.max(passRate, 0), 100)}%`;
    if (passRate >= 90) pBar.className = 'kpi-progress-bar bar-emerald';
    else if (passRate >= 75) pBar.className = 'kpi-progress-bar'; // neutral amber
    else pBar.className = 'kpi-progress-bar bar-rose';
  }

  // 2. FPS & Latency
  const fpsEl = document.getElementById('fpsVal');
  const latEl = document.getElementById('latencyVal');
  if (fpsEl) fpsEl.innerText = (data.fps || 0).toFixed(1);
  if (latEl) latEl.innerText = `${Math.round(data.processing_time_ms || 18)}ms`;

  // 3. Camera HUD Verdict Badge
  updateHudVerdict(data.current_decision, data.current_confidence, data.current_defect);

  // 4. Ultrasonic Sensor & Waveform
  let dist = 999.0;
  if (data.hardware && data.hardware.distance_cm !== undefined && data.hardware.distance_cm !== null) {
    dist = parseFloat(data.hardware.distance_cm);
  }
  const threshold = parseFloat(data.distance_threshold || 25.0);
  AppState.currentMetrics.threshold = threshold;
  
  if (dist < 400 && dist >= 0) {
    pushDistanceToWaveform(dist);
    updateRadialDistanceGauge(dist, threshold);
  } else {
    pushDistanceToWaveform(threshold * 1.5);
    updateRadialDistanceGauge(null, threshold);
  }

  // 5. Defect Donut Breakdown
  if (data.defect_counts) {
    updateDonutChart(data.defect_counts);
  }

  // 6. Defect Sound Alarm & Overlay
  if (data.alert_active) {
    if (!AppState.lastAlertState) {
      playAudioAlert();
      showToast(I18N[AppState.lang].toastDefectAlert, 'danger');
    }
  }
  AppState.lastAlertState = !!data.alert_active;

  // 7. Hardware Switches Sync
  if (data.hardware) {
    syncHardwareToggles(data.hardware);
  }

  // 8. Auto Mode Toggle Sync
  if (data.auto_mode !== undefined) {
    AppState.autoMode = !!data.auto_mode;
    const autoSw = document.getElementById('autoModeSwitch');
    if (autoSw) {
      if (AppState.autoMode) autoSw.classList.add('active');
      else autoSw.classList.remove('active');
    }
  }

  // 9. Inspection Table Logs
  if (data.logs && Array.isArray(data.logs)) {
    AppState.cachedLogs = data.logs;
    renderInspectionLogs(data.logs);
  }

  // 10. System Status Header Pills
  updateSystemStatusPills(data);
}

function updateHudVerdict(decision, confidence, defectName) {
  const badge = document.getElementById('hudDecisionBadge');
  const confText = document.getElementById('hudConfidenceText');
  if (!badge) return;

  const t = I18N[AppState.lang];
  const confPercent = confidence ? Math.round(confidence * 100) : 0;

  if (decision === 'PASS') {
    badge.className = 'hud-status-badge badge-pass';
    badge.innerHTML = `<i data-lucide="check-circle" style="width:18px;height:18px;"></i> <span>${t.statusPass}</span>`;
  } else if (decision === 'FAIL') {
    badge.className = 'hud-status-badge badge-fail';
    const defLabel = defectName ? ` (${defectName})` : '';
    badge.innerHTML = `<i data-lucide="alert-triangle" style="width:18px;height:18px;"></i> <span>${t.statusFail}${defLabel}</span>`;
  } else if (decision === 'REVIEW') {
    badge.className = 'hud-status-badge badge-review';
    badge.innerHTML = `<i data-lucide="help-circle" style="width:18px;height:18px;"></i> <span>${t.statusReview}</span>`;
  } else {
    badge.className = 'hud-status-badge badge-standby';
    badge.innerHTML = `<i data-lucide="loader" style="width:18px;height:18px;"></i> <span>${t.statusStandby}</span>`;
  }

  if (confText) {
    confText.innerText = confPercent > 0 ? `${confPercent}%` : '--%';
  }
  
  if (window.lucide) lucide.createIcons();
}

function syncHardwareToggles(hw) {
  const cSw = document.getElementById('conveyorSwitch');
  const lSw = document.getElementById('lightSwitch');
  
  // Conveyor state
  if (cSw && hw.motor !== undefined) {
    AppState.conveyorRunning = hw.motor === 'ON';
    if (AppState.conveyorRunning) cSw.classList.add('active');
    else cSw.classList.remove('active');
  }

  // Light/Relay state
  if (lSw && hw.relay !== undefined) {
    AppState.lightOn = hw.relay === 'ON';
    if (AppState.lightOn) lSw.classList.add('active');
    else lSw.classList.remove('active');
  }
}

function updateSystemStatusPills(data) {
  const espPill = document.getElementById('espStatusPill');
  const camPill = document.getElementById('camStatusPill');
  const t = I18N[AppState.lang];

  if (espPill) {
    const isOnline = data.hardware && data.hardware.esp32 === 'ONLINE';
    if (isOnline) {
      espPill.innerHTML = `<span class="pulse-dot pulse-green"></span> <span>${t.espConnected} (${data.hardware.port || 'COM'})</span>`;
    } else {
      espPill.innerHTML = `<span class="pulse-dot pulse-red"></span> <span>${t.espDisconnected}</span>`;
    }
  }

  if (camPill && data.current_source) {
    camPill.innerHTML = `<i data-lucide="video" style="width:14px;height:14px;color:var(--accent-cyan)"></i> <span>${data.current_source.toUpperCase()}</span>`;
  }
}

// ==========================================
// 9. Inspection History Log Table
// ==========================================
function renderInspectionLogs(logs) {
  const tbody = document.getElementById('inspectionLogTbody');
  const badgeCount = document.getElementById('tableLogCount');
  if (!tbody) return;

  if (badgeCount) badgeCount.innerText = `${logs.length} events`;

  // Filter logs based on activeFilter
  const filtered = logs.filter(item => {
    if (AppState.activeFilter === 'pass') return item.decision === 'PASS';
    if (AppState.activeFilter === 'defect') return item.decision === 'FAIL' || item.decision === 'REVIEW';
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:1.5rem;">No inspection events recorded yet.</td></tr>`;
    return;
  }

  let html = '';
  filtered.forEach(log => {
    let badgeClass = 'badge-pass-cell';
    let icon = 'check';
    if (log.decision === 'FAIL') {
      badgeClass = 'badge-fail-cell';
      icon = 'x-circle';
    } else if (log.decision === 'REVIEW') {
      badgeClass = 'badge-review-cell';
      icon = 'alert-circle';
    }

    const defectName = log.defect_type || log.defect || '—';
    const confVal = log.confidence ? `${Math.round(log.confidence * (log.confidence <= 1 ? 100 : 1))}%` : '—';
    const latVal = log.processing_time_ms ? `${Math.round(log.processing_time_ms)}ms` : '—';

    html += `
      <tr>
        <td style="color:var(--text-secondary);font-size:0.75rem;">${log.timestamp || log.time || '00:00:00'}</td>
        <td>
          <span class="status-badge-cell ${badgeClass}">
            <i data-lucide="${icon}" style="width:12px;height:12px;"></i>
            ${log.decision || 'PASS'}
          </span>
        </td>
        <td style="font-weight:600;color:${log.decision === 'FAIL' ? 'var(--accent-rose-light)' : 'var(--text-primary)'};">
          ${defectName}
        </td>
        <td style="color:var(--accent-cyan);">${confVal}</td>
        <td style="color:var(--text-muted);">${latVal}</td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

function setLogFilter(filterType) {
  AppState.activeFilter = filterType;
  const btns = ['btnFilterAll', 'btnFilterPass', 'btnFilterDefect'];
  btns.forEach(bId => {
    const el = document.getElementById(bId);
    if (el) el.classList.remove('active');
  });

  const activeBtn = document.getElementById(`btnFilter${filterType.charAt(0).toUpperCase() + filterType.slice(1)}`);
  if (activeBtn) activeBtn.classList.add('active');

  renderInspectionLogs(AppState.cachedLogs);
}

// ==========================================
// 10. SCADA Hardware Actuation Handlers
// ==========================================
async function toggleConveyor() {
  const nextState = !AppState.conveyorRunning;
  const action = nextState ? 'on' : 'off';
  try {
    const res = await fetch(`/api/hardware/motor?action=${action}`, { method: 'POST' });
    const data = await res.json();
    AppState.conveyorRunning = nextState;
    const sw = document.getElementById('conveyorSwitch');
    if (sw) {
      if (nextState) sw.classList.add('active');
      else sw.classList.remove('active');
    }
    showToast(nextState ? "Conveyor started (ON)" : "Conveyor halted (STOP)", nextState ? 'success' : 'info');
  } catch (err) {
    showToast("Error toggling conveyor motor", 'danger');
  }
}

async function toggleLight() {
  const nextState = !AppState.lightOn;
  const action = nextState ? 'on' : 'off';
  try {
    const res = await fetch(`/api/hardware/relay?action=${action}`, { method: 'POST' });
    const data = await res.json();
    AppState.lightOn = nextState;
    const sw = document.getElementById('lightSwitch');
    if (sw) {
      if (nextState) sw.classList.add('active');
      else sw.classList.remove('active');
    }
    showToast(nextState ? "Inspection illuminator ON" : "Inspection illuminator OFF", 'info');
  } catch (err) {
    showToast("Error toggling relay light", 'danger');
  }
}

async function toggleAutoMode() {
  const nextState = !AppState.autoMode;
  try {
    const res = await fetch('/api/mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_mode: nextState })
    });
    const data = await res.json();
    AppState.autoMode = !!data.auto_mode;
    const sw = document.getElementById('autoModeSwitch');
    if (sw) {
      if (AppState.autoMode) sw.classList.add('active');
      else sw.classList.remove('active');
    }
    showToast(AppState.autoMode ? "AI Autonomous Mode ACTIVE" : "Manual Mode ACTIVE", 'info');
  } catch (err) {
    showToast("Error toggling Auto mode", 'danger');
  }
}

async function triggerRejectSweep() {
  const btn = document.getElementById('btnRejectSweep');
  if (btn) btn.style.transform = 'scale(0.95)';
  
  try {
    showToast(I18N[AppState.lang].toastSweepSent, 'danger');
    await fetch('/api/hardware/servo?action=reject', { method: 'POST' });
    setTimeout(async () => {
      await fetch('/api/hardware/servo?action=home', { method: 'POST' });
      if (btn) btn.style.transform = '';
    }, 1200);
  } catch (err) {
    showToast("Failed to actuate servo reject", 'danger');
    if (btn) btn.style.transform = '';
  }
}

async function triggerResetStats() {
  const msg = AppState.lang === 'ar' ? "هل تؤكد تصفير جميع العدادات وسجلات الفحص؟" : "Confirm resetting all inspection statistics and counters?";
  if (!confirm(msg)) return;
  
  try {
    await fetch('/api/reset_stats', { method: 'POST' });
    showToast(I18N[AppState.lang].toastResetSuccess, 'success');
  } catch (err) {
    showToast("Failed to reset statistics", 'danger');
  }
}

// ==========================================
// 11. Camera HUD Viewport Actions
// ==========================================
function switchCameraSource(sourceType) {
  fetch('/api/update_settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_type: sourceType })
  }).then(res => res.json()).then(data => {
    const img = document.getElementById('mainCameraStream');
    if (img) img.src = `/video_feed?t=${Date.now()}`;
    showToast(`Camera source changed to ${sourceType.toUpperCase()}`, 'info');
  }).catch(err => {
    showToast("Failed to change camera source", 'danger');
  });
}

function captureSnapshotDownload() {
  const a = document.createElement('a');
  a.href = `/api/labview/snapshot.jpg?t=${Date.now()}`;
  a.download = `smartbottle_snap_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '_')}.jpg`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast("Snapshot downloaded successfully", 'success');
}

function toggleCameraFullscreen() {
  const container = document.getElementById('cameraViewportWrap');
  if (!container) return;
  
  if (!document.fullscreenElement) {
    container.requestFullscreen().catch(err => {
      console.warn("Fullscreen request error:", err);
    });
  } else {
    document.exitFullscreen();
  }
}

// ==========================================
// 12. Toast Notification Engine
// ==========================================
function showToast(message, type = 'info', duration = 3200) {
  const stack = document.getElementById('toastStack');
  if (!stack) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  let icon = 'info';
  if (type === 'success') icon = 'check-circle';
  if (type === 'danger') icon = 'alert-triangle';

  toast.innerHTML = `
    <i data-lucide="${icon}" style="width:20px;height:20px;flex-shrink:0;"></i>
    <div style="font-size:0.82rem;font-weight:600;color:var(--text-primary);">${message}</div>
  `;

  stack.appendChild(toast);
  if (window.lucide) lucide.createIcons();

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(12px) scale(0.9)';
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 350);
  }, duration);
}

// ==========================================
// 13. Bilingual & Audio Controls
// ==========================================
function setLanguage(lang) {
  AppState.lang = lang;
  localStorage.setItem('sb_lang', lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  document.body.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');

  // Update i18n text nodes in DOM
  const elements = document.querySelectorAll('[data-i18n]');
  elements.forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (I18N[lang] && I18N[lang][key]) {
      el.innerText = I18N[lang][key];
    }
  });

  const langBtn = document.getElementById('langToggleBtn');
  if (langBtn) {
    langBtn.innerHTML = `<i data-lucide="languages" style="width:15px;height:15px;"></i> <span>${lang === 'ar' ? 'English' : 'عربي'}</span>`;
  }
  if (window.lucide) lucide.createIcons();
}

function toggleLanguage() {
  const newLang = AppState.lang === 'ar' ? 'en' : 'ar';
  setLanguage(newLang);
  showToast(I18N[newLang].toastLangSwitched, 'info');
}

function toggleAudioMute() {
  AppState.isAudioEnabled = !AppState.isAudioEnabled;
  const btn = document.getElementById('audioMuteBtn');
  if (!btn) return;

  if (AppState.isAudioEnabled) {
    btn.innerHTML = `<i data-lucide="volume-2" style="width:16px;height:16px;"></i>`;
    btn.style.color = 'var(--text-primary)';
    showToast("Audio alerts enabled", 'info');
  } else {
    btn.innerHTML = `<i data-lucide="volume-x" style="width:16px;height:16px;"></i>`;
    btn.style.color = 'var(--accent-rose)';
    showToast("Audio alerts muted", 'warning');
  }
  if (window.lucide) lucide.createIcons();
}

// ==========================================
// 14. Live Uptime Counter
// ==========================================
const startTimeStamp = Date.now();

function updateUptimeDisplay() {
  const el = document.getElementById('uptimeVal');
  if (!el) return;
  const totalSeconds = Math.floor((Date.now() - startTimeStamp) / 1000);
  const hrs = String(Math.floor(totalSeconds / 3600)).padStart(2, '0');
  const mins = String(Math.floor((totalSeconds % 3600) / 60)).padStart(2, '0');
  const secs = String(totalSeconds % 60).padStart(2, '0');
  el.innerText = `${hrs}:${mins}:${secs}`;
}

// ==========================================
// 15. Real-Time Socket.IO & Polling Initialization
// ==========================================
function startTelemetryEngine() {
  // 1. Initialize Socket.IO connection
  try {
    if (typeof io !== 'undefined') {
      const socket = io();
      socket.on('connect', () => {
        console.log("⚡ Connected to SmartBottle Socket.IO server");
      });
      socket.on('telemetry', data => {
        updateDashboardData(data);
      });
      socket.on('inspection_result', data => {
        updateDashboardData(data);
      });
    }
  } catch (e) {
    console.warn("Socket.IO not reachable, continuing on REST fallback:", e);
  }

  // 2. Continuous 600ms REST Fallback Polling
  setInterval(async () => {
    try {
      const res = await fetch('/api/stats');
      if (res.ok) {
        const data = await res.json();
        updateDashboardData(data);
      }
    } catch (err) {
      // Network hiccup - ignore silently
    }
  }, AppConfig.POLL_INTERVAL_MS);

  // 3. 1-second Uptime interval
  setInterval(updateUptimeDisplay, 1000);
}

// ==========================================
// 16. Window Load Bootstrap
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  if (window.lucide) lucide.createIcons();
  
  // Set initial language
  setLanguage(AppState.lang);
  
  // Init visual charts
  initDonutChart();
  initWaveformCanvas();
  
  // Handle resize for waveform canvas
  window.addEventListener('resize', () => {
    initWaveformCanvas();
  });

  // Start Real-time Telemetry
  startTelemetryEngine();
  
  console.log("🚀 SmartBottle™ SCADA Dashboard Loaded & Initialized");
});
