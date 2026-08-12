"""
LUMINA - Gelişmiş Parlaklık Kontrolü
Monitör Algılama, Gerçek Zamanlı Senkronizasyon ve Loglama
"""
import sys, os, subprocess, json, winreg, time, queue, datetime, threading, tempfile, re, random, logging
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QFrame, QSystemTrayIcon,
    QMenu, QAction, QGraphicsDropShadowEffect, QCheckBox,
    QSizePolicy, QToolTip, QStackedWidget, QColorDialog,
    QTimeEdit, QScrollArea, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint, QSettings, QSize, QPropertyAnimation, QEasingCurve, QObject, QTime
from PyQt5.QtGui import QFont, QColor, QPainter, QLinearGradient, QBrush, QIcon, QPixmap, QCursor

# Loglama Yapılandırması
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BASE_DIR

LOG_FILE = os.path.join(EXE_DIR, "lumina.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    encoding='utf-8',
    filemode='w'
)
logger = logging.getLogger("LUMINA")

logger.info(f"Uygulama Başlatıldı. BASE_DIR: {BASE_DIR}, EXE_DIR: {EXE_DIR}")

def find_cmm():
    candidates = [
        os.path.join(BASE_DIR, "ControlMyMonitor.exe"),
        os.path.join(EXE_DIR, "ControlMyMonitor.exe"),
        os.path.join(os.getcwd(), "ControlMyMonitor.exe"),
        "ControlMyMonitor.exe"
    ]
    for p in candidates:
        if os.path.exists(p):
            logger.info(f"ControlMyMonitor bulundu: {p}")
            return os.path.abspath(p)
    logger.error("ControlMyMonitor.exe bulunamadı!")
    return "ControlMyMonitor.exe"

CMM_PATH = find_cmm()
LOGO_PATH = os.path.join(BASE_DIR, "lumina_logo.png")
APP_NAME = "LUMINA"

CMM_LOCK = threading.Lock()
CREATE_NO_WINDOW = 0x08000000

def run_ps(cmd):
    logger.debug(f"PowerShell Çalıştırılıyor: {cmd}")
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
            stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=8
        )
        res = out.decode("utf-8", errors="ignore").strip()
        logger.debug(f"PowerShell Yanıtı: {res[:100]}...")
        return res
    except Exception as e:
        logger.error(f"PowerShell Hatası: {str(e)}")
        return ""

def set_internal_brightness(v):
    logger.info(f"Dahili Parlaklık Ayarlanıyor: {v}%")
    run_ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{v})")

def set_external_brightness(monitor_id, v):
    if not CMM_PATH: return
    logger.info(f"Harici Parlaklık Ayarlanıyor: {monitor_id} -> {v}%")
    with CMM_LOCK:
        try:
            subprocess.call([CMM_PATH, "/SetValue", monitor_id, "10", str(v)], 
                            stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=5)
        except Exception as e:
            logger.error(f"Harici Parlaklık Hatası ({monitor_id}): {str(e)}")

class BrightnessWorker(QThread):
    def __init__(self):
        super().__init__()
        self._queue = queue.Queue(); self._running = True
        self._last_processed_values = {}; self._pending_values = {}
    def update_brightness(self, mon_id, val):
        self._pending_values[mon_id] = val; self._queue.put(mon_id)
    def stop(self): self._running = False; self._queue.put(None)
    def run(self):
        logger.info("BrightnessWorker Başlatıldı.")
        while self._running:
            try:
                mon_id = self._queue.get(timeout=0.1)
                if mon_id is None: break
                target_val = self._pending_values.get(mon_id)
                if target_val is None: self._queue.task_done(); continue
                if self._last_processed_values.get(mon_id) == target_val:
                    self._queue.task_done(); continue
                if mon_id == "__internal__": set_internal_brightness(target_val)
                else: set_external_brightness(mon_id, target_val)
                self._last_processed_values[mon_id] = target_val
                self._queue.task_done(); time.sleep(0.01)
            except Exception: continue

