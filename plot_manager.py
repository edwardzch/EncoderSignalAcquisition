import pyqtgraph as pg
from PySide6.QtCore import QObject
import numpy as np

class PlotManager(QObject):
    def __init__(self, time_plot: pg.PlotItem, lissajous_plots: list[pg.PlotItem]):
        super().__init__()
        self.time_plot = time_plot
        self.lissajous_plots = lissajous_plots
        
        self.time_plot.showGrid(x=True, y=True)
        self.time_plot.setLabel('bottom', "Time", units='ms')
        self.time_plot.disableAutoRange()
        self.time_plot.setYRange(-500, 4500)
        
        from PySide6.QtCore import QTimer
        self.render_timer = QTimer()
        self.render_timer.timeout.connect(self.update_plots)
        self.render_timer.start(50) # 20 FPS rendering
        
        for p in self.lissajous_plots:
            p.showGrid(x=True, y=True)
            p.setAspectLocked(True)
        
        self.buffer_size = 10000 # Max base samples
        self.data_buffer = np.zeros((self.buffer_size, 26))
        
        self.base_interval_ms = 0.125 # Changed to 0.125ms for 8kHz sampling rate
        self.downsample_factor = 1
        self.display_length = 2000 # points to show
        
        # Variable configurations
        self.var_names = ["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS", "MTAB", "HALL"]
        base_colors = [(255, 50, 50), (50, 255, 50), (50, 150, 255), (255, 255, 50), (255, 50, 255), (50, 255, 255), (255, 150, 50), (255, 255, 255)]
        self.colors = list(base_colors)
        
        for i, ch in enumerate(["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS"]):
            self.var_names.extend([f"{ch}_MAX", f"{ch}_MIN", f"{ch}_OFS"])
            r, g, b = base_colors[i]
            max_c = (min(255, r + 100), min(255, g + 100), min(255, b + 100))
            min_c = (max(0, r - 100), max(0, g - 100), max(0, b - 100))
            ofs_c = (min(255, r + 50), min(255, g + 50), min(255, b + 50))
            self.colors.extend([max_c, min_c, ofs_c])
        
        from PySide6.QtCore import Qt
        
        self.time_curves = []
        for i in range(26):
            if i < 8:
                pen = pg.mkPen(color=self.colors[i], width=1.5)
            else:
                idx = (i - 8) % 3
                if idx == 0: # MAX
                    pen = pg.mkPen(color=self.colors[i], width=1.0, style=Qt.SolidLine)
                elif idx == 1: # MIN
                    pen = pg.mkPen(color=self.colors[i], width=1.0, style=Qt.SolidLine)
                else: # OFS
                    pen = pg.mkPen(color=self.colors[i], width=1.5, style=Qt.SolidLine)
            
            curve = self.time_plot.plot(pen=pen, name=self.var_names[i])
            self.time_curves.append(curve)
            
        self.lissajous_curves = []
        # M (0,1), N (2,3), S (4,5)
        self.lissajous_configs = [(1, 0), (3, 2), (5, 4)] # (X, Y)
        for i, p in enumerate(self.lissajous_plots):
            curve = p.plot(pen=None, symbol='o', symbolSize=2, symbolPen=None, symbolBrush=(0, 255, 0, 150))
            self.lissajous_curves.append(curve)
        
        self.active_vars = [False] * 26
        
        self.meas_algo = 0 # 0: FFT, 1: Zero-Crossing
        # Results for all 3 channels: M, N, S phase diffs
        self.phase_diffs = {"M": None, "N": None, "S": None}
        # Results for all 6 channels: Max, Min, Ofs
        self.channel_stats = {}  # key: "M_SIN_MAX" etc, value: float or None
        # MTAB/HALL digital measurements
        self.digital_stats = {}  # key: "MTA_DUTY", "MTB_DUTY", "MTAB_PHASE", etc.
        
        self.sampling_mode = "Stop" # Continuous, Single, Stop
        self.trigger_source = -1 # -1 means None
        self.trigger_level = 2000
        self.trigger_edge = "Rising"
        self.pre_trigger = 500
        
        self.single_triggered = False
        self.new_samples_since_single = 0
        
        # Crosshair and tooltip
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.time_plot.addItem(self.vLine, ignoreBounds=True)
        self.time_plot.addItem(self.hLine, ignoreBounds=True)
        
        self.tooltip = pg.TextItem(text="", color=(255, 255, 255), fill=(0, 0, 0, 150))
        self.time_plot.addItem(self.tooltip)
        
        self.vLine.hide()
        self.hLine.hide()
        self.tooltip.hide()
        
        self.proxy = pg.SignalProxy(self.time_plot.scene().sigMouseMoved, rateLimit=60, slot=self.mouseMoved)
        
        self.last_plotted_ds_data = None
        self.last_plotted_time_axis = None
        
    def set_active_vars(self, states):
        self.active_vars = states
        for i, state in enumerate(states):
            if state:
                self.time_curves[i].setVisible(True)
            else:
                self.time_curves[i].setData([], [])
                self.time_curves[i].setVisible(False)
                
    def set_display_params(self, points, downsample):
        self.display_length = points
        self.downsample_factor = max(1, downsample)
        
        required_buffer = self.display_length * self.downsample_factor * 2
        if required_buffer > self.buffer_size:
            # Increase buffer size if needed
            self.buffer_size = required_buffer
            new_buf = np.zeros((self.buffer_size, 26))
            old_len = min(self.data_buffer.shape[0], self.buffer_size)
            new_buf[-old_len:] = self.data_buffer[-old_len:]
            self.data_buffer = new_buf
            
        # Update X-axis range based on display parameters
        max_time = self.display_length * self.downsample_factor * self.base_interval_ms
        self.time_plot.setXRange(0, max_time, padding=0)
            
    def set_sampling_mode(self, mode):
        self.sampling_mode = mode
        if mode == "Single":
            self.single_triggered = False
            self.points_since_single_start = 0
            self.new_samples_since_single = 0
            # Visually clear plots while waiting
            for i in range(26):
                self.time_curves[i].setData([], [])
            for curve in self.lissajous_curves:
                curve.setData([], [])
            
    def add_data(self, new_data):
        if self.sampling_mode == "Stop" or (self.sampling_mode == "Single" and self.single_triggered):
            return
            
        n = new_data.shape[0]
        if self.sampling_mode == "Single":
            self.new_samples_since_single += n
            
        if n >= self.buffer_size:
            self.data_buffer = new_data[-self.buffer_size:].copy()
        else:
            self.data_buffer = np.roll(self.data_buffer, -n, axis=0)
            self.data_buffer[-n:] = new_data
            
    def calculate_phase_diff(self, sig1, sig2, algo):
        # Prevent completely flat signals from causing errors
        if np.ptp(sig1) < 1e-3 or np.ptp(sig2) < 1e-3:
            return None
            
        s1 = sig1 - np.mean(sig1)
        s2 = sig2 - np.mean(sig2)
        
        if algo == 0: # FFT
            f1 = np.fft.rfft(s1)
            f2 = np.fft.rfft(s2)
            
            f1[0] = 0
            f2[0] = 0
            
            idx = np.argmax(np.abs(f1))
            if idx == 0 or np.abs(f1[idx]) < 1e-6:
                return None
                
            phase1 = np.angle(f1[idx], deg=True)
            phase2 = np.angle(f2[idx], deg=True)
            
            diff = phase1 - phase2
            diff = (diff + 180) % 360 - 180
            return diff
            
        else: # Zero-Crossing
            zc1 = np.where((s1[:-1] < 0) & (s1[1:] >= 0))[0]
            zc2 = np.where((s2[:-1] < 0) & (s2[1:] >= 0))[0]
            
            if len(zc1) < 2 or len(zc2) < 1:
                return None
                
            periods = np.diff(zc1)
            avg_period = np.mean(periods)
            
            if avg_period == 0:
                return None
                
            phase_diffs = []
            for z1 in zc1:
                idx = np.argmin(np.abs(zc2 - z1))
                z2 = zc2[idx]
                
                diff = z1 - z2 # Phase of 1 relative to 2
                if diff > avg_period / 2:
                    diff -= avg_period
                elif diff < -avg_period / 2:
                    diff += avg_period
                    
                phase = (diff / avg_period) * 360.0
                phase_diffs.append(phase)
                
            if len(phase_diffs) == 0:
                return None
            return np.mean(phase_diffs)
    
    def compute_digital_stats(self, ds_data):
        """Compute duty cycle and phase for MTAB (col6) and HALL (col7).
        
        MTAB encoding (cycle: 0→1→3→2):
          MTA = (value & 2) >> 1  →  high when MTAB is 2 or 3
          MTB = (value & 1)       →  high when MTAB is 1 or 3
          
        HALL encoding (cycle: 0→3→2→1):
          HALL1 = (value & 2) >> 1  →  high when HALL is 2 or 3
          HALL2 = (value & 1)       →  high when HALL is 1 or 3
        """
        n = ds_data.shape[0]
        if n < 10:
            return
            
        # --- MTAB ---
        mtab = ds_data[:, 6].astype(int)
        mta = (mtab & 2) >> 1  # MTA signal (0 or 1)
        mtb = (mtab & 1)       # MTB signal (0 or 1)
        
        self.digital_stats["MTA_DUTY"] = float(np.sum(mta)) / n * 100.0
        self.digital_stats["MTB_DUTY"] = float(np.sum(mtb)) / n * 100.0
        self.digital_stats["MTAB_PHASE"] = self._compute_square_phase(mta, mtb)

        # MTAB glitch detection (Sequence: 0->1->3->2)
        mtab_total, mtab_detail = self._detect_glitches(
            mtab, valid_fwd=[1, 3, 0, 2], valid_rev=[2, 0, 3, 1])
        self.digital_stats["MTAB_GLITCH"] = mtab_total
        self.digital_stats["MTAB_GLITCH_DETAIL"] = mtab_detail  # {state: count}
        
        # --- HALL ---
        # HALL encoding is different from MTAB!
        # Forward: 0→3→2→1,  Reverse: 0→1→2→3
        # bit0 alone toggles every state (double frequency), so we decode:
        #   HALL1 = bit1                     → high when val is 2 or 3
        #   HALL2 = bit0 XOR bit1            → high when val is 1 or 2
        # This produces two proper 50% duty square waves in quadrature.
        hall = ds_data[:, 7].astype(int)
        hall1 = (hall & 2) >> 1                         # HALL1 signal
        hall2 = (hall & 1) ^ ((hall >> 1) & 1)          # HALL2 = bit0 XOR bit1
        
        self.digital_stats["HALL1_DUTY"] = float(np.sum(hall1)) / n * 100.0
        self.digital_stats["HALL2_DUTY"] = float(np.sum(hall2)) / n * 100.0
        self.digital_stats["HALL_PHASE"] = self._compute_square_phase(hall1, hall2)
        
        # HALL glitch detection (valid transitions for quadrature 0→3→2→1)
        hall_total, hall_detail = self._detect_glitches(
            hall, valid_fwd=[3, 0, 1, 2], valid_rev=[1, 2, 3, 0])
        self.digital_stats["HALL_GLITCH"] = hall_total
        self.digital_stats["HALL_GLITCH_DETAIL"] = hall_detail
    
    def _detect_glitches(self, signal, valid_fwd, valid_rev):
        """Detect illegal state transitions in a quadrature signal.
        
        Returns:
            (total_count, detail_dict) where detail_dict maps
            each from_state to the number of glitches originating from it.
        """
        if len(signal) < 2:
            return 0, {0: 0, 1: 0, 2: 0, 3: 0}
        
        prev = signal[:-1]
        curr = signal[1:]
        
        # A transition is valid if: same state, or forward step, or reverse step
        is_same = (prev == curr)
        is_fwd = np.zeros(len(prev), dtype=bool)
        is_rev = np.zeros(len(prev), dtype=bool)
        
        for state in range(4):
            mask = (prev == state)
            is_fwd |= mask & (curr == valid_fwd[state])
            is_rev |= mask & (curr == valid_rev[state])
        
        is_valid = is_same | is_fwd | is_rev
        is_glitch = ~is_valid
        glitch_count = int(np.sum(is_glitch))
        
        # Per-state breakdown: which state was the signal in when the glitch occurred
        detail = {}
        for state in range(4):
            detail[state] = int(np.sum(is_glitch & (prev == state)))
        
        return glitch_count, detail
    
    def _compute_square_phase(self, sig_a, sig_b):
        """Compute phase difference between two square wave signals.
        
        Finds rising edges of both signals, measures the average time delay
        relative to the period, and converts to degrees.
        """
        # Find rising edges: transition from 0 to 1
        edges_a = np.where((sig_a[:-1] == 0) & (sig_a[1:] == 1))[0]
        edges_b = np.where((sig_b[:-1] == 0) & (sig_b[1:] == 1))[0]
        
        if len(edges_a) < 2 or len(edges_b) < 1:
            return None
            
        # Period from signal A
        periods = np.diff(edges_a)
        avg_period = np.mean(periods)
        
        if avg_period == 0:
            return None
        
        # For each rising edge of A, find nearest rising edge of B
        phase_diffs = []
        for ea in edges_a:
            idx = np.argmin(np.abs(edges_b - ea))
            eb = edges_b[idx]
            
            diff = float(ea - eb)
            if diff > avg_period / 2:
                diff -= avg_period
            elif diff < -avg_period / 2:
                diff += avg_period
            
            phase = (diff / avg_period) * 360.0
            phase_diffs.append(phase)
        
        if len(phase_diffs) == 0:
            return None
        return float(np.mean(phase_diffs))
        
    def update_plots(self):
        if self.sampling_mode == "Stop":
            return
            
        # We need to extract self.display_length * self.downsample_factor points from buffer
        points_needed = self.display_length * self.downsample_factor
        
        if self.sampling_mode == "Single" and self.new_samples_since_single < points_needed:
            return # Wait until we have enough new points
            
        pre_trigger_raw = self.pre_trigger * self.downsample_factor
        
        display_start = self.buffer_size - points_needed
        if display_start < 0:
            display_start = 0
            
        found = False
        
        if self.trigger_source >= 0:
            # Search for trigger in the newest half of the required buffer
            src_data = self.data_buffer[:, self.trigger_source]
            
            # Start searching from the end, going backwards
            search_end = self.buffer_size - points_needed + pre_trigger_raw
            if search_end > self.buffer_size - 1:
                search_end = self.buffer_size - 1
                
            search_start = 1
            if self.sampling_mode == "Single":
                search_start = self.buffer_size - self.new_samples_since_single + pre_trigger_raw
                if search_start < 1:
                    search_start = 1
                    
            if search_start <= search_end:
                for i in range(search_end, search_start - 1, -1):
                    if self.trigger_edge == "Rising":
                        if src_data[i-1] < self.trigger_level and src_data[i] >= self.trigger_level:
                            display_start = i - pre_trigger_raw
                            found = True
                            break
                    else:
                        if src_data[i-1] > self.trigger_level and src_data[i] <= self.trigger_level:
                            display_start = i - pre_trigger_raw
                            found = True
                            break
            
            if display_start < 0:
                display_start = 0
                
            if not found:
                # If single mode and no trigger, wait
                if self.sampling_mode == "Single":
                    return
                # If continuous and no trigger, fallback to blind capture
                display_start = self.buffer_size - points_needed
        else:
            # No trigger source (None)
            found = True
            display_start = self.buffer_size - points_needed
            
        if self.sampling_mode == "Single" and found:
            self.single_triggered = True
            self.sampling_mode = "Stop"
            if hasattr(self, 'on_single_complete') and self.on_single_complete:
                self.on_single_complete()
            
        # Extract data and apply downsample
        raw_slice = self.data_buffer[display_start:display_start+points_needed]
        ds_data = raw_slice[::self.downsample_factor]
        
        # Calculate time axis
        time_axis = np.arange(ds_data.shape[0]) * (self.base_interval_ms * self.downsample_factor)
        
        # Update time plots
        for i in range(len(self.active_vars)):
            if self.active_vars[i]:
                self.time_curves[i].setData(time_axis, ds_data[:, i])
                
        # Update 3 lissajous plots
        for idx, (x_ch, y_ch) in enumerate(self.lissajous_configs):
            self.lissajous_curves[idx].setData(ds_data[:, x_ch], ds_data[:, y_ch])
            
        # Calculate Phase Differences for M, N, S channels
        # M: SIN=col0, COS=col1; N: SIN=col2, COS=col3; S: SIN=col4, COS=col5
        ch_pairs = [("M", 0, 1), ("N", 2, 3), ("S", 4, 5)]
        for ch_name, sin_idx, cos_idx in ch_pairs:
            self.phase_diffs[ch_name] = self.calculate_phase_diff(
                ds_data[:, sin_idx], ds_data[:, cos_idx], self.meas_algo)
        
        # Extract Max, Min, Offset for all 6 channels from block calculations
        if ds_data.shape[1] >= 26:
            channels = ["M_SIN", "M_COS", "N_SIN", "N_COS", "S_SIN", "S_COS"]
            for ch_idx, ch_name in enumerate(channels):
                base = 8 + ch_idx * 3
                self.channel_stats[f"{ch_name}_MAX"] = float(ds_data[-1, base])
                self.channel_stats[f"{ch_name}_MIN"] = float(ds_data[-1, base + 1])
                self.channel_stats[f"{ch_name}_OFS"] = float(ds_data[-1, base + 2])
        
        # Compute MTAB/HALL digital measurements (use RAW data, not downsampled!)
        self.compute_digital_stats(raw_slice)
            
        self.last_plotted_ds_data = ds_data
        self.last_plotted_time_axis = time_axis
        self.last_tooltip_idx = -1
        
    def mouseMoved(self, evt):
        if self.sampling_mode == "Continuous":
            self.vLine.hide()
            self.hLine.hide()
            self.tooltip.hide()
            return
            
        # If Single is still running (not triggered), hide
        if self.sampling_mode == "Single" and not self.single_triggered:
            self.vLine.hide()
            self.hLine.hide()
            self.tooltip.hide()
            return
            
        pos = evt[0]
        if self.time_plot.getPlotItem().vb.sceneBoundingRect().contains(pos):
            mousePoint = self.time_plot.getPlotItem().vb.mapSceneToView(pos)
            x_val = mousePoint.x()
            y_val = mousePoint.y()
            
            if self.last_plotted_time_axis is not None and len(self.last_plotted_time_axis) > 0:
                # Find closest index
                idx = (np.abs(self.last_plotted_time_axis - x_val)).argmin()
                if 0 <= idx < len(self.last_plotted_time_axis):
                    actual_x = self.last_plotted_time_axis[idx]
                    
                    self.vLine.setPos(actual_x)
                    self.hLine.setPos(y_val)
                    self.vLine.show()
                    self.hLine.show()
                    
                    if not hasattr(self, 'last_tooltip_idx') or self.last_tooltip_idx != idx:
                        self.last_tooltip_idx = idx
                        text = f"t = {actual_x:.3f} ms\n"
                        for i in range(len(self.active_vars)):
                            if self.active_vars[i]:
                                val = self.last_plotted_ds_data[idx, i]
                                text += f"{self.var_names[i]}: {val:.1f}\n"
                        self.tooltip.setText(text.strip())
                    
                    # Anchor offset so mouse doesn't cover text
                    view_range = self.time_plot.getPlotItem().viewRange()
                    y_range = view_range[1][1] - view_range[1][0]
                    self.tooltip.setPos(actual_x, y_val + y_range * 0.05)
                    self.tooltip.show()
        else:
            self.vLine.hide()
            self.hLine.hide()
            self.tooltip.hide()
