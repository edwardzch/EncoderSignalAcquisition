import sys
import os
import serial.tools.list_ports
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog, QGridLayout, QLabel, QDoubleSpinBox, QDialogButtonBox, QGroupBox, QVBoxLayout, QScrollArea, QHBoxLayout, QPushButton, QWidget
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer, Qt, QSettings
import numpy as np
import pyqtgraph as pg

# Configure pyqtgraph for maximum performance
pg.setConfigOptions(antialias=False)
pg.setConfigOption('background', '#1e1e1e')
pg.setConfigOption('foreground', '#cccccc')

from ui_layout import UILayout
from serial_worker import SerialWorker
from plot_manager import PlotManager


class LimitsDialog(QDialog):
    """Dialog to set upper/lower limits for auto measurements."""
    def __init__(self, limits, parent=None):
        super().__init__(parent)
        self.setWindowTitle("测量范围设置 (Measurement Limits)")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.setMinimumWidth(600)
        self.resize(650, 700)
        self.limits = limits  # dict of key -> (low, high)
        self.spinboxes = {}
        
        main_layout = QVBoxLayout(self)
        
        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        
        # --- Phase Diff Limits ---
        phase_group = QGroupBox("相位差范围 (°)")
        phase_layout = QGridLayout()
        phase_layout.addWidget(QLabel("码道"), 0, 0)
        phase_layout.addWidget(QLabel("下限"), 0, 1)
        phase_layout.addWidget(QLabel("上限"), 0, 2)
        
        for row, ch in enumerate(["M", "N", "S"], 1):
            key = f"PHASE_{ch}"
            lo, hi = self.limits.get(key, (-180.0, 180.0))
            phase_layout.addWidget(QLabel(f"{ch} 码道"), row, 0)
            
            lo_spin = QDoubleSpinBox()
            lo_spin.setRange(-360, 360)
            lo_spin.setDecimals(2)
            lo_spin.setValue(lo)
            phase_layout.addWidget(lo_spin, row, 1)
            
            hi_spin = QDoubleSpinBox()
            hi_spin.setRange(-360, 360)
            hi_spin.setDecimals(2)
            hi_spin.setValue(hi)
            phase_layout.addWidget(hi_spin, row, 2)
            
            self.spinboxes[key] = (lo_spin, hi_spin)
        
        phase_group.setLayout(phase_layout)
        content_layout.addWidget(phase_group)
        
        # --- Channel Stats Limits ---
        stats_group = QGroupBox("通道极值范围")
        stats_layout = QGridLayout()
        stats_layout.addWidget(QLabel("通道"), 0, 0)
        stats_layout.addWidget(QLabel("指标"), 0, 1)
        stats_layout.addWidget(QLabel("下限"), 0, 2)
        stats_layout.addWidget(QLabel("上限"), 0, 3)
        
        channels = ["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS"]
        metrics = ["MAX", "MIN", "OFS"]
        row = 1
        for ch in channels:
            for metric in metrics:
                key = f"{ch}_{metric}"
                lo, hi = self.limits.get(key, (0.0, 4095.0))
                
                stats_layout.addWidget(QLabel(ch), row, 0)
                stats_layout.addWidget(QLabel(metric), row, 1)
                
                lo_spin = QDoubleSpinBox()
                lo_spin.setRange(-10000, 10000)
                lo_spin.setDecimals(1)
                lo_spin.setValue(lo)
                stats_layout.addWidget(lo_spin, row, 2)
                
                hi_spin = QDoubleSpinBox()
                hi_spin.setRange(-10000, 10000)
                hi_spin.setDecimals(1)
                hi_spin.setValue(hi)
                stats_layout.addWidget(hi_spin, row, 3)
                
                self.spinboxes[key] = (lo_spin, hi_spin)
                row += 1
        
        # Copy SIN → COS button
        copy_btn = QPushButton("复制 SIN 范围 → COS")
        copy_btn.clicked.connect(self._copy_sin_to_cos)
        stats_layout.addWidget(copy_btn, row, 0, 1, 4)
        
        stats_group.setLayout(stats_layout)
        content_layout.addWidget(stats_group)
        
        # --- MTAB/HALL Limits ---
        digital_group = QGroupBox("MTAB / HALL 范围")
        digital_layout = QGridLayout()
        digital_layout.addWidget(QLabel("参数"), 0, 0)
        digital_layout.addWidget(QLabel("下限"), 0, 1)
        digital_layout.addWidget(QLabel("上限"), 0, 2)
        
        digital_params = [
            ("MTA占空比 (%)", "MTA_DUTY", 40.0, 60.0),
            ("MTB占空比 (%)", "MTB_DUTY", 40.0, 60.0),
            ("MTAB相位差 (°)", "MTAB_PHASE", -180.0, 180.0),
            ("HALL1占空比 (%)", "HALL1_DUTY", 40.0, 60.0),
            ("HALL2占空比 (%)", "HALL2_DUTY", 40.0, 60.0),
            ("HALL相位差 (°)", "HALL_PHASE", -180.0, 180.0),
        ]
        for d_row, (label, key, def_lo, def_hi) in enumerate(digital_params, 1):
            lo, hi = self.limits.get(key, (def_lo, def_hi))
            digital_layout.addWidget(QLabel(label), d_row, 0)
            
            lo_spin = QDoubleSpinBox()
            lo_spin.setRange(-360, 360)
            lo_spin.setDecimals(2)
            lo_spin.setValue(lo)
            digital_layout.addWidget(lo_spin, d_row, 1)
            
            hi_spin = QDoubleSpinBox()
            hi_spin.setRange(-360, 360)
            hi_spin.setDecimals(2)
            hi_spin.setValue(hi)
            digital_layout.addWidget(hi_spin, d_row, 2)
            
            self.spinboxes[key] = (lo_spin, hi_spin)
        
        digital_group.setLayout(digital_layout)
        content_layout.addWidget(digital_group)
        
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, stretch=1)
        
        # Buttons (always visible at the bottom, outside scroll area)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)
    
    def _copy_sin_to_cos(self):
        """Copy SIN channel limits to corresponding COS channels."""
        for prefix in ["M", "N", "S"]:
            for metric in ["MAX", "MIN", "OFS"]:
                sin_key = f"{prefix}_SIN_{metric}"
                cos_key = f"{prefix}_COS_{metric}"
                if sin_key in self.spinboxes and cos_key in self.spinboxes:
                    sin_lo, sin_hi = self.spinboxes[sin_key]
                    cos_lo, cos_hi = self.spinboxes[cos_key]
                    cos_lo.setValue(sin_lo.value())
                    cos_hi.setValue(sin_hi.value())
    
    def get_limits(self):
        result = {}
        for key, (lo_spin, hi_spin) in self.spinboxes.items():
            result[key] = (lo_spin.value(), hi_spin.value())
        return result