def get_external_brightness(dev_id):
    logger.debug(f"Harici Değer Okunuyor: {dev_id}")
    temp_dir = tempfile.gettempdir()
    tid = f"{int(time.time()*1000)}_{random.randint(100,999)}"
    tmp_csv = os.path.join(temp_dir, f"l_val_{tid}.csv")
    val = None
    
    for i in range(2):
        try:
            logger.debug(f"Okuma Denemesi {i+1}...")
            subprocess.call([CMM_PATH, "/scomma", tmp_csv, dev_id], creationflags=CREATE_NO_WINDOW, timeout=5)
            if os.path.exists(tmp_csv):
                with open(tmp_csv, encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        p = line.split(",")
                        if len(p) >= 5 and p[0].strip() == "10":
                            val = int(p[3]); break
                os.remove(tmp_csv)
                if val is not None: return val
            time.sleep(0.15)
        except Exception as e:
            logger.warning(f"Okuma Denemesi {i+1} Başarısız: {str(e)}")
            time.sleep(0.15)
    logger.warning(f"Değer Okunamadı, 50% Fallback Dönülüyor: {dev_id}")
    return 50

def get_monitors_data(only_brightness=False, cached_monitors=None):
    logger.info(f"Monitör Taraması Başladı (only_brightness={only_brightness})")
    ps_result = run_ps(
        "$w=Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness;"
        "if($w){[string]::Join('|||',@($w.InstanceName))+':::'+[string]($w[0].CurrentBrightness)}"
    )
    ps_parts = ps_result.split(":::")
    internal_ids_raw = ps_parts[0] if ps_parts else ""
    internal_ids = [i.strip().upper() for i in internal_ids_raw.split("|||") if i.strip()]
    try: internal_brightness = int(ps_parts[1].strip()) if len(ps_parts) > 1 and ps_parts[1].strip() else 50
    except: internal_brightness = 50

    results = []

    if only_brightness and cached_monitors:
        def _fetch(m):
            m_copy = m.copy()
            if m_copy["type"] == "internal":
                m_copy["brightness"] = internal_brightness
            else:
                m_copy["brightness"] = get_external_brightness(m_copy["id"])
            return m_copy
        with ThreadPoolExecutor(max_workers=min(4, len(cached_monitors))) as ex:
            results = list(ex.map(_fetch, cached_monitors))
        return results

    temp_dir = tempfile.gettempdir()
    tmp_file = os.path.join(temp_dir, f"l_full_{int(time.time())}.txt")
    try:
        logger.info("Tam Tarama (/smonitors) Başlatılıyor...")
        with CMM_LOCK:
            subprocess.call([CMM_PATH, "/smonitors", tmp_file], creationflags=CREATE_NO_WINDOW, timeout=15)
        
        if os.path.exists(tmp_file):
            with open(tmp_file, mode='rb') as f:
                raw = f.read()
                content = raw.decode('utf-16') if raw.startswith(b'\xff\xfe') else raw.decode('utf-8', errors='ignore')
            os.remove(tmp_file)
            
            blocks = re.split(r'\n(?=Monitor Device Name)', content.replace("\r", ""))
            for block in blocks:
                if not block.strip(): continue
                m_data = {}
                for line in block.splitlines():
                    if ":" in line:
                        parts = line.split(":", 1)
                        m_data[parts[0].strip()] = parts[1].strip().strip('"')
                
                dev_name = m_data.get("Monitor Device Name")
                if not dev_name: continue
                mon_id = m_data.get("Monitor ID", "").upper(); short_id = m_data.get("Short Monitor ID", "").upper(); disp_name = m_data.get("Monitor Name", "")
                
                is_internal = False
                if mon_id:
                    for iid in internal_ids:
                        if mon_id in iid or iid in mon_id: is_internal = True; break
                if not is_internal and short_id:
                    for iid in internal_ids:
                        if short_id in iid: is_internal = True; break
                
                if is_internal:
                    if not any(r["type"] == "internal" for r in results):
                        results.append({"id": "__internal__", "name": "Laptop Ekranı", "brightness": internal_brightness, "max": 100, "type": "internal"})
                else:
                    cur_b = get_external_brightness(dev_name)
                    results.append({"id": dev_name, "name": disp_name or f"Harici Monitör ({short_id})", "brightness": cur_b, "max": 100, "type": "external"})
    except Exception as e:
        logger.error(f"Tam Tarama Hatası: {str(e)}")

    if not any(r["type"] == "internal" for r in results):
        results.insert(0, {"id": "__internal__", "name": "Laptop Ekranı", "brightness": internal_brightness, "max": 100, "type": "internal"})
    
    logger.info(f"Tarama Tamamlandı. Toplam {len(results)} monitör bulundu.")
    return results

class MonoSlider(QSlider):
    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.setStyleSheet("QSlider::groove:horizontal { height: 2px; background: #222; border-radius: 1px; } QSlider::sub-page:horizontal { background: #fff; } QSlider::sub-page:horizontal:disabled { background: #444; } QSlider::handle:horizontal { width: 14px; height: 14px; margin: -6px 0; background: #fff; border-radius: 7px; } QSlider::handle:horizontal:disabled { background: #333; }")

class MonoCard(QFrame):
    value_changed = pyqtSignal(str, int)   # debounced → worker calls
    value_dragging = pyqtSignal(str, int)  # immediate → visual sync during drag
    def __init__(self, info):
        super().__init__()
        self.info = info; self.setObjectName("card")
        self.setStyleSheet("#card { background: #080808; border: 1px solid #151515; border-radius: 8px; } #card:hover { border-color: #252525; }")
        layout = QVBoxLayout(self); layout.setContentsMargins(12, 10, 12, 10)
        h = QHBoxLayout(); n = QLabel(info["name"].upper()); n.setFont(QFont("Segoe UI", 7, QFont.Bold)); n.setStyleSheet("color: #555;")
        h.addWidget(n); h.addStretch(); self.v_lbl = QLabel(f"{info['brightness']}%"); self.v_lbl.setFont(QFont("Segoe UI", 9, QFont.Bold)); self.v_lbl.setStyleSheet("color: #fff;")
        h.addWidget(self.v_lbl); layout.addLayout(h); self.slider = MonoSlider(); self.slider.setRange(0, info["max"])
        self.slider.blockSignals(True); self.slider.setValue(info["brightness"]); self.slider.blockSignals(False)
        self._pending_val = None
        self._debounce = QTimer(); self._debounce.setSingleShot(True); self._debounce.timeout.connect(self._emit_debounced)
        self.slider.valueChanged.connect(self._on_change); layout.addWidget(self.slider)
    def _on_change(self, v):
        self.v_lbl.setText(f"{v}%")
        self.value_dragging.emit(self.info["id"], v)  # anlık görsel sync
        self._pending_val = v; self._debounce.start(150)
    def _emit_debounced(self):
        if self._pending_val is not None: self.value_changed.emit(self.info["id"], self._pending_val)
    def set_value(self, v): self.slider.blockSignals(True); self.slider.setValue(v); self.v_lbl.setText(f"{v}%"); self.slider.blockSignals(False)

class QuickPanel(QWidget):
    value_changed = pyqtSignal(str, int); value_dragging = pyqtSignal(str, int); sync_toggled = pyqtSignal(bool)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground); self.setFixedWidth(280)
        self.main_layout = QVBoxLayout(self); self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.container = QFrame(); self.container.setObjectName("container")
        self.container.setStyleSheet("#container { background: #000; border: 1px solid #222; border-radius: 12px; }")
        self.main_layout.addWidget(self.container)
        l = QVBoxLayout(self.container); l.setContentsMargins(15, 15, 15, 15)
        h = QHBoxLayout(); t = QLabel("LUMINA QUICK"); t.setFont(QFont("Segoe UI", 7, QFont.Bold)); t.setStyleSheet("color: #444; letter-spacing: 1px;"); h.addWidget(t); h.addStretch()
        self.sync_btn = QPushButton("\u21c4"); self.sync_btn.setCheckable(True); self.sync_btn.setFixedSize(28, 28); self.sync_btn.setCursor(Qt.PointingHandCursor)
        self.sync_btn.setStyleSheet("QPushButton { color: #444; background: transparent; border: 1px solid #222; border-radius: 4px; font-size: 14px; } QPushButton:checked { color: #fff; border-color: #fff; background: #111; }")
        self.sync_btn.clicked.connect(lambda: self.sync_toggled.emit(self.sync_btn.isChecked())); h.addWidget(self.sync_btn); l.addLayout(h)
        self._sync_lbl = QLabel("● SENKRONIZE EDİLİYOR")
        self._sync_lbl.setFont(QFont("Segoe UI", 7, QFont.Bold))
        self._sync_lbl.setStyleSheet("color: #e94560; letter-spacing: 1px; padding: 4px 0;")
        self._sync_lbl.hide(); l.addWidget(self._sync_lbl)
        self.list_layout = QVBoxLayout(); l.addLayout(self.list_layout); self._cards = []
    def set_syncing(self, syncing):
        if syncing: self._sync_lbl.show()
        else: self._sync_lbl.hide()
        self.adjustSize()
    def update_monitors(self, data):
        for c in self._cards: self.list_layout.removeWidget(c); c.deleteLater()
        self._cards = []
        for info in data:
            card = MonoCard(info)
            card.value_changed.connect(self.value_changed.emit)
            card.value_dragging.connect(self.value_dragging.emit)
            self.list_layout.addWidget(card); self._cards.append(card)
        self.adjustSize()

