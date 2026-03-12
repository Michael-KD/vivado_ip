#!/usr/bin/env python3
"""
zynq_client.py - PyQt6 GUI for controlling Zynq AXI peripherals

Connects to zynq_server running on the Zynq board and provides a unified
interface for controlling ADC (LTC2203), DAC (LTC1666), and SPGD peripherals.

Usage: python zynq_client.py [host] [port]
       Default: localhost:5000
"""

import sys
import socket
import json
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox,
    QComboBox, QProgressBar, QGroupBox, QStatusBar, QLineEdit, QMessageBox,
    QSlider, QFrame
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QPalette, QColor


# =============================================================================
# Network Client
# =============================================================================

class ZynqClient:
    """TCP/JSON client for communicating with zynq_server."""
    
    def __init__(self, host: str = "localhost", port: int = 5000):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Establish connection to server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2.0)
            self.sock.connect((self.host, self.port))
            self.connected = True
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Close connection."""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self.sock = None
        self.connected = False
    
    def send_command(self, cmd: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send JSON command and receive response."""
        if not self.connected or not self.sock:
            return None
        
        try:
            # Send command with newline
            msg = json.dumps(cmd) + "\n"
            self.sock.sendall(msg.encode())
            
            # Receive response (newline-delimited)
            data = b""
            while b"\n" not in data:
                chunk = self.sock.recv(4096)
                if not chunk:
                    self.connected = False
                    return None
                data += chunk
            
            response = json.loads(data.decode().strip())
            return response
        except Exception as e:
            print(f"Command failed: {e}")
            self.connected = False
            return None
    
    def get_all(self) -> Optional[Dict[str, Any]]:
        """Fetch all register values."""
        return self.send_command({"cmd": "get_all"})
    
    def write_reg(self, device: str, reg: int, value: int) -> bool:
        """Write to a device register."""
        resp = self.send_command({
            "cmd": "write",
            "device": device,
            "reg": reg,
            "value": value
        })
        return resp is not None and resp.get("status") == "ok"
    
    def pulse_bit(self, device: str, bit: int) -> bool:
        """Pulse a control bit."""
        resp = self.send_command({
            "cmd": "pulse",
            "device": device,
            "bit": bit
        })
        return resp is not None and resp.get("status") == "ok"


# =============================================================================
# ADC Tab (LTC2203)
# =============================================================================

