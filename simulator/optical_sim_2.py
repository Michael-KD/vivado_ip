#!/usr/bin/env python3
"""
optical_sim.py - Phased Array Power Beaming Simulator

Simulates N-channel coherent beam combining for long-distance power beaming.
Each channel has tip (X), tilt (Y), and phase control to correct for
atmospheric turbulence and align all beams at the receiver.

Features:
- Adjustable channel count (1-8)
- Configurable optimal DAC values
- Atmospheric turbulence simulation
- Realism mode with higher-order Zernike aberrations
- 2D/3D visualization toggle

Run: python optical_sim.py
"""

import sys
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QSlider, QGroupBox, QPushButton,
    QProgressBar, QTabWidget, QDoubleSpinBox, QSpinBox, QScrollArea,
    QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import matplotlib
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Circle
from mpl_toolkits.mplot3d import Axes3D


def zernike_radial(n, m, rho):
    """Compute radial Zernike polynomial R_n^m(rho)."""
    m_abs = abs(m)
    result = np.zeros_like(rho)
    for k in range((n - m_abs) // 2 + 1):
        coef = ((-1)**k * np.math.factorial(n - k) /
                (np.math.factorial(k) *
                 np.math.factorial((n + m_abs) // 2 - k) *
                 np.math.factorial((n - m_abs) // 2 - k)))
        result += coef * rho**(n - 2*k)
    return result


def zernike(n, m, rho, theta):
    """Compute Zernike polynomial Z_n^m(rho, theta)."""
    R = zernike_radial(n, m, rho)
    if m >= 0:
        return R * np.cos(m * theta)
    else:
        return R * np.sin(abs(m) * theta)


class OpticalSimulator:
    """Physics engine for phased array beam combining simulation."""
    
    # Zernike modes: (n, m, name)
    ZERNIKE_MODES = [
        (2, -2, 'Oblique Astigmatism'),
        (2, 2, 'Vertical Astigmatism'),
        (3, -1, 'Vertical Coma'),
        (3, 1, 'Horizontal Coma'),
        (3, -3, 'Oblique Trefoil'),
        (3, 3, 'Horizontal Trefoil'),
        (4, 0, 'Spherical'),
    ]
    
    def __init__(self, n_channels=4, grid_size=128):
        self.grid_size = grid_size
        
        # Configurable optimal values (what "perfect" looks like)
        self.optimal_tip = 2048
        self.optimal_tilt = 2048
        self.optimal_phase = 2048
        
        # Physical parameters
        self.beam_waist = 0.15
        self.fiber_waist = 0.25
        self.tip_tilt_range = 0.5
        
        # Realism mode
        self.realism_mode = False
        self.zernike_strength = 0.3  # Strength of higher-order aberrations
        
        # Create coordinate grids
        x = np.linspace(-1, 1, grid_size)
        y = np.linspace(-1, 1, grid_size)
        self.X, self.Y = np.meshgrid(x, y)
        
        # Polar coordinates for Zernike polynomials
        self.R = np.sqrt(self.X**2 + self.Y**2)
        self.Theta = np.arctan2(self.Y, self.X)
        
        # Precompute Zernike basis functions for each beam position
        self._precompute_zernike_cache()
        
        # Initialize with channel count
        self.set_channel_count(n_channels)
    
    def _precompute_zernike_cache(self):
        """Precompute Zernike polynomials on the grid."""
        self.zernike_cache = {}
        for n, m, _ in self.ZERNIKE_MODES:
            # Compute on unit disk
            Z = np.zeros_like(self.R)
            mask = self.R <= 1.0
            Z[mask] = zernike(n, m, self.R[mask], self.Theta[mask])
            self.zernike_cache[(n, m)] = Z
    
    def set_channel_count(self, n_channels):
        """Change the number of channels and reinitialize."""
        self.n_channels = n_channels
        
        # DAC values: [tip, tilt, phase] for each channel
        self.dac_values = np.full((n_channels, 3), 
                                   [self.optimal_tip, self.optimal_tilt, self.optimal_phase], 
                                   dtype=float)
        
        # Turbulence offsets: [tip, tilt, phase] for basic mode
        self.turbulence = np.zeros((n_channels, 3))
        
        # Higher-order aberration coefficients for realism mode
        # Shape: (n_channels, len(ZERNIKE_MODES))
        self.zernike_coeffs = np.zeros((n_channels, len(self.ZERNIKE_MODES)))
        
        # Recalibrate
        self._calibrate_max()
    
    def set_optimal_values(self, tip, tilt, phase):
        """Set the optimal DAC values."""
        self.optimal_tip = tip
        self.optimal_tilt = tilt
        self.optimal_phase = phase
        self._calibrate_max()
    
    def dac_to_position(self, dac_val):
        """Convert 12-bit DAC value to position offset."""
        return ((dac_val - 2048) / 2048.0) * self.tip_tilt_range
    
    def dac_to_phase(self, dac_val):
        """Convert 12-bit DAC value to phase (0 to 2π)."""
        return (dac_val / 4095.0) * 2 * np.pi
    
    def position_to_dac(self, pos):
        """Convert position to DAC value."""
        dac = int((pos / self.tip_tilt_range) * 2048 + 2048)
        return max(0, min(4095, dac))
    
    def phase_to_dac(self, phase):
        """Convert phase to DAC value."""
        return int((phase / (2 * np.pi)) * 4095) % 4096
    
    def _calibrate_max(self):
        """Compute maximum coupling for normalization."""
        saved_dac = self.dac_values.copy()
        saved_turb = self.turbulence.copy()
        saved_zernike = self.zernike_coeffs.copy()
        saved_realism = self.realism_mode
        
        # Set all to optimal, no turbulence, no aberrations
        for i in range(self.n_channels):
            self.dac_values[i] = [self.optimal_tip, self.optimal_tilt, self.optimal_phase]
        self.turbulence = np.zeros((self.n_channels, 3))
        self.zernike_coeffs = np.zeros((self.n_channels, len(self.ZERNIKE_MODES)))
        self.realism_mode = False
        
        E = self.compute_field()
        intensity = np.abs(E)**2
        receiver = np.exp(-(self.X**2 + self.Y**2) / (2 * self.fiber_waist**2))
        self.max_coupling = np.sum(intensity * receiver) / np.sum(receiver)
        
        self.dac_values = saved_dac
        self.turbulence = saved_turb
        self.zernike_coeffs = saved_zernike
        self.realism_mode = saved_realism
    
    def compute_field(self):
        """Compute the combined electric field at the receiver plane."""
        E_total = np.zeros((self.grid_size, self.grid_size), dtype=complex)
        
        for i in range(self.n_channels):
            tip_dac = self.dac_values[i, 0]
            tilt_dac = self.dac_values[i, 1]
            phase_dac = self.dac_values[i, 2]
            
            tip = self.dac_to_position(tip_dac) + self.turbulence[i, 0]
            tilt = self.dac_to_position(tilt_dac) + self.turbulence[i, 1]
            phase = self.dac_to_phase(phase_dac) + self.turbulence[i, 2]
            
            # Gaussian amplitude centered at (tip, tilt)
            r2 = (self.X - tip)**2 + (self.Y - tilt)**2
            amplitude = np.exp(-r2 / (2 * self.beam_waist**2))
            
            # Add higher-order aberrations in realism mode
            if self.realism_mode:
                # Create local polar coordinates centered on beam
                local_r = np.sqrt((self.X - tip)**2 + (self.Y - tilt)**2)
                local_theta = np.arctan2(self.Y - tilt, self.X - tip)
                
                # Normalize radius to beam waist for Zernike evaluation
                rho = local_r / (3 * self.beam_waist)  # Scale factor
                rho_clipped = np.clip(rho, 0, 1)
                
                # Accumulate phase aberrations from Zernike coefficients
                aberration_phase = np.zeros_like(self.X)
                for j, (n, m, _) in enumerate(self.ZERNIKE_MODES):
                    if self.zernike_coeffs[i, j] != 0:
                        Z = zernike(n, m, rho_clipped, local_theta)
                        aberration_phase += self.zernike_coeffs[i, j] * Z
                
                phase = phase + aberration_phase
            
            E_total += amplitude * np.exp(1j * phase)
        
        return E_total
    
    def compute_intensity(self):
        """Compute intensity pattern."""
        E = self.compute_field()
        return np.abs(E)**2
    
    def compute_metric(self):
        """Compute the ADC reading - power at receiver."""
        E = self.compute_field()
        intensity = np.abs(E)**2
        receiver = np.exp(-(self.X**2 + self.Y**2) / (2 * self.fiber_waist**2))
        coupled_power = np.sum(intensity * receiver) / np.sum(receiver)
        
        normalized = coupled_power / self.max_coupling if self.max_coupling > 0 else 0
        normalized = np.clip(normalized, 0, 1)
        adc_reading = int(normalized * 65535)
        
        return adc_reading, normalized
    
    def randomize_turbulence(self, tip_tilt_std=0.2, phase_std=1.5):
        """Apply random atmospheric turbulence."""
        for i in range(self.n_channels):
            self.turbulence[i, 0] = np.random.normal(0, tip_tilt_std)
            self.turbulence[i, 1] = np.random.normal(0, tip_tilt_std)
            self.turbulence[i, 2] = np.random.uniform(0, 2 * np.pi)
        
        # Add higher-order aberrations in realism mode
        if self.realism_mode:
            for i in range(self.n_channels):
                for j in range(len(self.ZERNIKE_MODES)):
                    # Kolmogorov-like scaling: higher orders have less power
                    n, m, _ = self.ZERNIKE_MODES[j]
                    scale = self.zernike_strength / (n + 1)
                    self.zernike_coeffs[i, j] = np.random.normal(0, scale)
    
    def clear_turbulence(self):
        """Remove all turbulence."""
        self.turbulence = np.zeros((self.n_channels, 3))
        self.zernike_coeffs = np.zeros((self.n_channels, len(self.ZERNIKE_MODES)))
    
    def get_optimal_dac_values(self):
        """Calculate DAC values that perfectly correct turbulence (tip/tilt/phase only)."""
        optimal = np.zeros((self.n_channels, 3), dtype=int)
        
        # Target physical values (what optimal DAC produces with no turbulence)
        target_tip_pos = self.dac_to_position(self.optimal_tip)
        target_tilt_pos = self.dac_to_position(self.optimal_tilt)
        target_phase = self.dac_to_phase(self.optimal_phase)
        
        for i in range(self.n_channels):
            # Find DAC that produces target position after turbulence
            needed_tip_pos = target_tip_pos - self.turbulence[i, 0]
            needed_tilt_pos = target_tilt_pos - self.turbulence[i, 1]
            
            optimal[i, 0] = self.position_to_dac(needed_tip_pos)
            optimal[i, 1] = self.position_to_dac(needed_tilt_pos)
            
            # Phase correction
            needed_phase = target_phase - self.turbulence[i, 2]
            needed_phase = needed_phase % (2 * np.pi)
            optimal[i, 2] = self.phase_to_dac(needed_phase)
        
        return optimal


class IntensityCanvas(FigureCanvas):
    """Matplotlib canvas for displaying the intensity pattern (2D or 3D)."""
    
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 5))
        super().__init__(self.fig)
        
        self.is_3d = False
        self.receiver_radius = 0.25
        self.receiver_center = (0, 0)
        
        self._setup_2d()
    
    def _setup_2d(self):
        """Setup 2D heatmap view."""
        self.fig.clear()
        self.ax = self.fig.add_subplot(111)
        
        self.img = self.ax.imshow(np.zeros((128, 128)), cmap='hot', 
                                   origin='lower', extent=[-1, 1, -1, 1])
        self.ax.set_xlabel('X Position')
        self.ax.set_ylabel('Y Position')
        self.ax.set_title('Receiver Plane Intensity')
        
        self.circle = Circle(self.receiver_center, self.receiver_radius, 
                             fill=False, color='cyan', linestyle='--', linewidth=2)
        self.ax.add_patch(self.circle)
        
        self.colorbar = self.fig.colorbar(self.img, ax=self.ax, shrink=0.8)
        self.fig.tight_layout()
        self.draw()
    
    def _setup_3d(self):
        """Setup 3D surface view."""
        self.fig.clear()
        self.ax = self.fig.add_subplot(111, projection='3d')
        
        # Create mesh for 3D plot
        self.grid_size = 64  # Lower resolution for 3D performance
        x = np.linspace(-1, 1, self.grid_size)
        y = np.linspace(-1, 1, self.grid_size)
        self.X3d, self.Y3d = np.meshgrid(x, y)
        
        # Initial surface
        Z = np.zeros((self.grid_size, self.grid_size))
        self.surf = self.ax.plot_surface(self.X3d, self.Y3d, Z, cmap='hot',
                                          linewidth=0, antialiased=True)
        
        self.ax.set_xlabel('X Position')
        self.ax.set_ylabel('Y Position')
        self.ax.set_zlabel('Intensity')
        self.ax.set_title('Receiver Plane Intensity (3D)')
        
        # Draw receiver circle on the XY plane
        theta = np.linspace(0, 2*np.pi, 50)
        cx, cy = self.receiver_center
        circle_x = cx + self.receiver_radius * np.cos(theta)
        circle_y = cy + self.receiver_radius * np.sin(theta)
        circle_z = np.zeros_like(theta)
        self.circle_line, = self.ax.plot(circle_x, circle_y, circle_z, 
                                          'c--', linewidth=2)
        
        self.fig.tight_layout()
        self.draw()
    
    def set_3d_mode(self, enable):
        """Switch between 2D and 3D views."""
        if enable != self.is_3d:
            self.is_3d = enable
            if enable:
                self._setup_3d()
            else:
                self._setup_2d()
    
    def update_plot(self, intensity):
        """Update the intensity data."""
        if self.is_3d:
            # Downsample intensity for 3D
            from scipy.ndimage import zoom
            factor = self.grid_size / intensity.shape[0]
            intensity_small = zoom(intensity, factor, order=1)
            
            # Remove old surface and redraw
            self.ax.clear()
            self.surf = self.ax.plot_surface(self.X3d, self.Y3d, intensity_small, 
                                              cmap='hot', linewidth=0, antialiased=True)
            
            # Redraw receiver circle
            theta = np.linspace(0, 2*np.pi, 50)
            cx, cy = self.receiver_center
            circle_x = cx + self.receiver_radius * np.cos(theta)
            circle_y = cy + self.receiver_radius * np.sin(theta)
            circle_z = np.zeros_like(theta)
            self.ax.plot(circle_x, circle_y, circle_z, 'c--', linewidth=2)
            
            self.ax.set_xlabel('X Position')
            self.ax.set_ylabel('Y Position')
            self.ax.set_zlabel('Intensity')
            self.ax.set_title('Receiver Plane Intensity (3D)')
            self.ax.set_xlim(-1, 1)
            self.ax.set_ylim(-1, 1)
        else:
            self.img.set_data(intensity)
            vmax = intensity.max() if intensity.max() > 0 else 1
            self.img.set_clim(vmin=0, vmax=vmax)
        
        self.draw_idle()
    
    def set_receiver_radius(self, radius):
        """Update the receiver circle size."""
        self.receiver_radius = radius
        if not self.is_3d:
            self.circle.set_radius(radius)
            self.draw_idle()
    
    def set_receiver_center(self, x, y):
        """Update the receiver circle position."""
        self.receiver_center = (x, y)
        if not self.is_3d:
            self.circle.set_center((x, y))
            self.draw_idle()


class ChannelControl(QGroupBox):
    """Control widget for a single beam channel."""
    
    def __init__(self, channel_id, color, callback, default_tip=2048, default_tilt=2048, default_phase=2048):
        super().__init__(f"Channel {channel_id}")
        self.channel_id = channel_id
        self.callback = callback
        self.defaults = (default_tip, default_tilt, default_phase)
        
        self.setStyleSheet(f"QGroupBox {{ color: {color}; font-weight: bold; }}")
        
        layout = QGridLayout(self)
        
        # Tip (X)
        layout.addWidget(QLabel("Tip (X):"), 0, 0)
        self.tip_slider = QSlider(Qt.Orientation.Horizontal)
        self.tip_slider.setRange(0, 4095)
        self.tip_slider.setValue(default_tip)
        self.tip_slider.valueChanged.connect(self._on_change)
        layout.addWidget(self.tip_slider, 0, 1)
        self.tip_label = QLabel(str(default_tip))
        self.tip_label.setMinimumWidth(45)
        layout.addWidget(self.tip_label, 0, 2)
        
        # Tilt (Y)
        layout.addWidget(QLabel("Tilt (Y):"), 1, 0)
        self.tilt_slider = QSlider(Qt.Orientation.Horizontal)
        self.tilt_slider.setRange(0, 4095)
        self.tilt_slider.setValue(default_tilt)
        self.tilt_slider.valueChanged.connect(self._on_change)
        layout.addWidget(self.tilt_slider, 1, 1)
        self.tilt_label = QLabel(str(default_tilt))
        self.tilt_label.setMinimumWidth(45)
        layout.addWidget(self.tilt_label, 1, 2)
        
        # Phase
        layout.addWidget(QLabel("Phase:"), 2, 0)
        self.phase_slider = QSlider(Qt.Orientation.Horizontal)
        self.phase_slider.setRange(0, 4095)
        self.phase_slider.setValue(default_phase)
        self.phase_slider.valueChanged.connect(self._on_change)
        layout.addWidget(self.phase_slider, 2, 1)
        self.phase_label = QLabel(str(default_phase))
        self.phase_label.setMinimumWidth(45)
        layout.addWidget(self.phase_label, 2, 2)
    
    def _on_change(self):
        self.tip_label.setText(str(self.tip_slider.value()))
        self.tilt_label.setText(str(self.tilt_slider.value()))
        self.phase_label.setText(str(self.phase_slider.value()))
        self.callback()
    
    def get_values(self):
        return [self.tip_slider.value(), 
                self.tilt_slider.value(), 
                self.phase_slider.value()]
    
    def set_values(self, tip, tilt, phase):
        self.tip_slider.blockSignals(True)
        self.tilt_slider.blockSignals(True)
        self.phase_slider.blockSignals(True)
        
        self.tip_slider.setValue(int(tip))
        self.tilt_slider.setValue(int(tilt))
        self.phase_slider.setValue(int(phase))
        
        self.tip_label.setText(str(int(tip)))
        self.tilt_label.setText(str(int(tilt)))
        self.phase_label.setText(str(int(phase)))
        
        self.tip_slider.blockSignals(False)
        self.tilt_slider.blockSignals(False)
        self.phase_slider.blockSignals(False)


class SettingsTab(QWidget):
    """Settings panel for simulation parameters."""
    
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # --- Display Options ---
        display_group = QGroupBox("Display Options")
        display_layout = QVBoxLayout(display_group)
        
        self.view_3d_checkbox = QCheckBox("3D Surface View")
        self.view_3d_checkbox.setChecked(False)
        self.view_3d_checkbox.stateChanged.connect(self.toggle_3d_view)
        display_layout.addWidget(self.view_3d_checkbox)
        
        layout.addWidget(display_group)
        
        # --- Realism Mode ---
        realism_group = QGroupBox("Realism Mode")
        realism_layout = QVBoxLayout(realism_group)
        
        self.realism_checkbox = QCheckBox("Enable Higher-Order Aberrations")
        self.realism_checkbox.setChecked(False)
        self.realism_checkbox.stateChanged.connect(self.toggle_realism)
        realism_layout.addWidget(self.realism_checkbox)
        
        realism_layout.addWidget(QLabel("Adds uncorrectable wavefront distortions:\n"
                                        "• Astigmatism (elliptical beams)\n"
                                        "• Coma (comet-tail effect)\n"
                                        "• Trefoil (3-fold distortion)\n"
                                        "• Spherical aberration (radial blur)\n\n"
                                        "These show why real AO needs\n"
                                        "deformable mirrors, not just tip/tilt."))
        
        strength_layout = QHBoxLayout()
        strength_layout.addWidget(QLabel("Aberration Strength:"))
        self.aberration_strength = QDoubleSpinBox()
        self.aberration_strength.setRange(0.1, 1.0)
        self.aberration_strength.setValue(0.3)
        self.aberration_strength.setSingleStep(0.1)
        self.aberration_strength.valueChanged.connect(self.update_aberration_strength)
        strength_layout.addWidget(self.aberration_strength)
        realism_layout.addLayout(strength_layout)
        
        layout.addWidget(realism_group)
        
        # --- Channel Count ---
        ch_group = QGroupBox("Channel Configuration")
        ch_layout = QGridLayout(ch_group)
        
        ch_layout.addWidget(QLabel("Number of Channels:"), 0, 0)
        self.channel_count_spin = QSpinBox()
        self.channel_count_spin.setRange(1, 8)
        self.channel_count_spin.setValue(4)
        ch_layout.addWidget(self.channel_count_spin, 0, 1)
        
        self.apply_channels_btn = QPushButton("Apply Channel Count")
        self.apply_channels_btn.clicked.connect(self.apply_channel_count)
        self.apply_channels_btn.setStyleSheet("font-weight: bold;")
        ch_layout.addWidget(self.apply_channels_btn, 1, 0, 1, 2)
        
        layout.addWidget(ch_group)
        
        # --- Optimal Values ---
        opt_group = QGroupBox("Optimal DAC Values (Baseline)")
        opt_layout = QGridLayout(opt_group)
        
        opt_layout.addWidget(QLabel("Target values SPGD should converge to:"), 0, 0, 1, 2)
        
        opt_layout.addWidget(QLabel("Optimal Tip (X):"), 1, 0)
        self.optimal_tip_spin = QSpinBox()
        self.optimal_tip_spin.setRange(0, 4095)
        self.optimal_tip_spin.setValue(2048)
        opt_layout.addWidget(self.optimal_tip_spin, 1, 1)
        
        opt_layout.addWidget(QLabel("Optimal Tilt (Y):"), 2, 0)
        self.optimal_tilt_spin = QSpinBox()
        self.optimal_tilt_spin.setRange(0, 4095)
        self.optimal_tilt_spin.setValue(2048)
        opt_layout.addWidget(self.optimal_tilt_spin, 2, 1)
        
        opt_layout.addWidget(QLabel("Optimal Phase:"), 3, 0)
        self.optimal_phase_spin = QSpinBox()
        self.optimal_phase_spin.setRange(0, 4095)
        self.optimal_phase_spin.setValue(2048)
        opt_layout.addWidget(self.optimal_phase_spin, 3, 1)
        
        self.apply_optimal_btn = QPushButton("Apply Optimal Values")
        self.apply_optimal_btn.clicked.connect(self.apply_optimal_values)
        self.apply_optimal_btn.setStyleSheet("font-weight: bold;")
        opt_layout.addWidget(self.apply_optimal_btn, 4, 0, 1, 2)
        
        layout.addWidget(opt_group)
        
        # --- Physical Parameters ---
        phys_group = QGroupBox("Physical Parameters")
        phys_layout = QGridLayout(phys_group)
        
        phys_layout.addWidget(QLabel("Beam Waist:"), 0, 0)
        self.beam_waist_spin = QDoubleSpinBox()
        self.beam_waist_spin.setRange(0.05, 0.5)
        self.beam_waist_spin.setValue(0.15)
        self.beam_waist_spin.setSingleStep(0.01)
        phys_layout.addWidget(self.beam_waist_spin, 0, 1)
        
        phys_layout.addWidget(QLabel("Receiver Size:"), 1, 0)
        self.receiver_size_spin = QDoubleSpinBox()
        self.receiver_size_spin.setRange(0.1, 0.8)
        self.receiver_size_spin.setValue(0.25)
        self.receiver_size_spin.setSingleStep(0.05)
        phys_layout.addWidget(self.receiver_size_spin, 1, 1)
        
        phys_layout.addWidget(QLabel("Tip/Tilt Range:"), 2, 0)
        self.tip_tilt_range_spin = QDoubleSpinBox()
        self.tip_tilt_range_spin.setRange(0.1, 1.0)
        self.tip_tilt_range_spin.setValue(0.5)
        self.tip_tilt_range_spin.setSingleStep(0.1)
        phys_layout.addWidget(self.tip_tilt_range_spin, 2, 1)
        
        self.apply_phys_btn = QPushButton("Apply Physical Parameters")
        self.apply_phys_btn.clicked.connect(self.apply_physical_params)
        phys_layout.addWidget(self.apply_phys_btn, 3, 0, 1, 2)
        
        layout.addWidget(phys_group)
        
        layout.addStretch()
    
    def toggle_3d_view(self, state):
        """Toggle between 2D and 3D views."""
        self.parent_window.canvas.set_3d_mode(state == Qt.CheckState.Checked.value)
        self.parent_window.update_display()
    
    def toggle_realism(self, state):
        """Toggle realism mode."""
        self.parent_window.simulator.realism_mode = (state == Qt.CheckState.Checked.value)
        self.parent_window.update_display()
    
    def update_aberration_strength(self, value):
        """Update aberration strength."""
        self.parent_window.simulator.zernike_strength = value
    
    def apply_channel_count(self):
        """Apply new channel count."""
        new_count = self.channel_count_spin.value()
        self.parent_window.rebuild_channels(new_count)
    
    def apply_optimal_values(self):
        """Apply new optimal DAC values."""
        tip = self.optimal_tip_spin.value()
        tilt = self.optimal_tilt_spin.value()
        phase = self.optimal_phase_spin.value()
        
        sim = self.parent_window.simulator
        sim.set_optimal_values(tip, tilt, phase)
        
        # Move receiver circle to match target position
        target_x = sim.dac_to_position(tip)
        target_y = sim.dac_to_position(tilt)
        self.parent_window.canvas.set_receiver_center(target_x, target_y)
        
        self.parent_window.center_all()  # Reset sliders to new optimal
    
    def apply_physical_params(self):
        """Apply physical parameters."""
        sim = self.parent_window.simulator
        sim.beam_waist = self.beam_waist_spin.value()
        sim.fiber_waist = self.receiver_size_spin.value()
        sim.tip_tilt_range = self.tip_tilt_range_spin.value()
        sim._calibrate_max()
        self.parent_window.canvas.set_receiver_radius(sim.fiber_waist)
        self.parent_window.update_display()


class MainWindow(QMainWindow):
    """Main application window."""
    
    COLORS = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', 
              '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F']
    
    def __init__(self):
        super().__init__()
        self.simulator = OpticalSimulator(n_channels=4)
        self.channel_controls = []
        
        self.setWindowTitle("Phased Array Power Beaming Simulator")
        self.setMinimumSize(1100, 800)
        
        self.init_ui()
        self.update_display()
    
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        
        # --- Left Panel with Tabs ---
        left_panel = QTabWidget()
        
        # Controls Tab
        controls_widget = QWidget()
        controls_layout = QVBoxLayout(controls_widget)
        
        # Scrollable channel area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.channels_container = QWidget()
        self.channels_layout = QVBoxLayout(self.channels_container)
        
        self._create_channel_controls()
        
        scroll.setWidget(self.channels_container)
        controls_layout.addWidget(scroll, stretch=3)
        
        # Turbulence Controls
        turb_group = QGroupBox("Atmospheric Turbulence")
        turb_layout = QVBoxLayout(turb_group)
        
        strength_layout = QHBoxLayout()
        strength_layout.addWidget(QLabel("Strength:"))
        self.turb_strength = QDoubleSpinBox()
        self.turb_strength.setRange(0.05, 0.5)
        self.turb_strength.setValue(0.15)
        self.turb_strength.setSingleStep(0.05)
        strength_layout.addWidget(self.turb_strength)
        turb_layout.addLayout(strength_layout)
        
        btn_randomize = QPushButton("Apply Random Turbulence")
        btn_randomize.clicked.connect(self.randomize_turbulence)
        btn_randomize.setStyleSheet("font-weight: bold;")
        turb_layout.addWidget(btn_randomize)
        
        btn_clear = QPushButton("Clear Turbulence (Ideal)")
        btn_clear.clicked.connect(self.clear_turbulence)
        turb_layout.addWidget(btn_clear)
        
        controls_layout.addWidget(turb_group)
        
        # Presets
        preset_group = QGroupBox("Presets")
        preset_layout = QVBoxLayout(preset_group)
        
        btn_center = QPushButton("Reset to Optimal")
        btn_center.clicked.connect(self.center_all)
        preset_layout.addWidget(btn_center)
        
        btn_optimal = QPushButton("Show Optimal Solution")
        btn_optimal.clicked.connect(self.show_optimal)
        btn_optimal.setStyleSheet("color: green; font-weight: bold;")
        preset_layout.addWidget(btn_optimal)
        
        controls_layout.addWidget(preset_group)
        
        left_panel.addTab(controls_widget, "Controls")
        
        # Settings Tab
        self.settings_tab = SettingsTab(self)
        left_panel.addTab(self.settings_tab, "Settings")
        
        layout.addWidget(left_panel, stretch=2)
        
        # --- Right Panel: Display ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        self.canvas = IntensityCanvas()
        right_layout.addWidget(self.canvas, stretch=3)
        
        # ADC Reading
        adc_group = QGroupBox("Receiver Power (ADC Reading)")
        adc_layout = QVBoxLayout(adc_group)
        
        self.adc_label = QLabel("0")
        self.adc_label.setFont(QFont("Courier", 36, QFont.Weight.Bold))
        self.adc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        adc_layout.addWidget(self.adc_label)
        
        self.efficiency_label = QLabel("Coupling: 0.0%")
        self.efficiency_label.setFont(QFont("Courier", 18))
        self.efficiency_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        adc_layout.addWidget(self.efficiency_label)
        
        self.coupling_bar = QProgressBar()
        self.coupling_bar.setRange(0, 100)
        self.coupling_bar.setTextVisible(True)
        self.coupling_bar.setFixedHeight(35)
        adc_layout.addWidget(self.coupling_bar)
        
        right_layout.addWidget(adc_group)
        
        # Info
        info_group = QGroupBox("Info")
        info_layout = QVBoxLayout(info_group)
        self.info_label = QLabel(self._get_info_text())
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)
        right_layout.addWidget(info_group)
        
        layout.addWidget(right_panel, stretch=3)
    
    def _get_info_text(self):
        mode = "Realism" if self.simulator.realism_mode else "Basic"
        return (f"Channels: {self.simulator.n_channels} | Mode: {mode}\n"
                f"Optimal: Tip={self.simulator.optimal_tip}, "
                f"Tilt={self.simulator.optimal_tilt}, "
                f"Phase={self.simulator.optimal_phase}\n"
                f"Goal: All beams overlapped with aligned phases\n"
                f"Perfect alignment: N² intensity gain")
    
    def _create_channel_controls(self):
        """Create channel control widgets."""
        # Clear existing
        for ctrl in self.channel_controls:
            ctrl.deleteLater()
        self.channel_controls.clear()
        
        # Create new
        for i in range(self.simulator.n_channels):
            color = self.COLORS[i % len(self.COLORS)]
            ctrl = ChannelControl(
                i, color, self.on_control_change,
                default_tip=self.simulator.optimal_tip,
                default_tilt=self.simulator.optimal_tilt,
                default_phase=self.simulator.optimal_phase
            )
            self.channel_controls.append(ctrl)
            self.channels_layout.addWidget(ctrl)
        
        self.channels_layout.addStretch()
    
    def rebuild_channels(self, n_channels):
        """Rebuild UI for new channel count."""
        self.simulator.set_channel_count(n_channels)
        
        # Remove all items from layout (spacers don't have deleteLater)
        while self.channels_layout.count():
            item = self.channels_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        self._create_channel_controls()
        self.info_label.setText(self._get_info_text())
        self.update_display()
    
    def on_control_change(self):
        """Update simulator when controls change."""
        for i, ctrl in enumerate(self.channel_controls):
            if i < self.simulator.n_channels:
                vals = ctrl.get_values()
                self.simulator.dac_values[i] = vals
        self.update_display()
    
    def update_display(self):
        """Update intensity plot and ADC reading."""
        intensity = self.simulator.compute_intensity()
        self.canvas.update_plot(intensity)
        
        adc_reading, normalized = self.simulator.compute_metric()
        
        self.adc_label.setText(f"{adc_reading}")
        self.efficiency_label.setText(f"Coupling: {normalized*100:.1f}%")
        self.coupling_bar.setValue(int(normalized * 100))
        
        if normalized > 0.7:
            self.adc_label.setStyleSheet("color: green;")
        elif normalized > 0.3:
            self.adc_label.setStyleSheet("color: orange;")
        else:
            self.adc_label.setStyleSheet("color: red;")
        
        self.info_label.setText(self._get_info_text())
    
    def randomize_turbulence(self):
        """Apply random turbulence."""
        strength = self.turb_strength.value()
        self.simulator.randomize_turbulence(tip_tilt_std=strength, phase_std=1.5)
        self.update_display()
    
    def clear_turbulence(self):
        """Clear turbulence."""
        self.simulator.clear_turbulence()
        self.update_display()
    
    def center_all(self):
        """Reset all to optimal values."""
        for ctrl in self.channel_controls:
            ctrl.set_values(
                self.simulator.optimal_tip,
                self.simulator.optimal_tilt,
                self.simulator.optimal_phase
            )
        self.on_control_change()
    
    def show_optimal(self):
        """Set controls to optimal solution."""
        optimal = self.simulator.get_optimal_dac_values()
        for i, ctrl in enumerate(self.channel_controls):
            if i < len(optimal):
                ctrl.set_values(optimal[i, 0], optimal[i, 1], optimal[i, 2])
        self.on_control_change()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
