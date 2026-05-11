from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox, 
    QComboBox, QPushButton, QLabel, QSpinBox, QCheckBox, QDoubleSpinBox, 
    QTabWidget, QGridLayout, QScrollArea, QToolButton, QSizePolicy
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction
import pyqtgraph as pg


class CollapsibleGroupBox(QWidget):
    """A GroupBox with a clickable header that can collapse/expand its content."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._is_collapsed = False
        
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        
        # Header button
        self._toggle_btn = QToolButton()
        self._toggle_btn.setStyleSheet("""
            QToolButton {
                font-weight: bold;
                color: #4daafc;
                font-size: 13px;
                border: none;
                padding: 6px 4px;
                text-align: left;
                background-color: transparent;
            }
            QToolButton:hover {
                background-color: #2a2d2e;
            }
        """)
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle_btn.setArrowType(Qt.DownArrow)
        self._toggle_btn.setText(title)
        self._toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._toggle_btn.clicked.connect(self.toggle_collapsed)
        self._layout.addWidget(self._toggle_btn)
        
        # Content container
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 8)
        self._content_layout.setSpacing(4)
        self._layout.addWidget(self._content)
    
    def content_layout(self):
        return self._content_layout
    
    def toggle_collapsed(self):
        self._is_collapsed = not self._is_collapsed
        self._content.setVisible(not self._is_collapsed)
        self._toggle_btn.setArrowType(Qt.RightArrow if self._is_collapsed else Qt.DownArrow)
    
    def set_collapsed(self, collapsed):
        self._is_collapsed = collapsed
        self._content.setVisible(not collapsed)
        self._toggle_btn.setArrowType(Qt.RightArrow if collapsed else Qt.DownArrow)
    
    def is_collapsed(self):
        return self._is_collapsed


class UILayout(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Encoder Signal Acquisition Oscilloscope")
        self.resize(1400, 900)
        
        # --- Menu Bar ---
        menubar = self.menuBar()
        
        self.view_menu = menubar.addMenu("视图 (View)")
        self.tools_menu = menubar.addMenu("工具 (Tools)")
        
        self.toggle_lissajous_action = QAction("李萨如图 (Lissajous)", self)
        self.toggle_lissajous_action.setCheckable(True)
        self.toggle_lissajous_action.setChecked(True)
        self.view_menu.addAction(self.toggle_lissajous_action)
        
        self.limits_action = QAction("测量范围设置 (Limits)...", self)
        self.tools_menu.addAction(self.limits_action)
        
        # --- Central Widget ---
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Left Panel - Plots (Time Domain + Lissajous in a vertical splitter)
        self.left_panel = QSplitter(Qt.Vertical)
        
        # Time Domain Plot
        self.time_plot_widget = pg.PlotWidget(title="Time Domain Oscilloscope")
        self.time_plot_widget.addLegend()
        self.time_plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.left_panel.addWidget(self.time_plot_widget)
        
        # 3 Lissajous Plots (inside left_panel splitter, same position as original)
        self.lissajous_container = QWidget()
        lissajous_layout = QHBoxLayout(self.lissajous_container)
        lissajous_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lissajous_plots = []
        titles = ["M Channel Lissajous", "N Channel Lissajous", "S Channel Lissajous"]
        for title in titles:
            plot = pg.PlotWidget(title=title)
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.setAspectLocked(True)
            lissajous_layout.addWidget(plot)
            self.lissajous_plots.append(plot)
            
        self.left_panel.addWidget(self.lissajous_container)
        self.left_panel.setSizes([600, 300])
        
        # Connect menu action to toggle Lissajous visibility
        self.toggle_lissajous_action.triggered.connect(self._toggle_lissajous)
        
        main_layout.addWidget(self.left_panel, stretch=4)
        
        # Right Panel - Controls (vertical only scroll)
        right_panel_widget = QWidget()
        right_panel_widget.setFixedWidth(350)
        right_panel = QVBoxLayout(right_panel_widget)
        right_panel.setSpacing(4)
        right_panel.setContentsMargins(4, 4, 4, 4)
        
        # Store collapsible groups for registry save/load
        self.collapsible_groups = {}
        
        # 1. Serial Port Configuration
        grp1 = CollapsibleGroupBox("1. 串口配置")
        g1 = grp1.content_layout()
        serial_layout = QGridLayout()
        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        self.baud_combo.setEditable(True)
        self.baud_combo.addItems(["2500000", "2000000", "1500000", "115200"])
        
        self.refresh_ports_btn = QPushButton("刷新端口")
        self.refresh_ports_btn.setMinimumHeight(35)
        self.connect_btn = QPushButton("连接端口")
        self.connect_btn.setMinimumHeight(35)
        
        serial_layout.addWidget(QLabel("端口(ID):"), 0, 0)
        serial_layout.addWidget(self.port_combo, 0, 1)
        serial_layout.addWidget(QLabel("波特率:"), 1, 0)
        serial_layout.addWidget(self.baud_combo, 1, 1)
        serial_layout.addWidget(self.refresh_ports_btn, 2, 0)
        serial_layout.addWidget(self.connect_btn, 2, 1)
        g1.addLayout(serial_layout)
        right_panel.addWidget(grp1)
        self.collapsible_groups["serial"] = grp1
        
        # 2. Acquisition Control
        grp2 = CollapsibleGroupBox("2. 采集通讯")
        g2 = grp2.content_layout()
        row1 = QHBoxLayout()
        self.encoder_type_combo = QComboBox()
        self.encoder_type_combo.addItems(["光编 (Optical)", "磁编 (Magnetic)"])
        row1.addWidget(QLabel("类型:"))
        row1.addWidget(self.encoder_type_combo)
        
        self.setup_btn = QPushButton("设置")
        self.setup_btn.setMinimumHeight(35)
        self.setup_btn.setCheckable(True)
        row1.addWidget(self.setup_btn)
        g2.addLayout(row1)
        right_panel.addWidget(grp2)
        self.collapsible_groups["acq"] = grp2
        
        # 3. Sampling Settings
        grp3 = CollapsibleGroupBox("3. 采样设置 (基准: 125μs)")
        g3 = grp3.content_layout()
        samp_layout = QHBoxLayout()
        
        self.downsample_spin = QSpinBox()
        self.downsample_spin.setRange(1, 1000)
        self.downsample_spin.setValue(1)
        
        self.points_spin = QSpinBox()
        self.points_spin.setRange(100, 50000)
        self.points_spin.setValue(2000)
        
        samp_layout.addWidget(QLabel("下采样:"))
        samp_layout.addWidget(self.downsample_spin)
        samp_layout.addWidget(QLabel("点数:"))
        samp_layout.addWidget(self.points_spin)
        g3.addLayout(samp_layout)
        right_panel.addWidget(grp3)
        self.collapsible_groups["sampling"] = grp3
        
        # 4. Trigger & Run Control
        grp4 = CollapsibleGroupBox("4. 触发与运行控制")
        g4 = grp4.content_layout()
        trig_layout = QGridLayout()
        
        self.trig_src_combo = QComboBox()
        self.trig_src_combo.setMinimumHeight(28)
        self.trig_src_combo.addItems(["无 (Free-run)", "M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS", "MTAB", "HALL"])
        
        self.trig_edge_combo = QComboBox()
        self.trig_edge_combo.addItems(["上升沿 (Rising)", "下降沿 (Falling)"])
        
        self.trig_level_spin = QSpinBox()
        self.trig_level_spin.setRange(0, 4095)
        self.trig_level_spin.setValue(2000)
        
        self.pre_trig_spin = QSpinBox()
        self.pre_trig_spin.setRange(0, 50000)
        self.pre_trig_spin.setValue(500)
        
        trig_layout.addWidget(QLabel("触发信源:"), 0, 0)
        trig_layout.addWidget(self.trig_src_combo, 0, 1)
        trig_layout.addWidget(QLabel("触发边沿:"), 0, 2)
        trig_layout.addWidget(self.trig_edge_combo, 0, 3)
        
        trig_layout.addWidget(QLabel("触发电平:"), 1, 0)
        trig_layout.addWidget(self.trig_level_spin, 1, 1)
        trig_layout.addWidget(QLabel("预触发数:"), 1, 2)
        trig_layout.addWidget(self.pre_trig_spin, 1, 3)
        
        btn_row = QHBoxLayout()
        self.continuous_btn = QPushButton("连续采样")
        self.continuous_btn.setMinimumHeight(40)
        self.continuous_btn.setCheckable(True)
        self.single_btn = QPushButton("单次采样")
        self.single_btn.setMinimumHeight(40)
        self.single_btn.setCheckable(True)
        
        btn_style = "QPushButton:checked { background-color: #A33; color: white; border-radius: 4px; }"
        self.setup_btn.setStyleSheet(btn_style)
        self.continuous_btn.setStyleSheet(btn_style)
        self.single_btn.setStyleSheet(btn_style)
        
        btn_row.addWidget(self.continuous_btn)
        btn_row.addWidget(self.single_btn)
        trig_layout.addLayout(btn_row, 2, 0, 1, 4)
        g4.addLayout(trig_layout)
        right_panel.addWidget(grp4)
        self.collapsible_groups["trigger"] = grp4
        
        # 5. Variable Selection
        grp5 = CollapsibleGroupBox("5. 记录变量 (时域显示)")
        g5 = grp5.content_layout()
        
        var_scroll_area = QScrollArea()
        var_scroll_area.setWidgetResizable(True)
        var_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        var_scroll_area.setStyleSheet("QScrollArea { border: none; }")

        var_scroll_area.setMinimumHeight(200)

        scroll_widget = QWidget()
        var_layout = QGridLayout(scroll_widget)
        
        self.var_checkboxes = []
        var_names = ["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS", "MTAB", "HALL"]
        for ch in ["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS"]:
            var_names.extend([f"{ch}_MAX", f"{ch}_MIN", f"{ch}_OFS"])
        
        for i, name in enumerate(var_names):
            cb = QCheckBox(name)
            if name in ["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS"]:
                cb.setChecked(True)
            self.var_checkboxes.append(cb)
            var_layout.addWidget(cb, i // 2, i % 2)
            
        var_scroll_area.setWidget(scroll_widget)
        g5.addWidget(var_scroll_area)
        right_panel.addWidget(grp5)
        self.collapsible_groups["vars"] = grp5
        
        # 6. Auto Measurements (M/N/S stats + phase diffs + digital)
        grp6 = CollapsibleGroupBox("6. 自动测量")
        g6 = grp6.content_layout()
        meas_layout = QGridLayout()
        meas_layout.setSpacing(3)
        meas_layout.setContentsMargins(0, 0, 0, 0)
        
        # Algorithm selector (top row)
        meas_layout.addWidget(QLabel("算法:"), 0, 0)
        self.meas_algo = QComboBox()
        self.meas_algo.addItems(["FFT (频域法)", "Zero-Crossing (过零点)"])
        meas_layout.addWidget(self.meas_algo, 0, 1, 1, 3)
        
        # Column headers
        header_style = "font-weight: bold; color: #4daafc; font-size: 11px;"
        for col, txt in enumerate(["", "Max", "Min", "Offset"], 0):
            lbl = QLabel(txt)
            lbl.setStyleSheet(header_style)
            lbl.setAlignment(Qt.AlignCenter)
            meas_layout.addWidget(lbl, 1, col)
        
        # Create labels for each channel's stats
        self.meas_labels = {}
        channels = ["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS"]
        meas_lbl_style = "font-size: 11px; font-weight: bold; color: #55FF55;"
        
        for row_idx, ch in enumerate(channels):
            ch_lbl = QLabel(ch)
            ch_lbl.setStyleSheet("font-weight: bold; color: #cccccc; font-size: 11px;")
            meas_layout.addWidget(ch_lbl, 2 + row_idx, 0)
            
            for col_idx, metric in enumerate(["MAX", "MIN", "OFS"], 1):
                key = f"{ch}_{metric}"
                lbl = QLabel("--")
                lbl.setStyleSheet(meas_lbl_style)
                lbl.setAlignment(Qt.AlignCenter)
                self.meas_labels[key] = lbl
                meas_layout.addWidget(lbl, 2 + row_idx, col_idx)
        
        # Phase Difference section
        phase_header = QLabel("相位差 (SIN vs COS)")
        phase_header.setStyleSheet(header_style)
        phase_header.setAlignment(Qt.AlignCenter)
        meas_layout.addWidget(phase_header, 8, 0, 1, 4)
        
        self.phase_labels = {}
        for row_idx, ch_name in enumerate(["M", "N", "S"]):
            ch_lbl = QLabel(f"{ch_name} 码道:")
            ch_lbl.setStyleSheet("font-weight: bold; color: #cccccc; font-size: 11px;")
            meas_layout.addWidget(ch_lbl, 9 + row_idx, 0, 1, 2)
            
            lbl = QLabel("-- °")
            lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #55FF55;")
            lbl.setAlignment(Qt.AlignCenter)
            self.phase_labels[ch_name] = lbl
            meas_layout.addWidget(lbl, 9 + row_idx, 2, 1, 2)
        
        # MTAB Section
        mtab_header = QLabel("MTAB (MTA/MTB)")
        mtab_header.setStyleSheet(header_style)
        mtab_header.setAlignment(Qt.AlignCenter)
        meas_layout.addWidget(mtab_header, 12, 0, 1, 4)
        
        self.digital_labels = {}
        row_base = 13
        for lbl_text, key in [("MTA占空比:", "MTA_DUTY"), ("MTB占空比:", "MTB_DUTY"),
                               ("MTA/MTB相位差:", "MTAB_PHASE"),
                               ("突变次数:", "MTAB_GLITCH"),
                               ("突变详情:", "MTAB_GLITCH_DETAIL")]:
            ch_lbl = QLabel(lbl_text)
            ch_lbl.setStyleSheet("font-weight: bold; color: #cccccc; font-size: 11px;")
            meas_layout.addWidget(ch_lbl, row_base, 0, 1, 2)
            
            if "DUTY" in key:
                unit_txt = "-- %"
            elif "PHASE" in key:
                unit_txt = "-- °"
            elif "DETAIL" in key:
                unit_txt = "0:- 1:- 2:- 3:-"
            else:
                unit_txt = "--"
            lbl = QLabel(unit_txt)
            lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #55FF55;")
            lbl.setAlignment(Qt.AlignCenter)
            self.digital_labels[key] = lbl
            meas_layout.addWidget(lbl, row_base, 2, 1, 2)
            row_base += 1
        
        # HALL Section
        hall_header = QLabel("HALL (H1/H2)")
        hall_header.setStyleSheet(header_style)
        hall_header.setAlignment(Qt.AlignCenter)
        meas_layout.addWidget(hall_header, row_base, 0, 1, 4)
        row_base += 1
        
        for lbl_text, key in [("HALL1占空比:", "HALL1_DUTY"), ("HALL2占空比:", "HALL2_DUTY"),
                               ("H1/H2相位差:", "HALL_PHASE"),
                               ("突变次数:", "HALL_GLITCH"),
                               ("突变详情:", "HALL_GLITCH_DETAIL")]:
            ch_lbl = QLabel(lbl_text)
            ch_lbl.setStyleSheet("font-weight: bold; color: #cccccc; font-size: 11px;")
            meas_layout.addWidget(ch_lbl, row_base, 0, 1, 2)
            
            if "DUTY" in key:
                unit_txt = "-- %"
            elif "PHASE" in key:
                unit_txt = "-- °"
            elif "DETAIL" in key:
                unit_txt = "0:- 1:- 2:- 3:-"
            else:
                unit_txt = "--"
            lbl = QLabel(unit_txt)
            lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #55FF55;")
            lbl.setAlignment(Qt.AlignCenter)
            self.digital_labels[key] = lbl
            meas_layout.addWidget(lbl, row_base, 2, 1, 2)
            row_base += 1
        
        g6.addLayout(meas_layout)
        right_panel.addWidget(grp6)
        self.collapsible_groups["meas"] = grp6
        
        right_panel.addStretch(1)
        
        # Wrap entire right panel in a scroll area (vertical only, NO horizontal)
        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setWidget(right_panel_widget)
        main_scroll.setFixedWidth(368)
        main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_scroll.setStyleSheet("QScrollArea { border: none; }")
        
        main_layout.addWidget(main_scroll, stretch=0)
    
    def _toggle_lissajous(self, checked):
        self.lissajous_container.setVisible(checked)
        if checked:
            self.left_panel.setSizes([600, 300])