class ScheduleItem(QFrame):
    removed = pyqtSignal(object)
    def __init__(self, data=None):
        super().__init__()
        self.setStyleSheet("QFrame { background: #080808; border-radius: 8px; border: 1px solid #151515; }")
        v_lay = QVBoxLayout(self); v_lay.setContentsMargins(15, 15, 15, 15); v_lay.setSpacing(12)
        h1 = QHBoxLayout(); h1.setSpacing(10)
        l1 = QLabel("ARALIK:"); l1.setStyleSheet("color: #555; font-size: 8px; font-weight: bold; border: none;")
        self.t1 = QTimeEdit(); self.t1.setDisplayFormat("HH:mm"); self.t1.setStyleSheet("background: #000; color: #fff; border: 1px solid #222; border-radius: 4px; padding: 4px; font-size: 10px;")
        l_to = QLabel("\u2192"); l_to.setStyleSheet("color: #333; border: none;")
        self.t2 = QTimeEdit(); self.t2.setDisplayFormat("HH:mm"); self.t2.setStyleSheet("background: #000; color: #fff; border: 1px solid #222; border-radius: 4px; padding: 4px; font-size: 10px;")
        btn = QPushButton("SİL"); btn.setFixedSize(40, 24); btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("QPushButton { background: #111; color: #e94560; border: 1px solid #222; border-radius: 4px; font-size: 8px; font-weight: bold; } QPushButton:hover { background: #e9456022; border-color: #e94560; }")
        btn.clicked.connect(lambda: self.removed.emit(self))
        h1.addWidget(l1); h1.addWidget(self.t1); h1.addWidget(l_to); h1.addWidget(self.t2); h1.addStretch(); h1.addWidget(btn)
        v_lay.addLayout(h1)
        h2 = QHBoxLayout(); h2.setSpacing(10)
        l2 = QLabel("PARLAKLIK:"); l2.setStyleSheet("color: #555; font-size: 8px; font-weight: bold; border: none;")
        self.s = MonoSlider(); self.s.setRange(0, 100)
        self.v = QLabel("50%"); self.v.setFixedWidth(35); self.v.setStyleSheet("color: #fff; font-size: 10px; font-weight: bold; border: none; background: transparent;")
        self.s.valueChanged.connect(lambda val: self.v.setText(f"{val}%"))
        if data and isinstance(data, dict):
            self.t1.setTime(QTime.fromString(data["start"], "HH:mm")); self.t2.setTime(QTime.fromString(data["end"], "HH:mm"))
            self.s.setValue(data["val"]); self.v.setText(f"{data['val']}%")
        else: self.s.setValue(50)
        h2.addWidget(l2); h2.addWidget(self.s); h2.addWidget(self.v); v_lay.addLayout(h2)
    def get_data(self): return {"start": self.t1.time().toString("HH:mm"), "end": self.t2.time().toString("HH:mm"), "val": self.s.value()}

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LUMINA")
        self.settings = QSettings("NIGHT", "LUMINA_APP")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground); self.setFixedSize(560, 580)
        
        if os.path.exists(LOGO_PATH): self.setWindowIcon(QIcon(LOGO_PATH))
            
        self._drag_pos = None; self._cards = []
        self._last_mon_data = self.settings.value("monitor_cache", [])
        self._sync_mode = self.settings.value("sync", False, type=bool); self._last_applied_sched = None
        self._initializing = True
        
        self.worker = BrightnessWorker(); self.worker.start()
        
        self.main_layout = QVBoxLayout(self)
        self.container = QFrame(); self.container.setObjectName("container")
        self.container.setStyleSheet("#container { background: #000; border: 1px solid #1a1a1a; border-radius: 12px; }")
        self.main_layout.addWidget(self.container)
        self.content_layout = QHBoxLayout(self.container); self.content_layout.setContentsMargins(0, 0, 0, 0); self.content_layout.setSpacing(0)
        
        sidebar = QFrame(); sidebar.setFixedWidth(160); sidebar.setStyleSheet("background: #050505; border-right: 1px solid #111;")
        slayout = QVBoxLayout(sidebar); slayout.setContentsMargins(0, 20, 0, 20)
        
        if os.path.exists(LOGO_PATH):
            logo_img = QLabel(); logo_pix = QPixmap(LOGO_PATH).scaled(60, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_img.setPixmap(logo_pix); logo_img.setAlignment(Qt.AlignCenter); logo_img.setStyleSheet("margin-bottom: 10px;"); slayout.addWidget(logo_img)
            
        logo_text = QLabel("LUMINA"); logo_text.setFont(QFont("Segoe UI", 12, QFont.Black)); logo_text.setStyleSheet("color: #fff; margin-bottom: 30px; letter-spacing: 4px;"); logo_text.setAlignment(Qt.AlignCenter); slayout.addWidget(logo_text)
        
        self.b1 = self._nav("DENETİM MASASI", True, 0); self.b2 = self._nav("ZAMANLAYICI", False, 1); self.b3 = self._nav("AYARLAR", False, 2)
        slayout.addWidget(self.b1); slayout.addWidget(self.b2); slayout.addWidget(self.b3); slayout.addStretch()
        q = QPushButton("SİSTEMDEN ÇIK"); q.setStyleSheet("color: #333; font-size: 8px; border: none; text-align: left; padding: 20px; font-weight: bold;"); q.clicked.connect(QApplication.quit); slayout.addWidget(q)
        self.content_layout.addWidget(sidebar)
        
        self.pages_container = QFrame(); self.pages_layout = QVBoxLayout(self.pages_container); self.pages_layout.setContentsMargins(0, 0, 0, 0)
        self.header_btn_layout = QHBoxLayout(); self.header_btn_layout.setContentsMargins(0, 15, 15, 0); self.header_btn_layout.addStretch()
        self.close_btn = QPushButton("\u00d7"); self.close_btn.setFixedSize(28, 28); self.close_btn.setStyleSheet("color: #444; border: 1px solid #111; border-radius: 14px; font-size: 16px;"); self.close_btn.clicked.connect(self.hide)
        self.header_btn_layout.addWidget(self.close_btn); self.pages_layout.addLayout(self.header_btn_layout)
        
        self.pages = QStackedWidget(); self.pages_layout.addWidget(self.pages); self.content_layout.addWidget(self.pages_container)
        self._init_p1(); self._init_p2(); self._init_p3()
        
        self.status_bar = QFrame(self.container); self.status_bar.setFixedHeight(30); self.status_bar.setObjectName("status_bar")
        self.status_bar.setStyleSheet("#status_bar { background: #e94560; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }")
        sb_lay = QHBoxLayout(self.status_bar); sb_lay.setContentsMargins(15, 0, 15, 0)
        self.status_msg = QLabel("SİSTEM SENKRONİZE EDİLİYOR, LÜTFEN BEKLEYİN..."); self.status_msg.setFont(QFont("Segoe UI", 7, QFont.Bold)); self.status_msg.setStyleSheet("color: #fff;"); sb_lay.addWidget(self.status_msg); sb_lay.addStretch()
        self.pages_layout.addWidget(self.status_bar)
        
        self.quick = QuickPanel(); self.quick.sync_btn.setChecked(self._sync_mode)
        self.quick.value_changed.connect(self._on_brightness_change)
        self.quick.value_dragging.connect(self._on_brightness_drag)
        self.quick.sync_toggled.connect(self._set_sync)
        self._init_tray()
        
        if self._last_mon_data:
            # Kartları cached değerlerle göster ama kilitli — gerçek brightness gelince açılır
            self._show_monitors(self._last_mon_data)
            self.quick.update_monitors(self._last_mon_data)
            self._set_ui_enabled(False)
            self._scan_only_brightness = True
            self.refresh_monitors(only_brightness=True)
            QTimer.singleShot(10000, self._end_initialization)  # fallback
        else:
            self._scan_only_brightness = False
            self.refresh_monitors(force=True, only_brightness=False)
            self._set_ui_enabled(False)
            QTimer.singleShot(25000, self._end_initialization)
        self.timer = QTimer(); self.timer.timeout.connect(self._check_schedules); self.timer.start(30000)

    def _set_ui_enabled(self, enabled):
        for c in self._cards: c.slider.setEnabled(enabled)
        for c in self.quick._cards: c.slider.setEnabled(enabled)
        self.quick.sync_btn.setEnabled(enabled); self.sy.setEnabled(enabled)
        self.quick.set_syncing(not enabled)

    def _end_initialization(self):
        if not self._initializing: return
        self._initializing = False; logger.info("Başlatma modu sona erdi."); self.status_bar.hide(); self._set_ui_enabled(True)

    def _nav(self, t, a, i):
        btn = QPushButton(t); btn.setCheckable(True); btn.setChecked(a); btn.setFixedHeight(40); btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("QPushButton { background: transparent; color: #555; border: none; text-align: left; padding-left: 20px; font-size: 9px; font-weight: bold; letter-spacing: 1px; } QPushButton:checked { color: #fff; border-left: 3px solid #fff; padding-left: 17px; }")
        btn.clicked.connect(lambda: self._switch(i)); return btn
    def _switch(self, i): self.pages.setCurrentIndex(i); self.b1.setChecked(i==0); self.b2.setChecked(i==1); self.b3.setChecked(i==2)

    def _init_p1(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(30, 0, 30, 30)
        h = QHBoxLayout(); t = QLabel("MONİTÖRLER"); t.setFont(QFont("Segoe UI", 11, QFont.Bold)); t.setStyleSheet("color: #fff;"); h.addWidget(t); h.addStretch()
        r = QPushButton("\u21bb"); r.setFixedSize(28, 28); r.setStyleSheet("color: #444; border: 1px solid #111; border-radius: 14px;"); r.clicked.connect(lambda: self.refresh_monitors(force=True)); h.addWidget(r)
        l.addLayout(h); self.mon_layout = QVBoxLayout(); self.mon_layout.setSpacing(10); l.addLayout(self.mon_layout); l.addStretch(); self.pages.addWidget(p)

    def _init_p2(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(30, 0, 30, 30)
        t = QLabel("OTOMATİK ZAMANLAYICI"); t.setFont(QFont("Segoe UI", 11, QFont.Bold)); t.setStyleSheet("color: #fff; margin-bottom: 15px;"); l.addWidget(t)
        self.sc = QScrollArea(); self.sc.setWidgetResizable(True); self.sc.setStyleSheet("background: transparent; border: none;")
        self.sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.sc.verticalScrollBar().setStyleSheet("QScrollBar:vertical { width: 4px; background: #000; } QScrollBar::handle:vertical { background: #222; border-radius: 2px; }")
        self.cw = QWidget(); self.cl = QVBoxLayout(self.cw); self.cl.setSpacing(10); self.cl.setContentsMargins(0, 0, 10, 0); self.cl.addStretch(); self.sc.setWidget(self.cw); l.addWidget(self.sc)
        a = QPushButton("+ YENİ KURAL EKLE"); a.setFixedHeight(35); a.setStyleSheet("background: #080808; color: #fff; border: 1px solid #222; border-radius: 6px; font-size: 9px; font-weight: bold;"); a.clicked.connect(lambda: self._add_s()); l.addWidget(a)
        s = QPushButton("AYARLARI KAYDET VE UYGULA"); s.setFixedHeight(40); s.setStyleSheet("background: #fff; color: #000; border-radius: 6px; font-weight: bold; margin-top: 10px;"); s.clicked.connect(self._save_s); l.addWidget(s)
        for d in self.settings.value("schedules", []): self._add_s(d)
        self.pages.addWidget(p)

    def _add_s(self, data=None):
        try:
            w = ScheduleItem(data); self.cl.insertWidget(self.cl.count()-1, w)
            w.removed.connect(lambda x: x.deleteLater()); w.show()
        except Exception: pass

    def _save_s(self):
        d = [self.cl.itemAt(i).widget().get_data() for i in range(self.cl.count()) if isinstance(self.cl.itemAt(i).widget(), ScheduleItem)]
        self.settings.setValue("schedules", d); self._last_applied_sched = None; self._check_schedules()

    def _check_schedules(self):
        n = QTime.currentTime().toString("HH:mm"); active = None
        for s in self.settings.value("schedules", []):
            if s["start"] <= n < s["end"]: active = s; break
        if active and active != self._last_applied_sched:
            logger.info(f"Zamanlayıcı Kuralı Tetiklendi: {active}")
            self._last_applied_sched = active
            for c in self._cards: c.set_value(active["val"]); self.worker.update_brightness(c.info["id"], active["val"])
            for c in self.quick._cards: c.set_value(active["val"]); self.worker.update_brightness(c.info["id"], active["val"])
        elif not active: self._last_applied_sched = None

    def _init_p3(self):
        p = QWidget(); l = QVBoxLayout(p); l.setContentsMargins(30, 0, 30, 30)
        t = QLabel("SİSTEM AYARLARI"); t.setFont(QFont("Segoe UI", 11, QFont.Bold)); t.setStyleSheet("color: #fff; margin-bottom: 20px;"); l.addWidget(t)
        self.st = QCheckBox("BİLGİSAYAR AÇILDIĞINDA BAŞLAT"); self.st.setChecked(self._get_st()); self.st.toggled.connect(self._set_st); self._style_cb(self.st); l.addWidget(self.st)
        self.sy = QCheckBox("EŞİTLEME MODUNU AKTİFLEŞTİR (SYNC)"); self.sy.setChecked(self._sync_mode); self.sy.toggled.connect(self._set_sync); self._style_cb(self.sy); l.addWidget(self.sy)
        l.addStretch(); self.pages.addWidget(p)

    def _style_cb(self, cb): cb.setStyleSheet("QCheckBox { color: #555; font-size: 9px; font-weight: bold; spacing: 10px; margin-bottom: 15px; } QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #151515; background: #000; border-radius: 3px; } QCheckBox::indicator:checked { background: #fff; }")
    def _set_sync(self, on):
        logger.info(f"Sync Modu Değişti: {on}")
        self._sync_mode = on; self.settings.setValue("sync", on); self.sy.blockSignals(True); self.sy.setChecked(on); self.sy.blockSignals(False)
        self.quick.sync_btn.blockSignals(True); self.quick.sync_btn.setChecked(on); self.quick.sync_btn.blockSignals(False)
        if on and not self._initializing:
            v = None
            if self._cards: v = self._cards[0].slider.value()
            elif self.quick._cards: v = self.quick._cards[0].slider.value()
            if v is not None:
                for c in self._cards: c.set_value(v); self.worker.update_brightness(c.info["id"], v)
                for c in self.quick._cards: c.set_value(v); self.worker.update_brightness(c.info["id"], v)

    def _get_st(self):
        try: k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ); winreg.QueryValueEx(k, "LUMINA"); return True
        except Exception: return False
    def _set_st(self, en):
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            if en: winreg.SetValueEx(k, "LUMINA", 0, winreg.REG_SZ, sys.executable if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"')
            else: winreg.DeleteValue(k, "LUMINA")
            logger.info(f"Başlangıçta Çalıştırma: {en}")
        except Exception: pass

    def refresh_monitors(self, force=False, only_brightness=False):
        class ST(QThread):
            done = pyqtSignal(list)
            def __init__(self, parent, only_b, cached): super().__init__(parent); self.only_b = only_b; self.cached = cached
            def run(self): self.done.emit(get_monitors_data(only_brightness=self.only_b, cached_monitors=self.cached))
        if hasattr(self, "scan") and self.scan.isRunning(): return
        self._scan_only_brightness = only_brightness
        self.scan = ST(self, only_brightness, self._last_mon_data if (only_brightness and not force) else None); self.scan.done.connect(self._on_scan_done); self.scan.start()
    def _on_scan_done(self, res):
        logger.info(f"Tarama Tamamlandı, UI Güncelleniyor ({len(res)} monitör)")
        self._last_mon_data = res; self.settings.setValue("monitor_cache", res)
        if getattr(self, '_scan_only_brightness', False):
            for mon in res:
                for c in self._cards + self.quick._cards:
                    if c.info["id"] == mon["id"]:
                        c.set_value(mon["brightness"]); c.info["brightness"] = mon["brightness"]
        else:
            self._show_monitors(res); self.quick.update_monitors(res)
        if self._initializing: self._end_initialization()

    def _show_monitors(self, data):
        for c in self._cards: self.mon_layout.removeWidget(c); c.deleteLater()
        self._cards = []
        for info in data:
            card = MonoCard(info)
            card.value_changed.connect(self._on_brightness_change)
            card.value_dragging.connect(self._on_brightness_drag)
            card.slider.setEnabled(not self._initializing)
            self.mon_layout.addWidget(card); self._cards.append(card)

    def _on_brightness_drag(self, mid, val):
        """Her slider hareketi: görsel sync, worker yok (debounce beklenir)"""
        if self._initializing: return
        for c in self._cards + self.quick._cards:
            if c.info["id"] == mid: c.set_value(val)
        if self._sync_mode:
            for c in self._cards + self.quick._cards:
                if c.info["id"] != mid: c.set_value(val)

    def _on_brightness_change(self, mid, val):
        """Debounce sonrası: worker çağrıları"""
        if self._initializing: return
        self.worker.update_brightness(mid, val)
        if self._sync_mode:
            seen_ids = {mid}
            for c in self._cards + self.quick._cards:
                cid = c.info["id"]
                if cid != mid and cid not in seen_ids:
                    seen_ids.add(cid); self.worker.update_brightness(cid, val)

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self)
        if os.path.exists(LOGO_PATH): self.tray.setIcon(QIcon(LOGO_PATH))
        else:
            px = QPixmap(64, 64); px.fill(Qt.transparent); p = QPainter(px); p.setBrush(QColor("#fff")); p.drawEllipse(10, 10, 44, 44); p.end()
            self.tray.setIcon(QIcon(px))
        self.tray.setToolTip("LUMINA")
        menu = QMenu(); menu.setStyleSheet("background: #000; color: #fff; border: 1px solid #111;")
        menu.addAction("Panel").triggered.connect(self.show_at_center); menu.addSeparator(); menu.addAction("Kapat").triggered.connect(QApplication.quit)
        self.tray.setContextMenu(menu); self.tray.activated.connect(self._on_tray_activated); self.tray.show()
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger: (self.quick.hide() if self.quick.isVisible() else self.show_quick_panel())
        elif reason == QSystemTrayIcon.DoubleClick: self.show_at_center()
    def show_quick_panel(self):
        if not self.quick._cards: self.quick.update_monitors(self._last_mon_data)
        p = QCursor.pos()
        self.quick.move(p.x() - self.quick.width() // 2, p.y() - self.quick.height() - 20)
        self.quick.show(); self.quick.activateWindow()
        now = time.time()
        if not hasattr(self, '_last_quick_refresh') or now - self._last_quick_refresh > 5:
            self._last_quick_refresh = now; self._scan_only_brightness = True; self.refresh_monitors(only_brightness=True)
    def show_at_center(self):
        g = QApplication.primaryScreen().availableGeometry(); self.move(g.center() - self.rect().center()); self.show(); self.raise_(); self.activateWindow()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if self._drag_pos: self.move(e.globalPos() - self._drag_pos)
    def mouseReleaseEvent(self, e): self._drag_pos = None

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False); win = MainWindow(); win.show(); sys.exit(app.exec_())
