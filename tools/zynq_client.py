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

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox,
    QComboBox, QProgressBar, QGroupBox, QLineEdit, QMessageBox,
    QSlider
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont

VERSION = "2.3"


def _reg_to_int(value: Any) -> int:
    """Best-effort conversion for register values returned by JSON transport."""
    try:
        if isinstance(value, str):
            return int(value, 0)
        return int(value)
    except (TypeError, ValueError):
        return 0


def format_raw_regs(dev_data: Dict[str, Any], count: int = 4) -> str:
    """Format device register map values as fixed-width hex readback text."""
    return " ".join(
        f"R{reg}=0x{_reg_to_int(dev_data.get(str(reg), 0)) & 0xFFFFFFFF:08X}"
        for reg in range(count)
    )


def _on_off(value: int) -> str:
    return "ON" if value else "OFF"


def format_spgd_bits(dev_data: Dict[str, Any]) -> str:
    """Decode SPGD AXI control/config fields from the RTL mapping."""
    ctrl = _reg_to_int(dev_data.get("0", 0))
    cfg = _reg_to_int(dev_data.get("1", 0))
    gamma = _reg_to_int(dev_data.get("2", 0))
    settle = cfg & 0xFFFF
    perturb = (cfg >> 16) & 0xFFFF
    return (
        f"enable_loop={_on_off(ctrl & 0x01)} "
        f"passthrough={_on_off(ctrl & 0x02)} "
        f"soft_reset={(ctrl >> 2) & 0x01} "
        f"settle={settle} perturb={perturb} gamma={gamma}"
    )


def format_adc_bits(dev_data: Dict[str, Any]) -> str:
    """Decode LTC2203 AXI fields: R0 sample data, R1 control bits, R2 prescaler."""
    r0 = _reg_to_int(dev_data.get("0", 0))
    r1 = _reg_to_int(dev_data.get("1", 0))
    r2 = _reg_to_int(dev_data.get("2", 0))
    sample = r0 & 0xFFFF
    if sample >= 0x8000:
        sample -= 0x10000
    return (
        f"oe={_on_off(r1 & 0x01)} "
        f"clk_sel={(r1 >> 1) & 0x01} "
        f"sample={sample:+d} prescaler={r2 & 0xFFFF}"
    )


def format_dac_bits(dev_data: Dict[str, Any]) -> str:
    """Decode LTC1666 AXI fields: R0 data, R1 control bits, R2 prescaler."""
    r0 = _reg_to_int(dev_data.get("0", 0))
    r1 = _reg_to_int(dev_data.get("1", 0))
    r2 = _reg_to_int(dev_data.get("2", 0))
    return (
        f"mode={'MANUAL' if (r1 & 0x01) else 'PASS'} "
        f"clk0={_on_off(r1 & 0x02)} "
        f"clk1={_on_off(r1 & 0x04)} "
        f"latch={_on_off(r1 & 0x08)} "
        f"ramp={_on_off(r1 & 0x10)} "
        f"value={r0 & 0x0FFF} prescaler={r2 & 0xFFFF}"
    )

# =============================================================================
# Hardware Addresses Configuration
# =============================================================================

# 1 ADC
ADC_ADDRS = [0x80030000]