class ADCTab(QWidget):
    """Control panel for LTC2203 ADC."""
    
    def __init__(self, client: ZynqClient):
        super().__init__()
        self.client = client
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- ADC Reading Group ---
        reading_group = QGroupBox("ADC Reading")
        reading_layout = QGridLayout(reading_group)
        
        self.adc_value_label = QLabel("0")
        self.adc_value_label.setFont(QFont("Courier", 24, QFont.Weight.Bold))
        self.adc_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reading_layout.addWidget(QLabel("Raw Value (signed):"), 0, 0)
        reading_layout.addWidget(self.adc_value_label, 0, 1)
        
        self.voltage_label = QLabel("0.000 V")
        self.voltage_label.setFont(QFont("Courier", 24, QFont.Weight.Bold))
        self.voltage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reading_layout.addWidget(QLabel("Voltage:"), 1, 0)
        reading_layout.addWidget(self.voltage_label, 1, 1)
        
        self.overflow_label = QLabel("NO")
        self.overflow_label.setFont(QFont("Courier", 16))
        reading_layout.addWidget(QLabel("Overflow:"), 2, 0)
        reading_layout.addWidget(self.overflow_label, 2, 1)
        
        # Bar graph
        self.adc_bar = QProgressBar()
        self.adc_bar.setMinimum(0)
        self.adc_bar.setMaximum(65535)
        self.adc_bar.setValue(32768)
        self.adc_bar.setTextVisible(False)
        self.adc_bar.setFixedHeight(30)
        reading_layout.addWidget(QLabel("-10V"), 3, 0)
        reading_layout.addWidget(self.adc_bar, 3, 1)
        reading_layout.addWidget(QLabel("+10V"), 3, 2)
        
        layout.addWidget(reading_group)
        
        # --- Control Group ---
        control_group = QGroupBox("Hardware Control")
        control_layout = QGridLayout(control_group)
        
        self.output_enable_cb = QCheckBox("Output Enable")
        self.output_enable_cb.stateChanged.connect(self.on_output_enable)
        control_layout.addWidget(self.output_enable_cb, 0, 0)
        
        control_layout.addWidget(QLabel("Clock Source:"), 1, 0)
        self.clock_source_combo = QComboBox()
        self.clock_source_combo.addItems(["External (SMA)", "Internal"])
        self.clock_source_combo.currentIndexChanged.connect(self.on_clock_source)
        control_layout.addWidget(self.clock_source_combo, 1, 1)
        
        control_layout.addWidget(QLabel("Prescaler:"), 2, 0)
        self.prescaler_spin = QSpinBox()
        self.prescaler_spin.setRange(0, 65535)
        self.prescaler_spin.valueChanged.connect(self.on_prescaler)
        control_layout.addWidget(self.prescaler_spin, 2, 1)
        
        self.freq_label = QLabel("-- MHz")
        control_layout.addWidget(QLabel("Sample Rate:"), 3, 0)
        control_layout.addWidget(self.freq_label, 3, 1)
        
        layout.addWidget(control_group)
        layout.addStretch()
    
    def on_output_enable(self, state):
        if self.client.connected:
            ctrl = 0
            resp = self.client.get_all()
            if resp and resp.get("status") == "ok":
                ctrl = resp["adc"]["ctrl"]
            if state:
                ctrl |= 0x01
            else:
                ctrl &= ~0x01
            self.client.write_reg("adc", 1, ctrl)
    
    def on_clock_source(self, index):
        if self.client.connected:
            ctrl = 0
            resp = self.client.get_all()
            if resp and resp.get("status") == "ok":
                ctrl = resp["adc"]["ctrl"]
            if index == 1:  # Internal
                ctrl |= 0x02
            else:  # External
                ctrl &= ~0x02
            self.client.write_reg("adc", 1, ctrl)
    
    def on_prescaler(self, value):
        if self.client.connected:
            self.client.write_reg("adc", 2, value)
    
    def update_from_data(self, adc_data: Dict):
        """Update UI from polled data."""
        raw_data = int(adc_data.get("data", 0))
        ctrl = int(adc_data.get("ctrl", 0))
        pre = int(adc_data.get("pre", 0))
        
        # Convert to signed 16-bit
        adc_val = raw_data & 0xFFFF
        if adc_val >= 0x8000:
            adc_val -= 0x10000
        
        overflow = (raw_data >> 16) & 0x01
        
        # Update value displays
        self.adc_value_label.setText(f"{adc_val:+6d}")
        
        # Voltage: ±10V full scale
        voltage = (adc_val / 32768.0) * 10.0
        self.voltage_label.setText(f"{voltage:+7.3f} V")
        
        # Overflow
        if overflow:
            self.overflow_label.setText("YES!")
            self.overflow_label.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.overflow_label.setText("NO")
            self.overflow_label.setStyleSheet("")
        
        # Bar graph (shift signed to unsigned for display)
        bar_val = adc_val + 32768
        self.adc_bar.setValue(bar_val)
        
        # Control states (block signals to prevent feedback loops)
        self.output_enable_cb.blockSignals(True)
        self.output_enable_cb.setChecked(bool(ctrl & 0x01))
        self.output_enable_cb.blockSignals(False)
        
        self.clock_source_combo.blockSignals(True)
        self.clock_source_combo.setCurrentIndex(1 if (ctrl & 0x02) else 0)
        self.clock_source_combo.blockSignals(False)
        
        self.prescaler_spin.blockSignals(True)
        self.prescaler_spin.setValue(pre)
        self.prescaler_spin.blockSignals(False)
        
        # Frequency calculation
        freq_mhz = 100.0 / (2.0 * (pre + 1))
        self.freq_label.setText(f"{freq_mhz:.2f} MHz")


