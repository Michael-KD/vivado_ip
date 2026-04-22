#!/usr/bin/env python3
"""
zynq_client.py - PyQt6 GUI for controlling Zynq AXI peripherals

Connects to zynq_server running on the Zynq board and provides a unified
interface for controlling variable numbers of ADC (LTC2203) and DAC (LTC1666) 
peripherals via dynamic addressing.

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
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QPalette, QColor

VERSION = "2.0"

# =============================================================================
# Hardware Addresses Configuration
# =============================================================================

# 1 ADC
ADC_ADDRS = [0x80030000]

# 8 DACs
DAC_ADDRS = [0x80040000]

# 1 SPGD
SPGD_ADDR = 0x80000000

# =============================================================================
# Network Client
# =============================================================================

class ZynqClient:
    """TCP/JSON client for communicating with zynq_server using dynamic addresses."""
    
    def __init__(self, host: str = "localhost", port: int = 5000):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.connected = False
    
    def connect(self) -> bool:
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
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None
        self.connected = False
    
    def send_command(self, cmd: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.connected or not self.sock:
            return None
        try:
            msg = json.dumps(cmd) + "\n"
            self.sock.sendall(msg.encode())
            
            data = b""
            while b"\n" not in data:
                chunk = self.sock.recv(65536)
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
            
    def read_all(self, addresses: list[int]) -> Optional[Dict[str, Any]]:
        """Fetch all register values for the requested addresses."""
        return self.send_command({"cmd": "read_all", "addresses": addresses})
    
    def write_reg(self, addr: int, reg: int, value: int) -> bool:
        """Write to a device register by its address."""
        resp = self.send_command({
            "cmd": "write",
            "addr": addr,
            "reg": reg,
            "value": value
        })
        return resp is not None and resp.get("status") == "ok"
    
    def pulse_bit(self, addr: int, bit: int) -> bool:
        """Pulse a control bit by its address."""
        resp = self.send_command({
            "cmd": "pulse",
            "addr": addr,
            "bit": bit
        })
        return resp is not None and resp.get("status") == "ok"


# =============================================================================
# Master Tab (SPGD + System Overview)
# =============================================================================

class MasterTab(QWidget):
    """Master Control tab with System Start, SPGD, and Master ADC/DAC overviews."""
    def __init__(self, client: ZynqClient, adc_addrs: list[int], dac_addrs: list[int], spgd_addr: int):
        super().__init__()
        self.client = client
        self.adc_addrs = adc_addrs
        self.dac_addrs = dac_addrs
        self.spgd_addr = spgd_addr
        
        self.spgd_ctrl = 0
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- System Control ---
        sys_group = QGroupBox("System Startup")
        sys_layout = QHBoxLayout(sys_group)
        self.start_sys_btn = QPushButton("Start System")
        self.start_sys_btn.clicked.connect(self.on_start_sys)
        self.start_sys_btn.setFont(QFont("", 14, QFont.Weight.Bold))
        sys_layout.addWidget(self.start_sys_btn)
        layout.addWidget(sys_group)

        # --- SPGD Section ---
        spgd_group = QGroupBox("SPGD Controller")
        spgd_layout = QGridLayout(spgd_group)
        self.spgd_enable_cb = QCheckBox("Enable SPGD Loop")
        self.spgd_enable_cb.stateChanged.connect(self.on_spgd_enable)
        self.spgd_passthrough_cb = QCheckBox("Passthrough Mode")
        self.spgd_passthrough_cb.stateChanged.connect(self.on_spgd_passthrough)
        spgd_layout.addWidget(self.spgd_enable_cb, 0, 0)
        spgd_layout.addWidget(self.spgd_passthrough_cb, 0, 1)

        self.spgd_settle_spin = QSpinBox()
        self.spgd_settle_spin.setRange(0, 65535)
        self.spgd_settle_spin.valueChanged.connect(self.on_spgd_params)
        self.spgd_perturb_spin = QSpinBox()
        self.spgd_perturb_spin.setRange(0, 65535)
        self.spgd_perturb_spin.valueChanged.connect(self.on_spgd_params)
        self.spgd_gamma_spin = QSpinBox()
        self.spgd_gamma_spin.setRange(0, 2147483647)
        self.spgd_gamma_spin.valueChanged.connect(self.on_spgd_gamma)
        
        spgd_layout.addWidget(QLabel("Settle:"), 1, 0)
        spgd_layout.addWidget(self.spgd_settle_spin, 1, 1)
        spgd_layout.addWidget(QLabel("Perturb:"), 2, 0)
        spgd_layout.addWidget(self.spgd_perturb_spin, 2, 1)
        spgd_layout.addWidget(QLabel("Gamma:"), 3, 0)
        spgd_layout.addWidget(self.spgd_gamma_spin, 3, 1)
        
        self.spgd_reset_btn = QPushButton("Pulse Manual Reset")
        self.spgd_reset_btn.clicked.connect(self.on_spgd_reset)
        spgd_layout.addWidget(self.spgd_reset_btn, 4, 0, 1, 2)
        layout.addWidget(spgd_group)
        
        # --- Master DAC Control ---
        dac_group = QGroupBox("Master DAC Control (All DACs)")
        dac_layout = QGridLayout(dac_group)
        
        self.master_dac_slider = QSlider(Qt.Orientation.Horizontal)
        self.master_dac_slider.setRange(0, 4095)
        self.master_dac_slider.valueChanged.connect(self.on_master_dac_slider)
        
        self.master_dac_spin = QSpinBox()
        self.master_dac_spin.setRange(0, 4095)
        self.master_dac_spin.valueChanged.connect(self.on_master_dac_spin)
        
        dac_layout.addWidget(QLabel("Set Value (Broadcast):"), 0, 0)
        dac_layout.addWidget(self.master_dac_spin, 0, 1)
        dac_layout.addWidget(self.master_dac_slider, 1, 0, 1, 2)
        
        layout.addWidget(dac_group)
        
        # --- Master ADC Overview ---
        adc_group = QGroupBox("ADC Status Overview")
        adc_layout = QVBoxLayout(adc_group)
        self.adc_info_label = QLabel("Waiting for data...")
        adc_layout.addWidget(self.adc_info_label)
        layout.addWidget(adc_group)
        
        layout.addStretch()

    def on_start_sys(self):
        # Placeholder for start system
        QMessageBox.information(self, "System Start", "Bootup sequence initiated (Placeholder).")

    def on_spgd_enable(self, state):
        if self.client.connected:
            ctrl = self.spgd_ctrl
            if state: ctrl |= 0x01
            else:     ctrl &= ~0x01
            self.client.write_reg(self.spgd_addr, 0, ctrl)
            self.spgd_ctrl = ctrl
            
    def on_spgd_passthrough(self, state):
        if self.client.connected:
            ctrl = self.spgd_ctrl
            if state: ctrl |= 0x02
            else:     ctrl &= ~0x02
            self.client.write_reg(self.spgd_addr, 0, ctrl)
            self.spgd_ctrl = ctrl

    def on_spgd_params(self, _):
        if self.client.connected:
            config = (self.spgd_perturb_spin.value() << 16) | self.spgd_settle_spin.value()
            self.client.write_reg(self.spgd_addr, 1, config)
            
    def on_spgd_gamma(self, value):
        if self.client.connected:
            self.client.write_reg(self.spgd_addr, 2, value)
            
    def on_spgd_reset(self):
        if self.client.connected:
            self.client.pulse_bit(self.spgd_addr, 2)

    def on_master_dac_slider(self, val):
        self.master_dac_spin.blockSignals(True)
        self.master_dac_spin.setValue(val)
        self.master_dac_spin.blockSignals(False)
        self._write_all_dacs(val)
        
    def on_master_dac_spin(self, val):
        self.master_dac_slider.blockSignals(True)
        self.master_dac_slider.setValue(val)
        self.master_dac_slider.blockSignals(False)
        self._write_all_dacs(val)
        
    def _write_all_dacs(self, val):
        if self.client.connected:
            for addr in self.dac_addrs:
                self.client.write_reg(addr, 0, val)

    def update_from_data(self, data: Dict):
        # Update SPGD
        spgd_d = data.get(str(self.spgd_addr), {})
        if spgd_d:
            self.spgd_ctrl = int(spgd_d.get("0", 0))
            config = int(spgd_d.get("1", 0))
            gamma = int(spgd_d.get("2", 0))
            
            self.spgd_enable_cb.blockSignals(True)
            self.spgd_enable_cb.setChecked(bool(self.spgd_ctrl & 0x01))
            self.spgd_enable_cb.blockSignals(False)
            
            self.spgd_passthrough_cb.blockSignals(True)
            self.spgd_passthrough_cb.setChecked(bool(self.spgd_ctrl & 0x02))
            self.spgd_passthrough_cb.blockSignals(False)
            
            self.spgd_settle_spin.blockSignals(True)
            self.spgd_settle_spin.setValue(config & 0xFFFF)
            self.spgd_settle_spin.blockSignals(False)
            
            self.spgd_perturb_spin.blockSignals(True)
            self.spgd_perturb_spin.setValue((config >> 16) & 0xFFFF)
            self.spgd_perturb_spin.blockSignals(False)
            
            self.spgd_gamma_spin.blockSignals(True)
            self.spgd_gamma_spin.setValue(gamma)
            self.spgd_gamma_spin.blockSignals(False)
            
        # Update ADC Overview
        adc_texts = []
        for i, addr in enumerate(self.adc_addrs):
            adc_d = data.get(str(addr), {})
            if adc_d:
                raw = int(adc_d.get("0", 0))
                val = raw & 0xFFFF
                if val >= 0x8000:
                    val -= 0x10000
                voltage = (val / 32768.0) * 10.0
                adc_texts.append(f"ADC {i} (0x{addr:08X}): {val:+7d} ({voltage:+7.3f} V)")
        
        if adc_texts:
            self.adc_info_label.setText("\n".join(adc_texts))


# =============================================================================
# ADC Tab
# =============================================================================

class ADCTab(QWidget):
    """Control panel for an ADC with dynamic dropdown selection."""
    def __init__(self, client: ZynqClient, addrs: list[int]):
        super().__init__()
        self.client = client
        self.addrs = addrs
        self.current_addr = addrs[0] if addrs else 0
        self.current_ctrl = 0
        self.last_data = {}
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Target Selection
        target_group = QGroupBox("Target Device")
        target_layout = QHBoxLayout(target_group)
        self.device_combo = QComboBox()
        for i, addr in enumerate(self.addrs):
            self.device_combo.addItem(f"ADC {i} (0x{addr:08X})", addr)
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        target_layout.addWidget(QLabel("Select ADC:"))
        target_layout.addWidget(self.device_combo)
        target_layout.addStretch()
        layout.addWidget(target_group)
        
        self.reading_group = QGroupBox(f"ADC Reading (0x{self.current_addr:08X})")
        reading_layout = QGridLayout(self.reading_group)
        
        self.adc_value_label = QLabel("0")
        self.adc_value_label.setFont(QFont("Courier", 24, QFont.Weight.Bold))
        self.adc_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reading_layout.addWidget(QLabel("Raw Value:"), 0, 0)
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
        
        self.adc_bar = QProgressBar()
        self.adc_bar.setMinimum(0)
        self.adc_bar.setMaximum(65535)
        self.adc_bar.setValue(32768)
        self.adc_bar.setTextVisible(False)
        self.adc_bar.setFixedHeight(30)
        reading_layout.addWidget(QLabel("-10V"), 3, 0)
        reading_layout.addWidget(self.adc_bar, 3, 1)
        reading_layout.addWidget(QLabel("+10V"), 3, 2)
        
        layout.addWidget(self.reading_group)
        
        control_group = QGroupBox("Hardware Control")
        control_layout = QGridLayout(control_group)
        
        self.output_enable_cb = QCheckBox("Output Enable")
        self.output_enable_cb.stateChanged.connect(self.on_output_enable)
        control_layout.addWidget(self.output_enable_cb, 0, 0)
        
        control_layout.addWidget(QLabel("Clock Source:"), 1, 0)
        self.clock_source_combo = QComboBox()
        self.clock_source_combo.addItems(["External", "Internal"])
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

    def on_device_changed(self, index):
        self.current_addr = self.device_combo.itemData(index)
        self.reading_group.setTitle(f"ADC Reading (0x{self.current_addr:08X})")
        if self.last_data:
            self.update_from_data(self.last_data)
            
    def on_output_enable(self, state):
        if self.client.connected:
            ctrl = self.current_ctrl
            if state: ctrl |= 0x01
            else:     ctrl &= ~0x01
            self.client.write_reg(self.current_addr, 1, ctrl)
            self.current_ctrl = ctrl
            
    def on_clock_source(self, index):
        if self.client.connected:
            ctrl = self.current_ctrl
            if index == 1: ctrl |= 0x02
            else:          ctrl &= ~0x02
            self.client.write_reg(self.current_addr, 1, ctrl)
            self.current_ctrl = ctrl
            
    def on_prescaler(self, value):
        if self.client.connected:
            self.client.write_reg(self.current_addr, 2, value)
    
    def update_from_data(self, data: Dict):
        self.last_data = data
        adc_data = data.get(str(self.current_addr), {})
        if not adc_data:
            return
            
        raw_data = int(adc_data.get("0", 0))
        self.current_ctrl = int(adc_data.get("1", 0))
        pre = int(adc_data.get("2", 0))
        
        adc_val = raw_data & 0xFFFF
        if adc_val >= 0x8000:
            adc_val -= 0x10000
        overflow = (raw_data >> 16) & 0x01
        
        self.adc_value_label.setText(f"{adc_val:+6d}")
        voltage = (adc_val / 32768.0) * 10.0
        self.voltage_label.setText(f"{voltage:+7.3f} V")
        
        if overflow:
            self.overflow_label.setText("YES!")
            self.overflow_label.setStyleSheet("color: red; font-weight: bold;")
        else:
            self.overflow_label.setText("NO")
            self.overflow_label.setStyleSheet("")
        
        self.adc_bar.setValue(adc_val + 32768)
        
        self.output_enable_cb.blockSignals(True)
        self.output_enable_cb.setChecked(bool(self.current_ctrl & 0x01))
        self.output_enable_cb.blockSignals(False)
        
        self.clock_source_combo.blockSignals(True)
        self.clock_source_combo.setCurrentIndex(1 if (self.current_ctrl & 0x02) else 0)
        self.clock_source_combo.blockSignals(False)
        
        self.prescaler_spin.blockSignals(True)
        self.prescaler_spin.setValue(pre)
        self.prescaler_spin.blockSignals(False)
        
        freq_mhz = 100.0 / (2.0 * (pre + 1))
        self.freq_label.setText(f"{freq_mhz:.2f} MHz")


# =============================================================================
# DAC Tab
# =============================================================================

class DACTab(QWidget):
    """Control panel for a DAC with dynamic dropdown selection."""
    def __init__(self, client: ZynqClient, addrs: list[int]):
        super().__init__()
        self.client = client
        self.addrs = addrs
        self.current_addr = addrs[0] if addrs else 0
        self.current_ctrl = 0
        self.last_data = {}
        self.ramp_enabled = {addr: False for addr in addrs}
        self.ramp_values = {addr: 0 for addr in addrs}
        self.ramp_speed = {addr: 400 for addr in addrs}  # steps per second
        self.ramp_interval_ms = 20
        self.ramp_timer = QTimer(self)
        self.ramp_timer.setInterval(self.ramp_interval_ms)
        self.ramp_timer.timeout.connect(self.on_ramp_tick)
        self.ramp_timer.start()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        target_group = QGroupBox("Target Device")
        target_layout = QHBoxLayout(target_group)
        self.device_combo = QComboBox()
        for i, addr in enumerate(self.addrs):
            self.device_combo.addItem(f"DAC {i} (0x{addr:08X})", addr)
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        target_layout.addWidget(QLabel("Select DAC:"))
        target_layout.addWidget(self.device_combo)
        target_layout.addStretch()
        layout.addWidget(target_group)
        
        self.output_group = QGroupBox(f"DAC Output (0x{self.current_addr:08X})")
        output_layout = QGridLayout(self.output_group)
        
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
        
        self.dac_bar = QProgressBar()
        self.dac_bar.setMinimum(0)
        self.dac_bar.setMaximum(4095)
        self.dac_bar.setTextVisible(False)
        self.dac_bar.setFixedHeight(25)
        output_layout.addWidget(QLabel("0V"), 3, 0)
        output_layout.addWidget(self.dac_bar, 3, 1)
        output_layout.addWidget(QLabel("4V"), 3, 2)
        
        layout.addWidget(self.output_group)
        
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

        self.latch_oe_cb = QCheckBox("Latch Output Enable")
        self.latch_oe_cb.stateChanged.connect(self.on_latch_change)
        control_layout.addWidget(self.latch_oe_cb, 3, 0, 1, 2)

        self.ramp_enable_cb = QCheckBox("Enable Ramp (0 -> 4095)")
        self.ramp_enable_cb.stateChanged.connect(self.on_ramp_enable)
        control_layout.addWidget(self.ramp_enable_cb, 4, 0, 1, 2)

        control_layout.addWidget(QLabel("Ramp Speed:"), 5, 0)
        self.ramp_speed_spin = QSpinBox()
        self.ramp_speed_spin.setRange(1, 20000)
        self.ramp_speed_spin.setSuffix(" steps/s")
        self.ramp_speed_spin.setValue(self.ramp_speed.get(self.current_addr, 400))
        self.ramp_speed_spin.valueChanged.connect(self.on_ramp_speed_change)
        control_layout.addWidget(self.ramp_speed_spin, 5, 1)
        
        layout.addWidget(control_group)
        
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

    def on_device_changed(self, index):
        self.current_addr = self.device_combo.itemData(index)
        self.output_group.setTitle(f"DAC Output (0x{self.current_addr:08X})")

        self.ramp_enable_cb.blockSignals(True)
        self.ramp_enable_cb.setChecked(self.ramp_enabled.get(self.current_addr, False))
        self.ramp_enable_cb.blockSignals(False)

        self.ramp_speed_spin.blockSignals(True)
        self.ramp_speed_spin.setValue(self.ramp_speed.get(self.current_addr, 400))
        self.ramp_speed_spin.blockSignals(False)

        if self.last_data:
            self.update_from_data(self.last_data)

    def on_value_change(self, value):
        if self.client.connected:
            self.value_slider.blockSignals(True)
            self.value_slider.setValue(value)
            self.value_slider.blockSignals(False)
            self.client.write_reg(self.current_addr, 0, value)
    
    def on_slider_change(self, value):
        if self.client.connected:
            self.value_spin.blockSignals(True)
            self.value_spin.setValue(value)
            self.value_spin.blockSignals(False)
            self.client.write_reg(self.current_addr, 0, value)
            
    def on_mode_change(self, index):
        if self.client.connected:
            ctrl = self.current_ctrl
            if index == 1: ctrl |= 0x01
            else:          ctrl &= ~0x01
            self.client.write_reg(self.current_addr, 1, ctrl)
            self.current_ctrl = ctrl
            
    def on_enable_change(self, _):
        if self.client.connected:
            ctrl = self.current_ctrl & 0x09
            if self.en0_cb.isChecked(): ctrl |= 0x02
            if self.en1_cb.isChecked(): ctrl |= 0x04
            self.client.write_reg(self.current_addr, 1, ctrl)
            self.current_ctrl = ctrl

    def on_latch_change(self, state):
        if self.client.connected:
            ctrl = self.current_ctrl
            if state: ctrl |= 0x08
            else:     ctrl &= ~0x08
            self.client.write_reg(self.current_addr, 1, ctrl)
            self.current_ctrl = ctrl
            
    def on_prescaler(self, value):
        if self.client.connected:
            self.client.write_reg(self.current_addr, 2, value)

    def on_ramp_enable(self, state):
        enabled = bool(state)
        self.ramp_enabled[self.current_addr] = enabled
        if enabled:
            self.ramp_values[self.current_addr] = self.value_spin.value()

    def on_ramp_speed_change(self, value):
        self.ramp_speed[self.current_addr] = value

    def on_ramp_tick(self):
        if not self.client.connected:
            return

        for addr in self.addrs:
            if not self.ramp_enabled.get(addr, False):
                continue

            speed = self.ramp_speed.get(addr, 400)
            step = max(1, (speed * self.ramp_interval_ms) // 1000)
            next_val = (self.ramp_values.get(addr, 0) + step) % 4096
            self.ramp_values[addr] = next_val
            self.client.write_reg(addr, 0, next_val)

            if addr == self.current_addr:
                self.value_spin.blockSignals(True)
                self.value_spin.setValue(next_val)
                self.value_spin.blockSignals(False)

                self.value_slider.blockSignals(True)
                self.value_slider.setValue(next_val)
                self.value_slider.blockSignals(False)

                voltage = (next_val / 4095.0) * 4.0
                self.voltage_label.setText(f"{voltage:.3f} V")
                self.dac_bar.setValue(next_val)
            
    def update_from_data(self, data: Dict):
        self.last_data = data

        for addr in self.addrs:
            dev_data = data.get(str(addr), {})
            if dev_data:
                self.ramp_values[addr] = int(dev_data.get("0", 0)) & 0x0FFF

        dac_data = data.get(str(self.current_addr), {})
        if not dac_data:
            return
            
        val = int(dac_data.get("0", 0)) & 0x0FFF
        self.current_ctrl = int(dac_data.get("1", 0))
        pre = int(dac_data.get("2", 0))
        
        self.value_spin.blockSignals(True)
        self.value_spin.setValue(val)
        self.value_spin.blockSignals(False)
        
        self.value_slider.blockSignals(True)
        self.value_slider.setValue(val)
        self.value_slider.blockSignals(False)
        
        voltage = (val / 4095.0) * 4.0
        self.voltage_label.setText(f"{voltage:.3f} V")
        self.dac_bar.setValue(val)
        
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(1 if (self.current_ctrl & 0x01) else 0)
        self.mode_combo.blockSignals(False)
        
        self.en0_cb.blockSignals(True)
        self.en0_cb.setChecked(bool(self.current_ctrl & 0x02))
        self.en0_cb.blockSignals(False)
        
        self.en1_cb.blockSignals(True)
        self.en1_cb.setChecked(bool(self.current_ctrl & 0x04))
        self.en1_cb.blockSignals(False)

        self.latch_oe_cb.blockSignals(True)
        self.latch_oe_cb.setChecked(bool(self.current_ctrl & 0x08))
        self.latch_oe_cb.blockSignals(False)

        self.ramp_enable_cb.blockSignals(True)
        self.ramp_enable_cb.setChecked(self.ramp_enabled.get(self.current_addr, False))
        self.ramp_enable_cb.blockSignals(False)

        self.ramp_speed_spin.blockSignals(True)
        self.ramp_speed_spin.setValue(self.ramp_speed.get(self.current_addr, 400))
        self.ramp_speed_spin.blockSignals(False)
        
        self.prescaler_spin.blockSignals(True)
        self.prescaler_spin.setValue(pre)
        self.prescaler_spin.blockSignals(False)
        
        freq_mhz = 100.0 / (2.0 * (pre + 1))
        self.freq_label.setText(f"{freq_mhz:.2f} MHz")


# =============================================================================
# Main Window
# =============================================================================

class MainWindow(QMainWindow):
    def __init__(self, host: str = "localhost", port: int = 5000):
        super().__init__()
        self.client = ZynqClient(host, port)
        
        self.setWindowTitle("Zynq Dynamic AXI Controller")
        self.setMinimumSize(600, 700)
        
        self.init_ui()
        
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll_data)
        
        self.reconnect()
    
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
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
        
        self.tabs = QTabWidget()
        
        self.master_tab = MasterTab(self.client, ADC_ADDRS, DAC_ADDRS, SPGD_ADDR)
        self.tabs.addTab(self.master_tab, "Master / SPGD")
        
        self.adc_tab = ADCTab(self.client, ADC_ADDRS)
        self.tabs.addTab(self.adc_tab, "ADC Control")
            
        self.dac_tab = DACTab(self.client, DAC_ADDRS)
        self.tabs.addTab(self.dac_tab, "DAC Control")
            
        layout.addWidget(self.tabs)
        
        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(QLabel("Poll Rate:"))
        self.poll_rate_spin = QSpinBox()
        self.poll_rate_spin.setRange(1, 100)
        self.poll_rate_spin.setValue(10)
        self.poll_rate_spin.setSuffix(" Hz")
        self.poll_rate_spin.valueChanged.connect(self.on_poll_rate_change)
        bottom_layout.addWidget(self.poll_rate_spin)
        bottom_layout.addStretch()
        version_label = QLabel(f"Version {VERSION}")
        version_label.setStyleSheet("color: gray;")
        bottom_layout.addWidget(version_label)
        layout.addLayout(bottom_layout)
    
    def reconnect(self):
        self.poll_timer.stop()
        self.client.disconnect()
        self.client.host = self.host_edit.text()
        try:
            self.client.port = int(self.port_edit.text())
        except ValueError:
            self.client.port = 5000
        
        if self.client.connect():
            self.status_label.setText("Connected")
            self.status_label.setStyleSheet("color: green;")
            self.connect_btn.setText("Reconnect")
            interval = 1000 // self.poll_rate_spin.value()
            self.poll_timer.start(interval)
        else:
            self.status_label.setText("Connection Failed")
            self.status_label.setStyleSheet("color: red;")
    
    def on_poll_rate_change(self, value):
        if self.poll_timer.isActive():
            interval = 1000 // value
            self.poll_timer.setInterval(interval)
    
    def poll_data(self):
        all_addrs = ADC_ADDRS + DAC_ADDRS + [SPGD_ADDR]
        resp = self.client.read_all(all_addrs)
        
        if resp is None or resp.get("status") != "ok":
            self.poll_timer.stop()
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("color: red;")
            self.client.connected = False
            return
        
        data = resp.get("data", {})
        
        self.master_tab.update_from_data(data)
        self.adc_tab.update_from_data(data)
        self.dac_tab.update_from_data(data)
    
    def closeEvent(self, event):
        self.poll_timer.stop()
        self.client.disconnect()
        event.accept()

def main():
    host = "192.168.1.85"
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