# 8 DACs
DAC_ADDRS = [0x80100000, 0x80110000, 0x80120000, 0x80130000, 0x80140000, 0x80150000, 0x80160000, 0x80170000]

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
        self.start_sys_btn.setToolTip("Placeholder startup action for future bring-up sequencing.")
        sys_layout.addWidget(self.start_sys_btn)
        layout.addWidget(sys_group)

        # --- SPGD Section ---
        spgd_group = QGroupBox("SPGD Controller")
        spgd_layout = QGridLayout(spgd_group)
        self.spgd_enable_cb = QCheckBox("Enable SPGD Loop")
        self.spgd_enable_cb.stateChanged.connect(self.on_spgd_enable)
        self.spgd_enable_cb.setToolTip("Control bit 0: enable/disable SPGD feedback loop.")
        self.spgd_passthrough_cb = QCheckBox("Passthrough Mode")
        self.spgd_passthrough_cb.stateChanged.connect(self.on_spgd_passthrough)
        self.spgd_passthrough_cb.setToolTip("Control bit 1: bypass SPGD update and use passthrough DAC source.")
        spgd_layout.addWidget(self.spgd_enable_cb, 0, 0)
        spgd_layout.addWidget(self.spgd_passthrough_cb, 0, 1)

        self.spgd_settle_spin = QSpinBox()
        self.spgd_settle_spin.setRange(0, 65535)
        self.spgd_settle_spin.valueChanged.connect(self.on_spgd_params)
        self.spgd_settle_spin.setToolTip("Settle wait in SPGD FSM clock cycles for both +du and -du measurements.")
        self.spgd_perturb_spin = QSpinBox()
        self.spgd_perturb_spin.setRange(0, 65535)
        self.spgd_perturb_spin.valueChanged.connect(self.on_spgd_params)
        self.spgd_perturb_spin.setToolTip("Perturbation magnitude du in DAC counts applied per channel.")
        self.spgd_gamma_spin = QSpinBox()
        self.spgd_gamma_spin.setRange(0, 2147483647)
        self.spgd_gamma_spin.valueChanged.connect(self.on_spgd_gamma)
        self.spgd_gamma_spin.setToolTip("Learning rate gamma register. Datapath uses fixed-point scaling (product bits [31:16]).")
        
        settle_label = QLabel("Settle:")
        settle_label.setToolTip("Settling delay after each perturbation, in SPGD clock cycles.")
        spgd_layout.addWidget(settle_label, 1, 0)
        spgd_layout.addWidget(self.spgd_settle_spin, 1, 1)
        perturb_label = QLabel("Perturb:")
        perturb_label.setToolTip("Unsigned perturbation amplitude du, in DAC counts.")
        spgd_layout.addWidget(perturb_label, 2, 0)
        spgd_layout.addWidget(self.spgd_perturb_spin, 2, 1)
        gamma_label = QLabel("Gamma:")
        gamma_label.setToolTip("Signed learning-rate parameter used in update term gamma * deltaJ.")
        spgd_layout.addWidget(gamma_label, 3, 0)
        spgd_layout.addWidget(self.spgd_gamma_spin, 3, 1)
        
        self.spgd_reset_btn = QPushButton("Pulse Manual Reset")
        self.spgd_reset_btn.clicked.connect(self.on_spgd_reset)
        self.spgd_reset_btn.setToolTip("Pulse control bit 2 for one-shot SPGD soft reset.")
        spgd_layout.addWidget(self.spgd_reset_btn, 4, 0, 1, 2)
        layout.addWidget(spgd_group)
        
        # --- Master DAC Control ---
        dac_group = QGroupBox("Master DAC Control (All DACs)")
        dac_layout = QGridLayout(dac_group)
        
        self.master_dac_slider = QSlider(Qt.Orientation.Horizontal)
        self.master_dac_slider.setRange(0, 4095)
        self.master_dac_slider.valueChanged.connect(self.on_master_dac_slider)
        self.master_dac_slider.setToolTip("Broadcast manual DAC value to all DAC addresses.")
        
        self.master_dac_spin = QSpinBox()
        self.master_dac_spin.setRange(0, 4095)
        self.master_dac_spin.valueChanged.connect(self.on_master_dac_spin)
        self.master_dac_spin.setToolTip("Broadcast manual DAC code (0..4095) to all DACs.")
        
        broadcast_label = QLabel("Set Value (Broadcast):")
        broadcast_label.setToolTip("Writes REG0 for all DAC devices in the configured list.")
        dac_layout.addWidget(broadcast_label, 0, 0)
        dac_layout.addWidget(self.master_dac_spin, 0, 1)
        dac_layout.addWidget(self.master_dac_slider, 1, 0, 1, 2)
        
        layout.addWidget(dac_group)
        
        # --- Master ADC Overview ---
        adc_group = QGroupBox("ADC Status Overview")
        adc_layout = QVBoxLayout(adc_group)
        self.adc_info_label = QLabel("Waiting for data...")
        self.adc_info_label.setToolTip("Live decoded ADC readings from all configured ADC addresses.")
        adc_layout.addWidget(self.adc_info_label)
        layout.addWidget(adc_group)

        raw_group = QGroupBox("Raw AXI Registers")
        raw_layout = QVBoxLayout(raw_group)
        self.raw_snapshot_label = QLabel("Waiting for data...")
        self.raw_snapshot_label.setFont(QFont("Courier", 10))
        self.raw_snapshot_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.raw_snapshot_label.setToolTip("Live AXI readback snapshot for SPGD, ADC, and DAC register banks.")
        raw_layout.addWidget(self.raw_snapshot_label)
        layout.addWidget(raw_group)
        
        layout.addStretch()

    def on_start_sys(self):
        # Placeholder for start system
        QMessageBox.information(self, "System Start", "Bootup sequence initiated (Placeholder).")

    def on_spgd_enable(self, state):
        if self.client.connected:
            ctrl = self.spgd_ctrl
            if state:
                ctrl |= 0x01
            else:
                ctrl &= ~0x01
            self.client.write_reg(self.spgd_addr, 0, ctrl)
            self.spgd_ctrl = ctrl
            
    def on_spgd_passthrough(self, state):
        if self.client.connected:
            ctrl = self.spgd_ctrl
            if state:
                ctrl |= 0x02
            else:
                ctrl &= ~0x02
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

        raw_lines = []
        spgd_data = data.get(str(self.spgd_addr), {})
        if spgd_data:
            raw_lines.append(
                f"SPGD (0x{self.spgd_addr:08X}): {format_raw_regs(spgd_data)}\n"
                f"  {format_spgd_bits(spgd_data)}"
            )

        for i, addr in enumerate(self.adc_addrs):
            adc_data = data.get(str(addr), {})
            if adc_data:
                raw_lines.append(
                    f"ADC {i} (0x{addr:08X}): {format_raw_regs(adc_data)}\n"
                    f"  {format_adc_bits(adc_data)}"
                )

        for i, addr in enumerate(self.dac_addrs):
            dac_data = data.get(str(addr), {})
            if dac_data:
                raw_lines.append(
                    f"DAC {i} (0x{addr:08X}): {format_raw_regs(dac_data)}\n"
                    f"  {format_dac_bits(dac_data)}"
                )

        if raw_lines:
            self.raw_snapshot_label.setText("\n".join(raw_lines))


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
        self.device_combo.setToolTip("Select which ADC base address this tab controls.")
        select_adc_label = QLabel("Select ADC:")
        select_adc_label.setToolTip("Active ADC target for writes and displayed reads.")
        target_layout.addWidget(select_adc_label)
        target_layout.addWidget(self.device_combo)
        target_layout.addStretch()
        layout.addWidget(target_group)
        
        self.reading_group = QGroupBox(f"ADC Reading (0x{self.current_addr:08X})")
        reading_layout = QGridLayout(self.reading_group)
        
        self.adc_value_label = QLabel("0")
        self.adc_value_label.setFont(QFont("Courier", 24, QFont.Weight.Bold))
        self.adc_value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.adc_value_label.setToolTip("Signed ADC code after two's complement conversion.")
        raw_label = QLabel("Raw Value:")
        raw_label.setToolTip("Current ADC sample represented as signed counts.")
        reading_layout.addWidget(raw_label, 0, 0)
        reading_layout.addWidget(self.adc_value_label, 0, 1)
        
        self.voltage_label = QLabel("0.000 V")
        self.voltage_label.setFont(QFont("Courier", 24, QFont.Weight.Bold))
        self.voltage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voltage_label.setToolTip("Estimated voltage from signed ADC code using +/-10V full scale.")
        voltage_text_label = QLabel("Voltage:")
        voltage_text_label.setToolTip("Estimated ADC input voltage.")
        reading_layout.addWidget(voltage_text_label, 1, 0)
        reading_layout.addWidget(self.voltage_label, 1, 1)
        
        self.overflow_label = QLabel("NO")
        self.overflow_label.setFont(QFont("Courier", 16))
        self.overflow_label.setToolTip("ADC overflow flag from status bit in REG0.")
        overflow_text_label = QLabel("Overflow:")
        overflow_text_label.setToolTip("Indicates ADC saturation/overflow condition.")
        reading_layout.addWidget(overflow_text_label, 2, 0)
        reading_layout.addWidget(self.overflow_label, 2, 1)
        
        self.adc_bar = QProgressBar()
        self.adc_bar.setMinimum(0)
        self.adc_bar.setMaximum(65535)
        self.adc_bar.setValue(32768)
        self.adc_bar.setTextVisible(False)
        self.adc_bar.setFixedHeight(30)
        self.adc_bar.setToolTip("Visualized ADC range from -10V to +10V.")
        minus10_label = QLabel("-10V")
        minus10_label.setToolTip("ADC negative full-scale reference.")
        reading_layout.addWidget(minus10_label, 3, 0)
        reading_layout.addWidget(self.adc_bar, 3, 1)
        plus10_label = QLabel("+10V")
        plus10_label.setToolTip("ADC positive full-scale reference.")
        reading_layout.addWidget(plus10_label, 3, 2)
        
        layout.addWidget(self.reading_group)
        
        control_group = QGroupBox("Hardware Control")
        control_layout = QGridLayout(control_group)
        
        self.output_enable_cb = QCheckBox("Output Enable")
        self.output_enable_cb.stateChanged.connect(self.on_output_enable)
        self.output_enable_cb.setToolTip("Control bit 0: enable ADC interface output path.")
        control_layout.addWidget(self.output_enable_cb, 0, 0)

        adc_prescaler_label = QLabel("Prescaler:")
        adc_prescaler_label.setToolTip("ADC encode-clock divider register value.")
        control_layout.addWidget(adc_prescaler_label, 1, 0)
        self.prescaler_spin = QSpinBox()
        self.prescaler_spin.setRange(0, 65535)
        self.prescaler_spin.valueChanged.connect(self.on_prescaler)
        self.prescaler_spin.setToolTip("Clock divider used by ADC clock generation.")
        control_layout.addWidget(self.prescaler_spin, 1, 1)
        
        self.freq_label = QLabel("-- MHz")
        self.freq_label.setToolTip("Computed from prescaler: 100 MHz / (2*(pre+1)).")
        sample_rate_label = QLabel("Sample Rate:")
        sample_rate_label.setToolTip("Estimated ADC sampling frequency from divider setting.")
        control_layout.addWidget(sample_rate_label, 2, 0)
        control_layout.addWidget(self.freq_label, 2, 1)
        
        layout.addWidget(control_group)

        raw_group = QGroupBox("Raw AXI Registers")
        raw_layout = QVBoxLayout(raw_group)
        self.raw_regs_label = QLabel("R0=0x00000000 R1=0x00000000 R2=0x00000000 R3=0x00000000")
        self.raw_regs_label.setFont(QFont("Courier", 10))
        self.raw_regs_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.raw_regs_label.setToolTip("Raw register readback for the selected ADC AXI device.")
        raw_layout.addWidget(self.raw_regs_label)

        self.raw_bits_label = QLabel("oe=OFF clk_sel=0 sample=+0 prescaler=0")
        self.raw_bits_label.setFont(QFont("Courier", 10))
        self.raw_bits_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.raw_bits_label.setToolTip("Decoded ADC register fields based on AXI RTL bit assignments.")
        raw_layout.addWidget(self.raw_bits_label)
        layout.addWidget(raw_group)

        layout.addStretch()

    def on_device_changed(self, index):
        self.current_addr = self.device_combo.itemData(index)
        self.reading_group.setTitle(f"ADC Reading (0x{self.current_addr:08X})")
        if self.last_data:
            self.update_from_data(self.last_data)
            
    def on_output_enable(self, state):
        if self.client.connected:
            ctrl = self.current_ctrl
            if state:
                ctrl |= 0x01
            else:
                ctrl &= ~0x01
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

        self.raw_regs_label.setText(format_raw_regs(adc_data))
        self.raw_bits_label.setText(format_adc_bits(adc_data))
            
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
    MASK_MODE = 0x01
    MASK_EN0 = 0x02
    MASK_LATCH = 0x08
    MASK_HW_RAMP = 0x10

    def __init__(self, client: ZynqClient, addrs: list[int]):
        super().__init__()
        self.client = client
        self.addrs = addrs
        self.global_addr = addrs[0] if addrs else 0
        self.current_addr = addrs[0] if addrs else 0
        self.current_ctrl = 0
        self.global_ctrl = 0
        self.global_pre = 0
        self.last_data = {}
        self.ramp_enabled = {addr: False for addr in addrs}
        self.all_rows: Dict[int, Dict[str, Any]] = {}
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        target_group = QGroupBox("Target Device")
        target_layout = QHBoxLayout(target_group)
        self.select_dac_label = QLabel("Select DAC:")
        self.select_dac_label.setToolTip("Active DAC target for writes and displayed reads.")
        self.device_combo = QComboBox()
        for i, addr in enumerate(self.addrs):
            self.device_combo.addItem(f"DAC {i} (0x{addr:08X})", addr)
        self.device_combo.currentIndexChanged.connect(self.on_device_changed)
        self.device_combo.setToolTip("Select which DAC base address this tab controls.")

        self.show_all_cb = QCheckBox("Show all DACs")
        self.show_all_cb.stateChanged.connect(self.on_view_mode_changed)
        self.show_all_cb.setToolTip("Toggle between single-DAC view and controlling all DAC channels on one page.")

        target_layout.addWidget(self.select_dac_label)
        target_layout.addWidget(self.device_combo)
        target_layout.addWidget(self.show_all_cb)
        target_layout.addStretch()
        layout.addWidget(target_group)
        
        self.output_group = QGroupBox(f"DAC Output (0x{self.current_addr:08X})")
        output_layout = QGridLayout(self.output_group)
        
        dac_value_label = QLabel("Value (0-4095):")
        dac_value_label.setToolTip("Manual DAC input code. 0 = 0V, 4095 = full scale.")
        output_layout.addWidget(dac_value_label, 0, 0)
        self.value_spin = QSpinBox()
        self.value_spin.setRange(0, 4095)
        self.value_spin.valueChanged.connect(self.on_value_change)
        self.value_spin.setToolTip("Manual DAC code written to REG0.")
        output_layout.addWidget(self.value_spin, 0, 1)
        
        self.value_slider = QSlider(Qt.Orientation.Horizontal)
        self.value_slider.setRange(0, 4095)
        self.value_slider.valueChanged.connect(self.on_slider_change)
        self.value_slider.setToolTip("Manual DAC code slider (mirrors Value spinbox).")
        output_layout.addWidget(self.value_slider, 1, 0, 1, 3)
        
        self.voltage_label = QLabel("0.000 V")
        self.voltage_label.setFont(QFont("Courier", 18, QFont.Weight.Bold))
        self.voltage_label.setToolTip("Estimated output voltage from DAC code using 0..4V scale.")
        dac_voltage_text_label = QLabel("Est. Voltage:")
        dac_voltage_text_label.setToolTip("Estimated analog output voltage.")
        output_layout.addWidget(dac_voltage_text_label, 2, 0)
        output_layout.addWidget(self.voltage_label, 2, 1)
        
        self.dac_bar = QProgressBar()
        self.dac_bar.setMinimum(0)
        self.dac_bar.setMaximum(4095)
        self.dac_bar.setTextVisible(False)
        self.dac_bar.setFixedHeight(25)
        self.dac_bar.setToolTip("Visualized DAC code from 0 to full scale.")
        dac_0v_label = QLabel("0V")
        dac_0v_label.setToolTip("DAC minimum output reference.")
        output_layout.addWidget(dac_0v_label, 3, 0)
        output_layout.addWidget(self.dac_bar, 3, 1)
        dac_4v_label = QLabel("4V")
        dac_4v_label.setToolTip("DAC maximum output reference.")
        output_layout.addWidget(dac_4v_label, 3, 2)
        
        layout.addWidget(self.output_group)
        
        control_group = QGroupBox("Per-Device Controls")
        control_layout = QGridLayout(control_group)

        dac_mode_label = QLabel("Mode:")
        dac_mode_label.setToolTip("Select passthrough source or manual REG0 source.")
        control_layout.addWidget(dac_mode_label, 0, 0)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Passthrough", "Manual (Register)"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_change)
        self.mode_combo.setToolTip("Control bit 0: 0=passthrough, 1=manual register source.")
        control_layout.addWidget(self.mode_combo, 0, 1)

        self.ramp_enable_cb = QCheckBox("Enable Hardware Ramp (0 -> 4095)")
        self.ramp_enable_cb.stateChanged.connect(self.on_ramp_enable)
        self.ramp_enable_cb.setToolTip("Control bit 4: enable on-FPGA DAC ramp generator in manual mode.")
        control_layout.addWidget(self.ramp_enable_cb, 1, 0, 1, 2)

        self.ramp_note_label = QLabel("Ramp rate follows prescaler/sample clock")
        self.ramp_note_label.setStyleSheet("color: gray;")
        self.ramp_note_label.setToolTip("Ramp increments one code per DAC sample tick from prescaler.")
        control_layout.addWidget(self.ramp_note_label, 2, 0, 1, 2)
        
        layout.addWidget(control_group)

        self.all_group = QGroupBox("All DAC Outputs")
        all_layout = QGridLayout(self.all_group)
        all_layout.addWidget(QLabel("DAC"), 0, 0)
        all_layout.addWidget(QLabel("Value"), 0, 1)
        all_layout.addWidget(QLabel("Slider"), 0, 2)
        all_layout.addWidget(QLabel("Est. Voltage"), 0, 3)
        all_layout.addWidget(QLabel("Passthrough"), 0, 4)
        all_layout.addWidget(QLabel("Ramp"), 0, 5)

        for i, addr in enumerate(self.addrs):
            row = i + 1
            name = QLabel(f"DAC {i} (0x{addr:08X})")
            spin = QSpinBox()
            spin.setRange(0, 4095)
            spin.setToolTip("Write DAC code to REG0 for this DAC.")
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 4095)
            slider.setToolTip("Write DAC code to REG0 for this DAC.")
            volt = QLabel("0.000 V")
            volt.setFont(QFont("Courier", 10))
            pass_cb = QCheckBox()
            pass_cb.setToolTip("Checked=passthrough mode, unchecked=manual mode.")
            ramp_cb = QCheckBox()
            ramp_cb.setToolTip("Enable hardware ramp bit for this DAC.")

            spin.valueChanged.connect(lambda value, a=addr: self.on_all_spin_changed(a, value))
            slider.valueChanged.connect(lambda value, a=addr: self.on_all_slider_changed(a, value))
            pass_cb.stateChanged.connect(lambda state, a=addr: self.on_all_passthrough_changed(a, state))
            ramp_cb.stateChanged.connect(lambda state, a=addr: self.on_all_ramp_changed(a, state))

            all_layout.addWidget(name, row, 0)
            all_layout.addWidget(spin, row, 1)
            all_layout.addWidget(slider, row, 2)
            all_layout.addWidget(volt, row, 3)
            all_layout.addWidget(pass_cb, row, 4)
            all_layout.addWidget(ramp_cb, row, 5)
            self.all_rows[addr] = {
                "spin": spin,
                "slider": slider,
                "volt": volt,
                "pass_cb": pass_cb,
                "ramp_cb": ramp_cb,
            }

        layout.addWidget(self.all_group)

        global_group = QGroupBox("Global Controls")
        global_layout = QGridLayout(global_group)

        global_note = QLabel(f"Global signals use DAC0 (0x{self.global_addr:08X})")
        global_note.setToolTip("Global clock/latch controls are shared and mapped through DAC0 control register.")
        global_layout.addWidget(global_note, 0, 0, 1, 2)

        self.en0_cb = QCheckBox("DAC 0 Clock Enable")
        self.en0_cb.stateChanged.connect(self.on_global_clock_change)
        self.en0_cb.setToolTip("Control bit 1: enable DAC clock output clk_0.")
        global_layout.addWidget(self.en0_cb, 1, 0, 1, 2)

        self.latch_oe_cb = QCheckBox("Latch Output Enable")
        self.latch_oe_cb.stateChanged.connect(self.on_global_latch_change)
        self.latch_oe_cb.setToolTip("Control bit 3: latch/output-enable control for DAC interface.")
        global_layout.addWidget(self.latch_oe_cb, 2, 0, 1, 2)

        global_prescaler_label = QLabel("Global Prescaler:")
        global_prescaler_label.setToolTip("Clock divider register for DAC sample clock generation.")
        global_layout.addWidget(global_prescaler_label, 3, 0)
        self.prescaler_spin = QSpinBox()
        self.prescaler_spin.setRange(0, 65535)
        self.prescaler_spin.valueChanged.connect(self.on_global_prescaler)
        self.prescaler_spin.setToolTip("Prescaler used for DAC clock/ramp tick: 100 MHz / (2*(pre+1)).")
        global_layout.addWidget(self.prescaler_spin, 3, 1)

        self.freq_label = QLabel("-- MHz")
        self.freq_label.setToolTip("Computed DAC sample clock from prescaler.")
        global_clock_label = QLabel("Global Clock Freq:")
        global_clock_label.setToolTip("Estimated DAC clock frequency.")
        global_layout.addWidget(global_clock_label, 4, 0)
        global_layout.addWidget(self.freq_label, 4, 1)

        layout.addWidget(global_group)

        raw_group = QGroupBox("Raw AXI Registers")
        raw_layout = QVBoxLayout(raw_group)
        self.raw_selected_label = QLabel("Selected: R0=0x00000000 R1=0x00000000 R2=0x00000000 R3=0x00000000")
        self.raw_selected_label.setFont(QFont("Courier", 10))
        self.raw_selected_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.raw_selected_label.setToolTip("Raw register readback for the selected DAC AXI device.")
        raw_layout.addWidget(self.raw_selected_label)

        self.raw_selected_bits_label = QLabel("Selected bits: mode=PASS clk0=OFF clk1=OFF latch=OFF ramp=OFF value=0 prescaler=0")
        self.raw_selected_bits_label.setFont(QFont("Courier", 10))
        self.raw_selected_bits_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.raw_selected_bits_label.setToolTip("Decoded selected-DAC register fields based on AXI RTL bit assignments.")
        raw_layout.addWidget(self.raw_selected_bits_label)

        self.raw_global_label = QLabel("Global:   R0=0x00000000 R1=0x00000000 R2=0x00000000 R3=0x00000000")
        self.raw_global_label.setFont(QFont("Courier", 10))
        self.raw_global_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.raw_global_label.setToolTip("Raw register readback for DAC0 global control mapping.")
        raw_layout.addWidget(self.raw_global_label)

        self.raw_global_bits_label = QLabel("Global bits: mode=PASS clk0=OFF clk1=OFF latch=OFF ramp=OFF value=0 prescaler=0")
        self.raw_global_bits_label.setFont(QFont("Courier", 10))
        self.raw_global_bits_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.raw_global_bits_label.setToolTip("Decoded DAC0 register fields based on AXI RTL bit assignments.")
        raw_layout.addWidget(self.raw_global_bits_label)

        layout.addWidget(raw_group)

        self.single_mode_widgets = [self.output_group, control_group, raw_group]
        self.all_group.setVisible(False)
        layout.addStretch()

    def on_view_mode_changed(self, state):
        show_all = bool(state)
        self.select_dac_label.setVisible(not show_all)
        self.device_combo.setVisible(not show_all)
        self.all_group.setVisible(show_all)
        for widget in self.single_mode_widgets:
            widget.setVisible(not show_all)

    def on_device_changed(self, index):
        self.current_addr = self.device_combo.itemData(index)
        self.output_group.setTitle(f"DAC Output (0x{self.current_addr:08X})")

        self.ramp_enable_cb.blockSignals(True)
        self.ramp_enable_cb.setChecked(self.ramp_enabled.get(self.current_addr, False))
        self.ramp_enable_cb.blockSignals(False)

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
            ctrl = self.current_ctrl & ~self.MASK_MODE
            if index == 1:
                ctrl |= self.MASK_MODE
            else:
                ctrl &= ~self.MASK_MODE
            self.client.write_reg(self.current_addr, 1, ctrl)
            self.current_ctrl = ctrl
            if self.current_addr == self.global_addr:
                self.global_ctrl = ctrl

    def on_all_spin_changed(self, addr: int, value: int):
        if not self.client.connected:
            return
        row = self.all_rows.get(addr)
        if not row:
            return
        row["slider"].blockSignals(True)
        row["slider"].setValue(value)
        row["slider"].blockSignals(False)
        row["volt"].setText(f"{(value / 4095.0) * 4.0:.3f} V")
        self.client.write_reg(addr, 0, value)

    def on_all_slider_changed(self, addr: int, value: int):
        if not self.client.connected:
            return
        row = self.all_rows.get(addr)
        if not row:
            return
        row["spin"].blockSignals(True)
        row["spin"].setValue(value)
        row["spin"].blockSignals(False)
        row["volt"].setText(f"{(value / 4095.0) * 4.0:.3f} V")
        self.client.write_reg(addr, 0, value)

    def on_all_passthrough_changed(self, addr: int, state: int):
        if not self.client.connected:
            return
        row = self.all_rows.get(addr)
        if not row:
            return

        dev_data = self.last_data.get(str(addr), {}) if isinstance(self.last_data, dict) else {}
        ctrl = _reg_to_int(dev_data.get("1", 0))
        is_passthrough = bool(state)

        if is_passthrough:
            ctrl &= ~self.MASK_MODE
            ctrl &= ~self.MASK_HW_RAMP
        else:
            ctrl |= self.MASK_MODE

        self.client.write_reg(addr, 1, ctrl)

        row["ramp_cb"].setEnabled(not is_passthrough)
        if is_passthrough:
            row["ramp_cb"].blockSignals(True)
            row["ramp_cb"].setChecked(False)
            row["ramp_cb"].blockSignals(False)

        if addr == self.current_addr:
            self.current_ctrl = ctrl
        if addr == self.global_addr:
            self.global_ctrl = ctrl

    def on_all_ramp_changed(self, addr: int, state: int):
        if not self.client.connected:
            return
        row = self.all_rows.get(addr)
        if not row:
            return

        dev_data = self.last_data.get(str(addr), {}) if isinstance(self.last_data, dict) else {}
        ctrl = _reg_to_int(dev_data.get("1", 0))

        if state:
            ctrl |= self.MASK_MODE
            ctrl |= self.MASK_HW_RAMP
            row["pass_cb"].blockSignals(True)
            row["pass_cb"].setChecked(False)
            row["pass_cb"].blockSignals(False)
            row["ramp_cb"].setEnabled(True)
        else:
            ctrl &= ~self.MASK_HW_RAMP

        self.client.write_reg(addr, 1, ctrl)

        if addr == self.current_addr:
            self.current_ctrl = ctrl
        if addr == self.global_addr:
            self.global_ctrl = ctrl

    def on_global_clock_change(self, state):
        if self.client.connected:
            ctrl = self.global_ctrl
            if state:
                ctrl |= self.MASK_EN0
            else:
                ctrl &= ~self.MASK_EN0
            self.client.write_reg(self.global_addr, 1, ctrl)
            self.global_ctrl = ctrl

    def on_global_latch_change(self, state):
        if self.client.connected:
            ctrl = self.global_ctrl
            if state:
                ctrl |= self.MASK_LATCH
            else:
                ctrl &= ~self.MASK_LATCH
            self.client.write_reg(self.global_addr, 1, ctrl)
            self.global_ctrl = ctrl

    def on_global_prescaler(self, value):
        if self.client.connected:
            self.client.write_reg(self.global_addr, 2, value)
            self.global_pre = value

    def on_ramp_enable(self, state):
        if not self.client.connected:
            return

        ctrl = self.current_ctrl
        if state:
            ctrl |= self.MASK_MODE
            ctrl |= self.MASK_HW_RAMP
        else:
            ctrl &= ~self.MASK_HW_RAMP

        self.client.write_reg(self.current_addr, 1, ctrl)
        self.current_ctrl = ctrl
        if self.current_addr == self.global_addr:
            self.global_ctrl = ctrl

        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(1 if (ctrl & self.MASK_MODE) else 0)
        self.mode_combo.blockSignals(False)
        self.ramp_enabled[self.current_addr] = bool(ctrl & self.MASK_HW_RAMP)
            
    def update_from_data(self, data: Dict):
        self.last_data = data

        for addr in self.addrs:
            dev_data = data.get(str(addr), {})
            if dev_data:
                ctrl = int(dev_data.get("1", 0))
                self.ramp_enabled[addr] = bool(ctrl & self.MASK_HW_RAMP)
                value = int(dev_data.get("0", 0)) & 0x0FFF
                row = self.all_rows.get(addr)
                if row:
                    row["spin"].blockSignals(True)
                    row["spin"].setValue(value)
                    row["spin"].blockSignals(False)
                    row["slider"].blockSignals(True)
                    row["slider"].setValue(value)
                    row["slider"].blockSignals(False)
                    row["volt"].setText(f"{(value / 4095.0) * 4.0:.3f} V")
                    is_passthrough = not bool(ctrl & self.MASK_MODE)
                    has_ramp = bool(ctrl & self.MASK_HW_RAMP)
                    row["pass_cb"].blockSignals(True)
                    row["pass_cb"].setChecked(is_passthrough)
                    row["pass_cb"].blockSignals(False)
                    row["ramp_cb"].setEnabled(not is_passthrough)
                    row["ramp_cb"].blockSignals(True)
                    row["ramp_cb"].setChecked(has_ramp)
                    row["ramp_cb"].blockSignals(False)

        dac_data = data.get(str(self.current_addr), {})
        if not dac_data:
            return

        self.raw_selected_label.setText(f"Selected: {format_raw_regs(dac_data)}")
        self.raw_selected_bits_label.setText(f"Selected bits: {format_dac_bits(dac_data)}")

        global_data = data.get(str(self.global_addr), {})
        if global_data:
            self.global_ctrl = int(global_data.get("1", 0))
            self.global_pre = int(global_data.get("2", 0))
            self.raw_global_label.setText(f"Global:   {format_raw_regs(global_data)}")
            self.raw_global_bits_label.setText(f"Global bits: {format_dac_bits(global_data)}")
            
        val = int(dac_data.get("0", 0)) & 0x0FFF
        self.current_ctrl = int(dac_data.get("1", 0))
        
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
        self.en0_cb.setChecked(bool(self.global_ctrl & 0x02))
        self.en0_cb.blockSignals(False)

        self.latch_oe_cb.blockSignals(True)
        self.latch_oe_cb.setChecked(bool(self.global_ctrl & 0x08))
        self.latch_oe_cb.blockSignals(False)

        self.ramp_enable_cb.blockSignals(True)
        self.ramp_enable_cb.setChecked(bool(self.current_ctrl & self.MASK_HW_RAMP))
        self.ramp_enable_cb.blockSignals(False)
        
        self.prescaler_spin.blockSignals(True)
        self.prescaler_spin.setValue(self.global_pre)
        self.prescaler_spin.blockSignals(False)
        
        freq_mhz = 100.0 / (2.0 * (self.global_pre + 1))
        self.freq_label.setText(f"{freq_mhz:.2f} MHz")