# =============================================================================
# DAC Tab (LTC1666)
# =============================================================================

class DACTab(QWidget):
    """Control panel for LTC1666 DAC."""
    
    def __init__(self, client: ZynqClient):
        super().__init__()
        self.client = client
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Output Value Group ---
        output_group = QGroupBox("DAC Output")
        output_layout = QGridLayout(output_group)
        
        output_layout.addWidget(QLabel("Value (0-4095):"), 0, 0)
        self.value_spin = QSpinBox()
        self.value_spin.setRange(0, 4095)
        self.value_spin.valueChanged.connect(self.on_value_change)
        output_layout.addWidget(self.value_spin, 0, 1)
        
        self.value_slider = QSlider(Qt.Orientation.Horizontal)
        self.value_slider.setRange(0, 4095)
        self.value_slider.valueChanged.connect(self.on_slider_change)
        output_layout.addWidget(self.value_slider, 1, 0, 1, 3)
        
        self.voltage_label = QLabel("0.000 V")
        self.voltage_label.setFont(QFont("Courier", 18, QFont.Weight.Bold))
        output_layout.addWidget(QLabel("Est. Voltage:"), 2, 0)
        output_layout.addWidget(self.voltage_label, 2, 1)
        
        # Bar graph
        self.dac_bar = QProgressBar()
        self.dac_bar.setMinimum(0)
        self.dac_bar.setMaximum(4095)
        self.dac_bar.setTextVisible(False)
        self.dac_bar.setFixedHeight(25)
        output_layout.addWidget(QLabel("0V"), 3, 0)
        output_layout.addWidget(self.dac_bar, 3, 1)
        output_layout.addWidget(QLabel("4V"), 3, 2)
        
        layout.addWidget(output_group)
        
        # --- Control Group ---
        control_group = QGroupBox("Control")
        control_layout = QGridLayout(control_group)
        
        control_layout.addWidget(QLabel("Mode:"), 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Passthrough", "Manual (Register)"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_change)
        control_layout.addWidget(self.mode_combo, 0, 1)
        
        self.en0_cb = QCheckBox("DAC 0 Clock Enable")
        self.en0_cb.stateChanged.connect(self.on_enable_change)
        control_layout.addWidget(self.en0_cb, 1, 0, 1, 2)
        
        self.en1_cb = QCheckBox("DAC 1 Clock Enable")
        self.en1_cb.stateChanged.connect(self.on_enable_change)
        control_layout.addWidget(self.en1_cb, 2, 0, 1, 2)
        
        layout.addWidget(control_group)
        
        # --- Timing Group ---
        timing_group = QGroupBox("Timing")
        timing_layout = QGridLayout(timing_group)
        
        timing_layout.addWidget(QLabel("Prescaler:"), 0, 0)
        self.prescaler_spin = QSpinBox()
        self.prescaler_spin.setRange(0, 65535)
        self.prescaler_spin.valueChanged.connect(self.on_prescaler)
        timing_layout.addWidget(self.prescaler_spin, 0, 1)
        
        self.freq_label = QLabel("-- MHz")
        timing_layout.addWidget(QLabel("Clock Freq:"), 1, 0)
        timing_layout.addWidget(self.freq_label, 1, 1)
        
        layout.addWidget(timing_group)
        layout.addStretch()
    
    def on_value_change(self, value):
        if self.client.connected:
            self.value_slider.blockSignals(True)
            self.value_slider.setValue(value)
            self.value_slider.blockSignals(False)
            self.client.write_reg("dac", 0, value)
    
    def on_slider_change(self, value):
        self.value_spin.blockSignals(True)
        self.value_spin.setValue(value)
        self.value_spin.blockSignals(False)
        if self.client.connected:
            self.client.write_reg("dac", 0, value)
    
    def on_mode_change(self, index):
        if self.client.connected:
            ctrl = self._get_current_ctrl()
            if index == 1:  # Manual
                ctrl |= 0x01
            else:  # Passthrough
                ctrl &= ~0x01
            self.client.write_reg("dac", 1, ctrl)
    
    def on_enable_change(self, _):
        if self.client.connected:
            ctrl = self._get_current_ctrl() & 0x01  # Keep mode bit
            if self.en0_cb.isChecked():
                ctrl |= 0x02
            if self.en1_cb.isChecked():
                ctrl |= 0x04
            self.client.write_reg("dac", 1, ctrl)
    
    def on_prescaler(self, value):
        if self.client.connected:
            self.client.write_reg("dac", 2, value)
    
    def _get_current_ctrl(self) -> int:
        resp = self.client.get_all()
        if resp and resp.get("status") == "ok":
            return int(resp["dac"]["ctrl"])
        return 0
    
    def update_from_data(self, dac_data: Dict):
        """Update UI from polled data."""
        data = int(dac_data.get("data", 0)) & 0x0FFF
        ctrl = int(dac_data.get("ctrl", 0))
        pre = int(dac_data.get("pre", 0))
        
        # Update value (block signals to prevent loops)
        self.value_spin.blockSignals(True)
        self.value_spin.setValue(data)
        self.value_spin.blockSignals(False)
        
        self.value_slider.blockSignals(True)
        self.value_slider.setValue(data)
        self.value_slider.blockSignals(False)
        
        # Voltage (0-4V scale)
        voltage = (data / 4095.0) * 4.0
        self.voltage_label.setText(f"{voltage:.3f} V")
        
        # Bar
        self.dac_bar.setValue(data)
        
        # Control bits
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(1 if (ctrl & 0x01) else 0)
        self.mode_combo.blockSignals(False)
        
        self.en0_cb.blockSignals(True)
        self.en0_cb.setChecked(bool(ctrl & 0x02))
        self.en0_cb.blockSignals(False)
        
        self.en1_cb.blockSignals(True)
        self.en1_cb.setChecked(bool(ctrl & 0x04))
        self.en1_cb.blockSignals(False)
        
        self.prescaler_spin.blockSignals(True)
        self.prescaler_spin.setValue(pre)
        self.prescaler_spin.blockSignals(False)
        
        # Frequency
        freq_mhz = 100.0 / (2.0 * (pre + 1))
        self.freq_label.setText(f"{freq_mhz:.2f} MHz")


# =============================================================================
# SPGD Tab
# =============================================================================

class SPGDTab(QWidget):
    """Control panel for SPGD controller."""
    
    def __init__(self, client: ZynqClient):
        super().__init__()
        self.client = client
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Status Group ---
        status_group = QGroupBox("Status")
        status_layout = QGridLayout(status_group)
        
        self.enable_cb = QCheckBox("Enable SPGD Loop")
        self.enable_cb.setFont(QFont("", 12, QFont.Weight.Bold))
        self.enable_cb.stateChanged.connect(self.on_enable_change)
        status_layout.addWidget(self.enable_cb, 0, 0, 1, 2)
        
        self.passthrough_cb = QCheckBox("Passthrough Mode")
        self.passthrough_cb.stateChanged.connect(self.on_passthrough_change)
        status_layout.addWidget(self.passthrough_cb, 1, 0, 1, 2)
        
        layout.addWidget(status_group)
        
        # --- Parameters Group ---
        params_group = QGroupBox("SPGD Parameters")
        params_layout = QGridLayout(params_group)
        
        params_layout.addWidget(QLabel("Settle Cycles:"), 0, 0)
        self.settle_spin = QSpinBox()
        self.settle_spin.setRange(0, 65535)
        self.settle_spin.setSingleStep(10)
        self.settle_spin.valueChanged.connect(self.on_params_change)
        params_layout.addWidget(self.settle_spin, 0, 1)
        
        params_layout.addWidget(QLabel("Perturbation Amplitude:"), 1, 0)
        self.perturb_spin = QSpinBox()
        self.perturb_spin.setRange(0, 65535)
        self.perturb_spin.setSingleStep(10)
        self.perturb_spin.valueChanged.connect(self.on_params_change)
        params_layout.addWidget(self.perturb_spin, 1, 1)
        
        params_layout.addWidget(QLabel("Gamma (Learning Rate):"), 2, 0)
        self.gamma_spin = QSpinBox()
        self.gamma_spin.setRange(0, 2147483647)
        self.gamma_spin.setSingleStep(100)
        self.gamma_spin.valueChanged.connect(self.on_gamma_change)
        params_layout.addWidget(self.gamma_spin, 2, 1)
        
        layout.addWidget(params_group)
        
        # --- Reset Group ---
        reset_group = QGroupBox("DAC Reset")
        reset_layout = QHBoxLayout(reset_group)
        
        self.reset_btn = QPushButton("Manual Reset (Mid-Scale)")
        self.reset_btn.clicked.connect(self.on_reset)
        reset_layout.addWidget(self.reset_btn)
        
        layout.addWidget(reset_group)
        layout.addStretch()
    
    def on_enable_change(self, state):
        if self.client.connected:
            ctrl = self._get_current_ctrl()
            if state:
                ctrl |= 0x01
            else:
                ctrl &= ~0x01
            self.client.write_reg("spgd", 0, ctrl)
    
    def on_passthrough_change(self, state):
        if self.client.connected:
            ctrl = self._get_current_ctrl()
            if state:
                ctrl |= 0x02
            else:
                ctrl &= ~0x02
            self.client.write_reg("spgd", 0, ctrl)
    
    def on_params_change(self, _):
        if self.client.connected:
            settle = self.settle_spin.value()
            perturb = self.perturb_spin.value()
            config = (perturb << 16) | settle
            self.client.write_reg("spgd", 1, config)
    
    def on_gamma_change(self, value):
        if self.client.connected:
            self.client.write_reg("spgd", 2, value)
    
    def on_reset(self):
        if self.client.connected:
            self.client.pulse_bit("spgd", 2)
    
    def _get_current_ctrl(self) -> int:
        resp = self.client.get_all()
        if resp and resp.get("status") == "ok":
            return int(resp["spgd"]["ctrl"])
        return 0
    
    def update_from_data(self, spgd_data: Dict):
        """Update UI from polled data."""
        ctrl = int(spgd_data.get("ctrl", 0))
        config = int(spgd_data.get("config", 0))
        gamma = int(spgd_data.get("gamma", 0))
        
        settle = config & 0xFFFF
        perturb = (config >> 16) & 0xFFFF
        
        # Update controls (block signals)
        self.enable_cb.blockSignals(True)
        self.enable_cb.setChecked(bool(ctrl & 0x01))
        self.enable_cb.blockSignals(False)
        
        self.passthrough_cb.blockSignals(True)
        self.passthrough_cb.setChecked(bool(ctrl & 0x02))
        self.passthrough_cb.blockSignals(False)
        
        self.settle_spin.blockSignals(True)
        self.settle_spin.setValue(settle)
        self.settle_spin.blockSignals(False)
        
        self.perturb_spin.blockSignals(True)
        self.perturb_spin.setValue(perturb)
        self.perturb_spin.blockSignals(False)
        
        self.gamma_spin.blockSignals(True)
        self.gamma_spin.setValue(gamma)
        self.gamma_spin.blockSignals(False)


# =============================================================================
# Main Window
# =============================================================================

class MainWindow(QMainWindow):
    """Main application window with tabs for each peripheral."""
    
    def __init__(self, host: str = "localhost", port: int = 5000):
        super().__init__()
        self.client = ZynqClient(host, port)
        
        self.setWindowTitle("Zynq AXI Controller")
        self.setMinimumSize(500, 600)
        
        self.init_ui()
        
        # Polling timer
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll_data)
        
        # Try initial connection
        self.reconnect()
    
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # --- Connection Bar ---
        conn_layout = QHBoxLayout()
        
        conn_layout.addWidget(QLabel("Host:"))
        self.host_edit = QLineEdit(self.client.host)
        self.host_edit.setFixedWidth(150)
        conn_layout.addWidget(self.host_edit)
        
        conn_layout.addWidget(QLabel("Port:"))
        self.port_edit = QLineEdit(str(self.client.port))
        self.port_edit.setFixedWidth(60)
        conn_layout.addWidget(self.port_edit)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.reconnect)
        conn_layout.addWidget(self.connect_btn)
        
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: red;")
        conn_layout.addWidget(self.status_label)
        
        conn_layout.addStretch()
        layout.addLayout(conn_layout)
        
        # --- Tabs ---
        self.tabs = QTabWidget()
        
        self.adc_tab = ADCTab(self.client)
        self.tabs.addTab(self.adc_tab, "ADC (LTC2203)")
        
        self.dac_tab = DACTab(self.client)
        self.tabs.addTab(self.dac_tab, "DAC (LTC1666)")
        
        self.spgd_tab = SPGDTab(self.client)
        self.tabs.addTab(self.spgd_tab, "SPGD")
        
        layout.addWidget(self.tabs)
        
        # --- Bottom Bar ---
        bottom_layout = QHBoxLayout()
        
        bottom_layout.addWidget(QLabel("Poll Rate:"))
        self.poll_rate_spin = QSpinBox()
        self.poll_rate_spin.setRange(1, 100)
        self.poll_rate_spin.setValue(10)
        self.poll_rate_spin.setSuffix(" Hz")
        self.poll_rate_spin.valueChanged.connect(self.on_poll_rate_change)
        bottom_layout.addWidget(self.poll_rate_spin)
        
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
    
    def reconnect(self):
        """Attempt to connect/reconnect to the server."""
        self.poll_timer.stop()
        self.client.disconnect()
        
        # Update host/port from UI
        self.client.host = self.host_edit.text()
        try:
            self.client.port = int(self.port_edit.text())
        except ValueError:
            self.client.port = 5000
        
        if self.client.connect():
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: green;")
            self.connect_btn.setText("Reconnect")
            
            # Start polling
            interval = 1000 // self.poll_rate_spin.value()
            self.poll_timer.start(interval)
        else:
            self.status_label.setText("Connection Failed")
            self.status_label.setStyleSheet("color: red;")
    
    def on_poll_rate_change(self, value):
        """Update polling interval."""
        if self.poll_timer.isActive():
            interval = 1000 // value
            self.poll_timer.setInterval(interval)
    
    def poll_data(self):
        """Poll all data from server and update UI."""
        resp = self.client.get_all()
        
        if resp is None or resp.get("status") != "ok":
            # Connection lost
            self.poll_timer.stop()
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("color: red;")
            self.client.connected = False
            return
        
        # Update each tab
        if "adc" in resp:
            self.adc_tab.update_from_data(resp["adc"])
        if "dac" in resp:
            self.dac_tab.update_from_data(resp["dac"])
        if "spgd" in resp:
            self.spgd_tab.update_from_data(resp["spgd"])
    
    def closeEvent(self, event):
        """Clean up on close."""
        self.poll_timer.stop()
        self.client.disconnect()
        event.accept()


# =============================================================================
# Entry Point
# =============================================================================

def main():
    # Parse command line args
    host = "192.168.1.10"  # Default Zynq IP - change as needed
    port = 5000
    
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        try:
            port = int(sys.argv[2])
        except ValueError:
            pass
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow(host, port)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