class MainWindow(UILayout):
    def __init__(self):
        super().__init__()
        
        # Set Application Icon
        icon_path = self.get_resource_path("sincos.ico")
        self.setWindowIcon(QIcon(icon_path))
        
        self.serial_worker = None
        self.plot_manager = PlotManager(self.time_plot_widget, self.lissajous_plots)
        self.plot_manager.on_single_complete = self.on_single_complete
        
        self.refresh_ports()
        
        self.refresh_ports_btn.clicked.connect(self.refresh_ports)
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.setup_btn.clicked.connect(self.toggle_setup_sequence)
        
        # UI updates to plot manager
        for cb in self.var_checkboxes:
            cb.stateChanged.connect(self.update_plot_vars)
            
        self.trig_src_combo.currentIndexChanged.connect(self.update_trigger)
        self.trig_level_spin.valueChanged.connect(self.update_trigger)
        self.trig_edge_combo.currentTextChanged.connect(self.update_trigger)
        self.pre_trig_spin.valueChanged.connect(self.update_trigger)
        self.points_spin.valueChanged.connect(self.update_points)
        self.downsample_spin.valueChanged.connect(self.update_points)
        
        self.continuous_btn.clicked.connect(self.on_continuous_clicked)
        self.single_btn.clicked.connect(self.on_single_clicked)
        
        # Measurement Connections
        self.meas_algo.currentIndexChanged.connect(self.update_meas_algo)
        
        self.meas_timer = QTimer()
        self.meas_timer.timeout.connect(self.update_meas_labels)
        self.meas_timer.start(200) # Update label 5 times a second
        
        # Menu connections
        self.limits_action.triggered.connect(self.open_limits_dialog)
        
        # Persistent settings (Windows registry)
        self.settings = QSettings("EncoderSignalAcquisition", "Settings")
        self.meas_limits = self._load_limits()
        
        # Command Sequence State
        self.seq_timer = QTimer()
        self.seq_timer.timeout.connect(self.execute_next_sequence)
        self.seq_step = 0
        
        self.update_plot_vars()
        self.update_trigger()
        self.update_points()
        self.update_meas_algo()
        
        # Restore saved panel settings (must be after signal connections)
        self._load_panel_settings()
        
    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            # Display format: "COMx - Description [HWID]"
            display_text = f"{p.device} - {p.description}"
            self.port_combo.addItem(display_text, userData=p.device)
            
    def toggle_connection(self):
        if self.serial_worker and self.serial_worker.running:
            self.serial_worker.stop()
            self.connect_btn.setText("连接采集卡")
            self.port_combo.setEnabled(True)
            self.baud_combo.setEnabled(True)
        else:
            if self.port_combo.currentIndex() < 0:
                QMessageBox.warning(self, "Error", "请选择串口")
                return
                
            port = self.port_combo.currentData()
            baudrate = int(self.baud_combo.currentText())
                
            self.serial_worker = SerialWorker(port, baudrate)
            self.serial_worker.data_received.connect(self.plot_manager.add_data)
            self.serial_worker.error_occurred.connect(self.on_serial_error)
            self.serial_worker.connection_status.connect(self.on_connection_status)
            self.serial_worker.start()
            
    def on_connection_status(self, connected):
        if connected:
            self.connect_btn.setText("断开端口")
            self.connect_btn.setStyleSheet("background-color: #A33; color: white;")
            self.port_combo.setEnabled(False)
            self.baud_combo.setEnabled(False)
        else:
            self.connect_btn.setText("连接端口")
            self.connect_btn.setStyleSheet("")
            self.port_combo.setEnabled(True)
            self.baud_combo.setEnabled(True)
            
    def on_serial_error(self, err):
        QMessageBox.critical(self, "Serial Error", err)
        self.on_connection_status(False)
        
    def toggle_setup_sequence(self):
        if not self.serial_worker or not self.serial_worker.running:
            QMessageBox.warning(self, "Error", "请先连接串口")
            self.setup_btn.setChecked(False)
            return
            
        if self.setup_btn.isChecked():
            self.setup_btn.setText("取消")
            self.seq_step = 1
            self.execute_next_sequence()
        else:
            self.setup_btn.setText("设置")
            self.start_reset_sequence()
            self.seq_timer.stop()
            self.seq_step = 0
            
    def start_reset_sequence(self):
        self.reset_count = 0
        self.reset_timer = QTimer(self)
        self.reset_timer.timeout.connect(self.send_reset_pulse)
        self.reset_timer.start(10) # 10ms interval
        
    def send_reset_pulse(self):
        if self.serial_worker and self.serial_worker.ser and self.serial_worker.ser.is_open:
            try:
                self.serial_worker.ser.write(bytes([0x05, 0x06, 0x10, 0x10, 0x5A, 0xA5, 0x77, 0x90]))
                self.serial_worker.ser.flush()
            except Exception:
                pass
        
        self.reset_count += 1
        if self.reset_count >= 10:
            self.reset_timer.stop()
            
    def execute_next_sequence(self):
        if self.seq_step == 1:
            # 1. 05 06 10 00 00 01 4D 4E
            self.serial_worker.send_data(bytes([0x05, 0x06, 0x10, 0x00, 0x00, 0x01, 0x4D, 0x4E]))
            self.seq_step = 2
            self.seq_timer.start(1000) # Wait 1s
            
        elif self.seq_step == 2:
            self.seq_timer.stop()
            enc_type = self.encoder_type_combo.currentIndex()
            if enc_type == 0: # Optical
                self.serial_worker.send_data(bytes([0x05, 0x06, 0x00, 0x04, 0x00, 0x02, 0x48, 0x4E]))
            else: # Magnetic
                self.serial_worker.send_data(bytes([0x05, 0x06, 0x00, 0x04, 0x00, 0x01, 0x08, 0x4F]))
            
            self.seq_step = 3
            self.seq_timer.start(100) # Wait 100ms
            
        elif self.seq_step == 3:
            self.seq_timer.stop()
            enc_type = self.encoder_type_combo.currentIndex()
            if enc_type == 0: # Optical
                self.serial_worker.send_data(bytes([0x05, 0x06, 0x03, 0x07, 0x00, 0x01, 0xF8, 0x0B]))
            else: # Magnetic
                self.serial_worker.send_data(bytes([0x05, 0x06, 0x02, 0x07, 0x00, 0x01, 0xFA, 0x7B]))
                
            self.seq_step = 4
            self.seq_timer.start(100) # Wait 100ms
            
        elif self.seq_step == 4:
            self.seq_timer.stop()
            # 4. Start Acq: 05 06 00 0C 00 01 89 8D
            self.serial_worker.send_data(bytes([0x05, 0x06, 0x00, 0x0C, 0x00, 0x01, 0x89, 0x8D]))
            self.seq_step = 0
            
    def update_plot_vars(self):
        states = [cb.isChecked() for cb in self.var_checkboxes]
        self.plot_manager.set_active_vars(states)
        
    def get_resource_path(self, relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

        
    def update_trigger(self):
        # Index 0 is "None", so if > 0, subtract 1 for the actual variable index
        idx = self.trig_src_combo.currentIndex()
        if idx == 0:
            self.plot_manager.trigger_source = -1
        else:
            self.plot_manager.trigger_source = idx - 1
            
        self.plot_manager.trigger_level = self.trig_level_spin.value()
        self.plot_manager.trigger_edge = self.trig_edge_combo.currentText()
        self.plot_manager.pre_trigger = self.pre_trig_spin.value()
        
    def update_points(self):
        self.plot_manager.set_display_params(
            self.points_spin.value(),
            self.downsample_spin.value()
        )
        
    def update_meas_algo(self):
        self.plot_manager.meas_algo = self.meas_algo.currentIndex()
        
    def update_meas_labels(self):
        """Update all measurement labels with color-coded warnings."""
        green = "font-size: 13px; font-weight: bold; color: #55FF55;"
        red = "font-size: 13px; font-weight: bold; color: #FF5555;"
        green_phase = "font-size: 15px; font-weight: bold; color: #55FF55;"
        red_phase = "font-size: 15px; font-weight: bold; color: #FF5555;"
        
        # Update channel stats (Max, Min, Ofs for 6 channels)
        channels = ["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS"]
        metrics = ["MAX", "MIN", "OFS"]
        
        for ch in channels:
            for metric in metrics:
                key = f"{ch}_{metric}"
                val = self.plot_manager.channel_stats.get(key)
                lbl = self.meas_labels.get(key)
                if lbl is None:
                    continue
                    
                if val is None:
                    lbl.setText("--")
                    lbl.setStyleSheet(green)
                else:
                    lbl.setText(f"{val:.1f}")
                    # Check limits
                    if key in self.meas_limits:
                        lo, hi = self.meas_limits[key]
                        if lo <= val <= hi:
                            lbl.setStyleSheet(green)
                        else:
                            lbl.setStyleSheet(red)
                    else:
                        lbl.setStyleSheet(green)
        
        # Update phase diffs for M, N, S
        for ch_name in ["M", "N", "S"]:
            val = self.plot_manager.phase_diffs.get(ch_name)
            lbl = self.phase_labels.get(ch_name)
            if lbl is None:
                continue
                
            if val is None:
                lbl.setText("-- °")
                lbl.setStyleSheet(green)
            else:
                lbl.setText(f"{val:.2f} °")
                limit_key = f"PHASE_{ch_name}"
                if limit_key in self.meas_limits:
                    lo, hi = self.meas_limits[limit_key]
                    if lo <= val <= hi:
                        lbl.setStyleSheet(green)
                    else:
                        lbl.setStyleSheet(red)
                else:
                    lbl.setStyleSheet(green)

                # Update MTAB/HALL digital stats
                for key, lbl in self.digital_labels.items():
                    val = self.plot_manager.digital_stats.get(key)

                    if "GLITCH" in key:
                        if val is None:
                            lbl.setText("--")
                            lbl.setStyleSheet(green)
                        elif isinstance(val, dict):
                            # 如果抓取到的是 DETAIL 字典，把它格式化成文本显示
                            # 例如显示成: "0:0  1:0  2:0  3:0"
                            detail_str = "  ".join([f"{k}:{v}" for k, v in val.items()])
                            lbl.setText(detail_str)

                            # 如果字典里记录的毛刺总数 > 0，则标红
                            has_error = sum(val.values()) > 0
                            lbl.setStyleSheet(red if has_error else green)
                        else:
                            # 如果是总数 (integer)，直接显示并判断标红
                            count = int(val)
                            lbl.setText(str(count))
                            lbl.setStyleSheet(red if count > 0 else green)
                    else:
                        unit = "%" if "DUTY" in key else "°"
                        if val is None:
                            lbl.setText(f"-- {unit}")
                            lbl.setStyleSheet(green)
                        else:
                            lbl.setText(f"{val:.2f} {unit}")
                            if key in self.meas_limits:
                                lo, hi = self.meas_limits[key]
                                if lo <= val <= hi:
                                    lbl.setStyleSheet(green)
                                else:
                                    lbl.setStyleSheet(red)
                            else:
                                lbl.setStyleSheet(green)
    
    def open_limits_dialog(self):
        dialog = LimitsDialog(self.meas_limits, self)
        if dialog.exec() == QDialog.Accepted:
            self.meas_limits = dialog.get_limits()
            self._save_limits()
    
    def _save_limits(self):
        """Save measurement limits to Windows registry via QSettings."""
        self.settings.beginGroup("Limits")
        self.settings.remove("")  # Clear old keys
        for key, (lo, hi) in self.meas_limits.items():
            self.settings.setValue(f"{key}/lo", lo)
            self.settings.setValue(f"{key}/hi", hi)
        self.settings.endGroup()
        self.settings.sync()
    
    def _load_limits(self):
        """Load measurement limits from Windows registry via QSettings."""
        limits = {}
        self.settings.beginGroup("Limits")
        for key in self.settings.childGroups():
            lo = self.settings.value(f"{key}/lo", type=float)
            hi = self.settings.value(f"{key}/hi", type=float)
            limits[key] = (lo, hi)
        self.settings.endGroup()
        return limits
    
    def _save_panel_settings(self):
        """Save all right-panel configurations to registry."""
        s = self.settings
        s.beginGroup("Panel")
        
        # Serial
        s.setValue("baud_rate", self.baud_combo.currentText())
        
        # Encoder type
        s.setValue("encoder_type", self.encoder_type_combo.currentIndex())
        
        # Sampling
        s.setValue("downsample", self.downsample_spin.value())
        s.setValue("points", self.points_spin.value())
        
        # Trigger
        s.setValue("trig_source", self.trig_src_combo.currentIndex())
        s.setValue("trig_edge", self.trig_edge_combo.currentIndex())
        s.setValue("trig_level", self.trig_level_spin.value())
        s.setValue("pre_trigger", self.pre_trig_spin.value())
        
        # Variable checkboxes
        checked = [cb.isChecked() for cb in self.var_checkboxes]
        s.setValue("var_checked", checked)
        
        # Algorithm
        s.setValue("meas_algo", self.meas_algo.currentIndex())
        
        s.endGroup()
        s.sync()
    
    def _load_panel_settings(self):
        """Restore right-panel configurations from registry."""
        s = self.settings
        s.beginGroup("Panel")
        
        # Serial
        baud = s.value("baud_rate")
        if baud is not None:
            idx = self.baud_combo.findText(str(baud))
            if idx >= 0:
                self.baud_combo.setCurrentIndex(idx)
            else:
                self.baud_combo.setCurrentText(str(baud))
        
        # Encoder type
        enc = s.value("encoder_type")
        if enc is not None:
            self.encoder_type_combo.setCurrentIndex(int(enc))
        
        # Sampling
        ds = s.value("downsample")
        if ds is not None:
            self.downsample_spin.setValue(int(ds))
        pts = s.value("points")
        if pts is not None:
            self.points_spin.setValue(int(pts))
        
        # Trigger
        ts = s.value("trig_source")
        if ts is not None:
            self.trig_src_combo.setCurrentIndex(int(ts))
        te = s.value("trig_edge")
        if te is not None:
            self.trig_edge_combo.setCurrentIndex(int(te))
        tl = s.value("trig_level")
        if tl is not None:
            self.trig_level_spin.setValue(int(tl))
        pt = s.value("pre_trigger")
        if pt is not None:
            self.pre_trig_spin.setValue(int(pt))
        
        # Variable checkboxes
        checked = s.value("var_checked")
        if checked is not None and len(checked) == len(self.var_checkboxes):
            for cb, state in zip(self.var_checkboxes, checked):
                cb.setChecked(state == True or state == 'true')
        
        # Algorithm
        algo = s.value("meas_algo")
        if algo is not None:
            self.meas_algo.setCurrentIndex(int(algo))
        
        s.endGroup()
    
    def closeEvent(self, event):
        """Save all settings when the window is closed."""
        self._save_panel_settings()
        self._save_limits()
        super().closeEvent(event)
            
    def on_continuous_clicked(self):
        if self.continuous_btn.isChecked():
            self.continuous_btn.setText("停止采样")
            self.single_btn.setChecked(False)
            self.plot_manager.set_sampling_mode("Continuous")
        else:
            self.continuous_btn.setText("连续采样")
            self.plot_manager.set_sampling_mode("Stop")
            
    def on_single_clicked(self):
        if self.single_btn.isChecked():
            self.continuous_btn.setChecked(False)
            self.continuous_btn.setText("连续采样")
            self.plot_manager.set_sampling_mode("Single")
        else:
            self.plot_manager.set_sampling_mode("Stop")
            
    def on_single_complete(self):
        self.single_btn.setChecked(False)
        
MODERN_QSS = """
/* Global */
QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 14px;
}

/* Menu Bar */
QMenuBar {
    background-color: #252526;
    color: #cccccc;
    border-bottom: 1px solid #3e3e42;
}
QMenuBar::item:selected {
    background-color: #094771;
}
QMenu {
    background-color: #252526;
    color: #cccccc;
    border: 1px solid #3e3e42;
}
QMenu::item:selected {
    background-color: #094771;
}

/* GroupBox */
QGroupBox {
    background-color: #252526;
    border: 1px solid #3e3e42;
    border-radius: 8px;
    margin-top: 15px;
    padding-top: 20px;
    padding-left: 10px;
    padding-right: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #4daafc;
    font-weight: bold;
}

/* QPushButton */
QPushButton {
    background-color: #0e639c;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 12px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #1177bb;
}
QPushButton:pressed {
    background-color: #094771;
}
QPushButton:checked {
    background-color: #c72a2a;
    color: #ffffff;
    border: 2px solid #ff4d4d;
}

/* QComboBox */
QComboBox {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px;
    color: #ffffff;
    min-height: 25px;
}
QComboBox:drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #252526;
    color: #cccccc;
    selection-background-color: #094771;
}

/* QSpinBox */
QSpinBox, QDoubleSpinBox {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 5px;
    color: #ffffff;
    min-height: 25px;
}

/* QCheckBox */
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #555555;
    background-color: #3c3c3c;
}
QCheckBox::indicator:checked {
    background-color: #0e639c;
    border: 1px solid #4daafc;
}

/* QSplitter */
QSplitter::handle {
    background-color: #3e3e42;
    margin: 2px;
}

/* ToolTip */
QToolTip {
    color: #ffffff;
    background-color: #252526;
    border: 1px solid #4daafc;
    border-radius: 4px;
    padding: 4px;
}

/* QDialog */
QDialog {
    background-color: #1e1e1e;
}
"""

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    
    # Apply modern custom stylesheet
    app.setStyleSheet(MODERN_QSS)
    
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())