# =============================================================================
# Calibration / Test Tab
# =============================================================================

class CalibrationTab(QWidget):
    """Ramp a DAC while recording the connected ADC response in real time."""

    MASK_MODE = 0x01
    MASK_EN0 = 0x02
    MASK_LATCH = 0x08
    MASK_HW_RAMP = 0x10

    def __init__(
        self,
        client: ZynqClient,
        adc_addrs: list[int],
        dac_addrs: list[int],
        spgd_addr: int,
        pause_polling=None,
        resume_polling=None,
        refresh_now=None,
    ):
        super().__init__()
        self.client = client
        self.adc_addrs = adc_addrs
        self.dac_addrs = dac_addrs
        self.spgd_addr = spgd_addr
        self.pause_polling = pause_polling
        self.resume_polling = resume_polling
        self.refresh_now = refresh_now

        self.is_running = False
        self.samples = []
        self.saved_state: Dict[str, Dict[str, int]] = {}

        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self.capture_sample)

        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_xlabel("DAC Code")
        self.axes.set_ylabel("ADC Voltage (V)")
        self.axes.set_xlim(0, 4095)
        self.axes.set_ylim(-10.5, 10.5)
        self.axes.grid(True, alpha=0.25)
        self.axes.axhline(0.0, color="#888888", linewidth=0.8)
        (self.plot_line,) = self.axes.plot([], [], color="#1f77b4", linewidth=1.5)

        self.init_ui()
        self.update_target_labels()
        self.update_rate_labels()

    def init_ui(self):
        layout = QVBoxLayout(self)

        setup_group = QGroupBox("Calibration Setup")
        setup_layout = QGridLayout(setup_group)

        dac_label = QLabel("DAC Number:")
        dac_label.setToolTip("Select the DAC output being looped back into the ADC.")
        setup_layout.addWidget(dac_label, 0, 0)
        self.dac_index_spin = QSpinBox()
        self.dac_index_spin.setRange(0, max(0, len(self.dac_addrs) - 1))
        self.dac_index_spin.valueChanged.connect(self.on_target_changed)
        setup_layout.addWidget(self.dac_index_spin, 0, 1)
        self.dac_addr_label = QLabel("n/a")
        self.dac_addr_label.setToolTip("Resolved DAC base address for the selected number.")
        setup_layout.addWidget(self.dac_addr_label, 0, 2)

        adc_label = QLabel("ADC Number:")
        adc_label.setToolTip("Select the ADC channel connected to the test DAC.")
        setup_layout.addWidget(adc_label, 1, 0)
        self.adc_index_spin = QSpinBox()
        self.adc_index_spin.setRange(0, max(0, len(self.adc_addrs) - 1))
        self.adc_index_spin.valueChanged.connect(self.on_target_changed)
        setup_layout.addWidget(self.adc_index_spin, 1, 1)
        self.adc_addr_label = QLabel("n/a")
        self.adc_addr_label.setToolTip("Resolved ADC base address for the selected number.")
        setup_layout.addWidget(self.adc_addr_label, 1, 2)

        ramp_rate_label = QLabel("Ramp Rate (Hz):")
        ramp_rate_label.setToolTip("Desired DAC ramp clock. The FPGA ramp advances one code per clock tick.")
        setup_layout.addWidget(ramp_rate_label, 2, 0)
        self.ramp_rate_spin = QDoubleSpinBox()
        self.ramp_rate_spin.setDecimals(3)
        self.ramp_rate_spin.setRange(0.001, 50000000.0)
        self.ramp_rate_spin.setValue(1000.0)
        self.ramp_rate_spin.valueChanged.connect(self.update_rate_labels)
        setup_layout.addWidget(self.ramp_rate_spin, 2, 1)
        self.actual_rate_label = QLabel("-- Hz")
        self.actual_rate_label.setToolTip("Actual clock rate after prescaler quantization.")
        setup_layout.addWidget(self.actual_rate_label, 2, 2)

        capture_rate_label = QLabel("Plot Rate (Hz):")
        capture_rate_label.setToolTip("How often the GUI samples the ADC and redraws the plot.")
        setup_layout.addWidget(capture_rate_label, 3, 0)
        self.capture_rate_spin = QSpinBox()
        self.capture_rate_spin.setRange(1, 1000)
        self.capture_rate_spin.setValue(50)
        self.capture_rate_spin.valueChanged.connect(self.on_capture_rate_changed)
        setup_layout.addWidget(self.capture_rate_spin, 3, 1)
        self.sweep_time_label = QLabel("-- s")
        self.sweep_time_label.setToolTip("Estimated 0-to-full-scale sweep duration at the selected ramp rate.")
        setup_layout.addWidget(self.sweep_time_label, 3, 2)

        self.force_passthrough_cb = QCheckBox("Force SPGD passthrough while running")
        self.force_passthrough_cb.setChecked(True)
        self.force_passthrough_cb.setToolTip("Sets SPGD control bit 1 during the test so the DAC path is bypassed.")
        setup_layout.addWidget(self.force_passthrough_cb, 4, 0, 1, 3)

        self.auto_stop_cb = QCheckBox("Auto-stop when ramp reaches full scale")
        self.auto_stop_cb.setChecked(True)
        self.auto_stop_cb.setToolTip("Stops capture after the ramp reaches the top of its range.")
        setup_layout.addWidget(self.auto_stop_cb, 5, 0, 1, 3)

        button_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Calibration")
        self.start_btn.clicked.connect(self.start_test)
        button_row.addWidget(self.start_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_test)
        self.stop_btn.setEnabled(False)
        button_row.addWidget(self.stop_btn)
        self.clear_btn = QPushButton("Clear Plot")
        self.clear_btn.clicked.connect(self.clear_plot)
        button_row.addWidget(self.clear_btn)
        button_row.addStretch()
        setup_layout.addLayout(button_row, 6, 0, 1, 3)

        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet("color: gray;")
        self.status_label.setToolTip("Current calibration state.")
        setup_layout.addWidget(self.status_label, 7, 0, 1, 3)

        self.sample_label = QLabel("Samples: 0")
        self.sample_label.setToolTip("Number of captured ADC points.")
        setup_layout.addWidget(self.sample_label, 8, 0, 1, 3)

        layout.addWidget(setup_group)

        plot_group = QGroupBox("Live Transfer Plot")
        plot_layout = QVBoxLayout(plot_group)
        plot_layout.addWidget(self.canvas)
        layout.addWidget(plot_group)

        layout.addStretch()

    def current_dac_addr(self) -> int:
        if not self.dac_addrs:
            return 0
        return self.dac_addrs[min(self.dac_index_spin.value(), len(self.dac_addrs) - 1)]

    def current_adc_addr(self) -> int:
        if not self.adc_addrs:
            return 0
        return self.adc_addrs[min(self.adc_index_spin.value(), len(self.adc_addrs) - 1)]

    def on_target_changed(self, _):
        self.update_target_labels()
        if self.is_running:
            self.status_label.setText("Running with updated target selection")

    def update_target_labels(self):
        if self.dac_addrs:
            dac_index = min(self.dac_index_spin.value(), len(self.dac_addrs) - 1)
            self.dac_addr_label.setText(f"0x{self.dac_addrs[dac_index]:08X}")
        else:
            self.dac_addr_label.setText("n/a")

        if self.adc_addrs:
            adc_index = min(self.adc_index_spin.value(), len(self.adc_addrs) - 1)
            self.adc_addr_label.setText(f"0x{self.adc_addrs[adc_index]:08X}")
        else:
            self.adc_addr_label.setText("n/a")

        self.axes.set_title(
            f"DAC {self.dac_index_spin.value()} -> ADC {self.adc_index_spin.value()}"
        )
        self.canvas.draw_idle()

    def on_capture_rate_changed(self, value):
        if self.is_running:
            self.capture_timer.setInterval(max(1, 1000 // max(1, value)))

    def _selected_addresses(self) -> list[int]:
        addrs = [self.spgd_addr]
        dac_addr = self.current_dac_addr()
        adc_addr = self.current_adc_addr()
        if dac_addr not in addrs:
            addrs.append(dac_addr)
        if adc_addr not in addrs:
            addrs.append(adc_addr)
        global_dac_addr = self.dac_addrs[0] if self.dac_addrs else 0
        if global_dac_addr not in addrs:
            addrs.append(global_dac_addr)
        return addrs

    @staticmethod
    def _signed_adc_value(raw_value: int) -> int:
        value = raw_value & 0xFFFF
        if value >= 0x8000:
            value -= 0x10000
        return value

    @staticmethod
    def _adc_voltage(raw_value: int) -> float:
        return (CalibrationTab._signed_adc_value(raw_value) / 32768.0) * 10.0

    @staticmethod
    def _prescaler_from_rate(rate_hz: float) -> int:
        if rate_hz <= 0.0:
            return 0
        prescaler = int(round((50000000.0 / rate_hz) - 1.0))
        return max(0, min(65535, prescaler))

    @staticmethod
    def _rate_from_prescaler(prescaler: int) -> float:
        return 100000000.0 / (2.0 * (prescaler + 1))

    def update_rate_labels(self):
        requested_rate = float(self.ramp_rate_spin.value())
        prescaler = self._prescaler_from_rate(requested_rate)
        actual_rate = self._rate_from_prescaler(prescaler)
        sweep_time = 4096.0 / actual_rate if actual_rate > 0.0 else 0.0
        self.actual_rate_label.setText(f"{actual_rate:,.3f} Hz")
        self.sweep_time_label.setText(f"{sweep_time:.3f} s")

    def clear_plot(self):
        self.samples = []
        self.plot_line.set_data([], [])
        self.sample_label.setText("Samples: 0")
        self.canvas.draw_idle()

    def _set_running_ui(self, running: bool):
        self.is_running = running
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.dac_index_spin.setEnabled(not running)
        self.adc_index_spin.setEnabled(not running)
        self.ramp_rate_spin.setEnabled(not running)
        self.force_passthrough_cb.setEnabled(not running)
        self.auto_stop_cb.setEnabled(not running)

    def start_test(self):
        if not self.client.connected:
            QMessageBox.warning(self, "Calibration", "Connect to zynq_server before starting the test.")
            return

        if not self.dac_addrs or not self.adc_addrs:
            QMessageBox.warning(self, "Calibration", "Need at least one DAC and one ADC configured.")
            return

        self.clear_plot()

        read_addrs = self._selected_addresses()
        resp = self.client.read_all(read_addrs)
        if resp is None or resp.get("status") != "ok":
            QMessageBox.warning(self, "Calibration", "Failed to read initial device state.")
            return

        data = resp.get("data", {})
        selected_dac_addr = self.current_dac_addr()
        global_dac_addr = self.dac_addrs[0]
        adc_addr = self.current_adc_addr()

        self.saved_state = {
            "spgd": {
                "ctrl": int(data.get(str(self.spgd_addr), {}).get("0", 0)),
            },
            "selected_dac": {
                "value": int(data.get(str(selected_dac_addr), {}).get("0", 0)) & 0x0FFF,
                "ctrl": int(data.get(str(selected_dac_addr), {}).get("1", 0)),
                "pre": int(data.get(str(selected_dac_addr), {}).get("2", 0)),
            },
            "global_dac": {
                "value": int(data.get(str(global_dac_addr), {}).get("0", 0)) & 0x0FFF,
                "ctrl": int(data.get(str(global_dac_addr), {}).get("1", 0)),
                "pre": int(data.get(str(global_dac_addr), {}).get("2", 0)),
            },
            "adc": {
                "ctrl": int(data.get(str(adc_addr), {}).get("1", 0)),
                "pre": int(data.get(str(adc_addr), {}).get("2", 0)),
            },
        }

        prescaler = self._prescaler_from_rate(float(self.ramp_rate_spin.value()))
        actual_rate = self._rate_from_prescaler(prescaler)
        self.update_rate_labels()

        if self.pause_polling:
            self.pause_polling()

        if self.force_passthrough_cb.isChecked():
            spgd_ctrl = self.saved_state["spgd"]["ctrl"] | self.MASK_EN0
            if not self.client.write_reg(self.spgd_addr, 0, spgd_ctrl):
                self._abort_start("Failed to enable SPGD passthrough.")
                return

        if not self.client.write_reg(global_dac_addr, 2, prescaler):
            self._abort_start("Failed to program DAC ramp prescaler.")
            return

        if selected_dac_addr != global_dac_addr:
            if not self.client.write_reg(selected_dac_addr, 2, prescaler):
                self._abort_start("Failed to program target DAC prescaler.")
                return

        ramp_ctrl = self.saved_state["selected_dac"]["ctrl"] | self.MASK_MODE | self.MASK_HW_RAMP
        if not self.client.write_reg(selected_dac_addr, 0, 0):
            self._abort_start("Failed to zero the DAC before ramping.")
            return
        if not self.client.write_reg(selected_dac_addr, 1, ramp_ctrl):
            self._abort_start("Failed to enable the hardware ramp.")
            return

        self.capture_timer.start(max(1, 1000 // max(1, self.capture_rate_spin.value())))
        self._set_running_ui(True)
        self.status_label.setText(
            f"Running: DAC {self.dac_index_spin.value()} -> ADC {self.adc_index_spin.value()} at {actual_rate:,.1f} Hz"
        )
        self.status_label.setStyleSheet("color: green;")

    def _abort_start(self, message: str):
        if self.resume_polling:
            self.resume_polling()
        self.restore_state()
        self._set_running_ui(False)
        self.status_label.setText("Idle")
        self.status_label.setStyleSheet("color: gray;")
        QMessageBox.warning(self, "Calibration", message)

    def stop_test(self):
        if not self.is_running and not self.saved_state:
            return

        self.capture_timer.stop()
        self.restore_state()
        self._set_running_ui(False)

        if self.resume_polling:
            self.resume_polling()
        if self.refresh_now:
            self.refresh_now()

        self.status_label.setText("Idle")
        self.status_label.setStyleSheet("color: gray;")

    def restore_state(self):
        if not self.saved_state:
            return

        selected_dac_addr = self.current_dac_addr()
        global_dac_addr = self.dac_addrs[0] if self.dac_addrs else 0

        selected_dac = self.saved_state.get("selected_dac", {})
        global_dac = self.saved_state.get("global_dac", {})
        spgd = self.saved_state.get("spgd", {})

        if selected_dac:
            self.client.write_reg(selected_dac_addr, 1, int(selected_dac.get("ctrl", 0)))
            self.client.write_reg(selected_dac_addr, 0, int(selected_dac.get("value", 0)))
            self.client.write_reg(selected_dac_addr, 2, int(selected_dac.get("pre", 0)))

        if global_dac and global_dac_addr != selected_dac_addr:
            self.client.write_reg(global_dac_addr, 1, int(global_dac.get("ctrl", 0)))
            self.client.write_reg(global_dac_addr, 0, int(global_dac.get("value", 0)))
            self.client.write_reg(global_dac_addr, 2, int(global_dac.get("pre", 0)))

        if spgd:
            self.client.write_reg(self.spgd_addr, 0, int(spgd.get("ctrl", 0)))

        self.saved_state = {}

    def capture_sample(self):
        if not self.is_running:
            return

        read_addrs = self._selected_addresses()
        resp = self.client.read_all(read_addrs)
        if resp is None or resp.get("status") != "ok":
            self.status_label.setText("Connection lost during calibration")
            self.status_label.setStyleSheet("color: red;")
            self.stop_test()
            return

        data = resp.get("data", {})
        selected_dac_addr = self.current_dac_addr()
        adc_addr = self.current_adc_addr()

        dac_data = data.get(str(selected_dac_addr), {})
        adc_data = data.get(str(adc_addr), {})
        if not dac_data or not adc_data:
            return

        dac_code = int(dac_data.get("0", 0)) & 0x0FFF
        adc_raw = int(adc_data.get("0", 0))
        adc_code = self._signed_adc_value(adc_raw)
        adc_voltage = self._adc_voltage(adc_raw)

        self.samples.append((dac_code, adc_code, adc_voltage))
        self.sample_label.setText(f"Samples: {len(self.samples)} | DAC: {dac_code:04d} | ADC: {adc_code:+06d} | {adc_voltage:+7.3f} V")

        x_vals = [sample[0] for sample in self.samples]
        y_vals = [sample[2] for sample in self.samples]
        self.plot_line.set_data(x_vals, y_vals)
        self.canvas.draw_idle()

        if self.auto_stop_cb.isChecked() and dac_code >= 4095:
            self.stop_test()


# =============================================================================
# Main Window
# =============================================================================

class MainWindow(QMainWindow):
    def __init__(self, host: str = "localhost", port: int = 5000):
        super().__init__()
        self.client = ZynqClient(host, port)
        self.polling_enabled = True
        self.poll_interval_ms = 100
        
        self.setWindowTitle("Zynq Dynamic AXI Controller")
        self.setMinimumSize(900, 800)
        
        self.init_ui()
        
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.poll_data)
        
        self.reconnect()
    
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        conn_layout = QHBoxLayout()
        host_label = QLabel("Host:")
        host_label.setToolTip("IP address or hostname of zynq_server.")
        conn_layout.addWidget(host_label)
        self.host_edit = QLineEdit(self.client.host)
        self.host_edit.setFixedWidth(150)
        self.host_edit.setToolTip("Target server host. Example: 192.168.1.85")
        conn_layout.addWidget(self.host_edit)
        
        port_label = QLabel("Port:")
        port_label.setToolTip("TCP port used by zynq_server (default 5000).")
        conn_layout.addWidget(port_label)
        self.port_edit = QLineEdit(str(self.client.port))
        self.port_edit.setFixedWidth(60)
        self.port_edit.setToolTip("Server TCP port number.")
        conn_layout.addWidget(self.port_edit)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.reconnect)
        self.connect_btn.setToolTip("Connect/reconnect to server and start polling.")
        conn_layout.addWidget(self.connect_btn)
        
        self.status_label = QLabel("Disconnected")
        self.status_label.setStyleSheet("color: red;")
        self.status_label.setToolTip("Current client connection state.")
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

        self.cal_tab = CalibrationTab(
            self.client,
            ADC_ADDRS,
            DAC_ADDRS,
            SPGD_ADDR,
            pause_polling=self.pause_polling,
            resume_polling=self.resume_polling,
            refresh_now=self.poll_data,
        )
        self.tabs.addTab(self.cal_tab, "Calibrate / Test")
            
        layout.addWidget(self.tabs)
        
        bottom_layout = QHBoxLayout()
        poll_rate_label = QLabel("Poll Rate:")
        poll_rate_label.setToolTip("How often the GUI reads all registers from the server.")
        bottom_layout.addWidget(poll_rate_label)
        self.poll_rate_spin = QSpinBox()
        self.poll_rate_spin.setRange(1, 100)
        self.poll_rate_spin.setValue(10)
        self.poll_rate_spin.setSuffix(" Hz")
        self.poll_rate_spin.valueChanged.connect(self.on_poll_rate_change)
        self.poll_rate_spin.setToolTip("Readback polling frequency in Hz. Higher values increase network traffic.")
        bottom_layout.addWidget(self.poll_rate_spin)
        bottom_layout.addStretch()
        version_label = QLabel(f"Version {VERSION}")
        version_label.setStyleSheet("color: gray;")
        bottom_layout.addWidget(version_label)
        layout.addLayout(bottom_layout)

    def _poll_interval_for_rate(self, rate_hz: int) -> int:
        return max(1, 1000 // max(1, rate_hz))

    def pause_polling(self):
        self.polling_enabled = False
        self.poll_timer.stop()

    def resume_polling(self):
        self.polling_enabled = True
        if self.client.connected:
            self.poll_timer.start(self.poll_interval_ms)
    
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
            self.polling_enabled = True
            self.poll_interval_ms = self._poll_interval_for_rate(self.poll_rate_spin.value())
            self.poll_timer.start(self.poll_interval_ms)
        else:
            self.status_label.setText("Connection Failed")
            self.status_label.setStyleSheet("color: red;")
    
    def on_poll_rate_change(self, value):
        self.poll_interval_ms = self._poll_interval_for_rate(value)
        if self.poll_timer.isActive() and self.polling_enabled:
            self.poll_timer.setInterval(self.poll_interval_ms)
    
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
