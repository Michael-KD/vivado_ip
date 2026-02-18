# =============================================================================
# Clock Definitions
# =============================================================================

# ADC DCO input clock (25 MHz from LTC2203)
create_clock -period 40.000 -name adc_dco_clk [get_ports adc_dco]

# Mark ADC DCO as asynchronous to Zynq PL clock
set_clock_groups -asynchronous \
    -group [get_clocks adc_dco_clk] \
    -group [get_clocks zynq_ultra_ps_e_0_pl_clk]

# =============================================================================
# False Paths for CDC (Toggle Handshake)
# =============================================================================

# Toggle signal CDC path (2-stage sync + edge detect)
set_false_path -from [get_cells -hierarchical -filter {NAME =~ *adc_toggle_reg*}] \
               -to   [get_cells -hierarchical -filter {NAME =~ *toggle_sync1_reg*}]

# Data capture path (sampled when toggle edge detected - data is stable)
set_false_path -from [get_cells -hierarchical -filter {NAME =~ *adc_captured_raw_reg*}] \
               -to   [get_cells -hierarchical -filter {NAME =~ *adc_data_stable_reg*}]

# =============================================================================
# Clock Output Constraints (Programmable Dividers)
# =============================================================================
# These clocks have runtime-programmable frequency via slv_reg2.
# Cannot meaningfully constrain timing - mark as false paths.
set_false_path -to [get_ports adc_enc]
set_false_path -to [get_ports clk_0]
set_false_path -to [get_ports clk_1]

# =============================================================================
# DAC Pin Assignments & Constraints
# =============================================================================

set_property PACKAGE_PIN H11 [get_ports {dac_data[0]}]
set_property PACKAGE_PIN L13 [get_ports {dac_data[1]}]
set_property PACKAGE_PIN L14 [get_ports {dac_data[2]}]
set_property PACKAGE_PIN K12 [get_ports {dac_data[3]}]
set_property PACKAGE_PIN K13 [get_ports {dac_data[4]}]
set_property PACKAGE_PIN J14 [get_ports {dac_data[5]}]
set_property PACKAGE_PIN K14 [get_ports {dac_data[6]}]
set_property PACKAGE_PIN H12 [get_ports {dac_data[7]}]
set_property PACKAGE_PIN J12 [get_ports {dac_data[8]}]
set_property PACKAGE_PIN F10 [get_ports {dac_data[9]}]
set_property PACKAGE_PIN G11 [get_ports {dac_data[10]}]
set_property PACKAGE_PIN G15 [get_ports {dac_data[11]}]
set_property PACKAGE_PIN G14 [get_ports {clk_0}]
set_property PACKAGE_PIN G10 [get_ports {clk_1}]

set_property IOSTANDARD LVCMOS33 [get_ports {dac_data[*]}]
set_property IOSTANDARD LVCMOS33 [get_ports {clk_0}]
set_property IOSTANDARD LVCMOS33 [get_ports {clk_1}]

# DAC clock output optimization (low jitter)
set_property DRIVE 12 [get_ports {clk_0}]
set_property DRIVE 12 [get_ports {clk_1}]
set_property SLEW FAST [get_ports {clk_0}]
set_property SLEW FAST [get_ports {clk_1}]

# Force ODDRE1 into IOB for consistent timing
set_property IOB TRUE [get_ports {clk_0}]
set_property IOB TRUE [get_ports {clk_1}]

# =============================================================================
# ADC Pin Assignments & Constraints
# =============================================================================

set_property PACKAGE_PIN A11 [get_ports {adc_data[0]}]
set_property PACKAGE_PIN A14 [get_ports {adc_data[1]}]
set_property PACKAGE_PIN A13 [get_ports {adc_data[2]}]
set_property PACKAGE_PIN B14 [get_ports {adc_data[3]}]
set_property PACKAGE_PIN A15 [get_ports {adc_data[4]}]
set_property PACKAGE_PIN E14 [get_ports {adc_data[5]}]
set_property PACKAGE_PIN C13 [get_ports {adc_data[6]}]
set_property PACKAGE_PIN B15 [get_ports {adc_data[7]}]
set_property PACKAGE_PIN D14 [get_ports {adc_data[8]}]
set_property PACKAGE_PIN F11 [get_ports {adc_data[9]}]
set_property PACKAGE_PIN H13 [get_ports {adc_data[10]}]
set_property PACKAGE_PIN C14 [get_ports {adc_data[11]}]
set_property PACKAGE_PIN C11 [get_ports {adc_data[12]}]
set_property PACKAGE_PIN D15 [get_ports {adc_data[13]}]
set_property PACKAGE_PIN F12 [get_ports {adc_data[14]}]
set_property PACKAGE_PIN H14 [get_ports {adc_data[15]}]

set_property IOSTANDARD LVCMOS33 [get_ports {adc_data[*]}]

# ADC data input delay relative to DCO (from LTC2203 datasheet)
set_input_delay -clock adc_dco_clk -min 1.0 [get_ports {adc_data[*]}]
set_input_delay -clock adc_dco_clk -max 3.0 [get_ports {adc_data[*]}]

# =============================================================================
# ADC Control Pin Assignments & Constraints
# =============================================================================

set_property PACKAGE_PIN A12 [get_ports {adc_enc}]
set_property PACKAGE_PIN B13 [get_ports {adc_oe}]
set_property PACKAGE_PIN E13 [get_ports {clk_sel}]
set_property PACKAGE_PIN B10 [get_ports {adc_dco}]

set_property IOSTANDARD LVCMOS33 [get_ports {adc_enc}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_oe}]
set_property IOSTANDARD LVCMOS33 [get_ports {clk_sel}]
set_property IOSTANDARD LVCMOS33 [get_ports {adc_dco}]

# ADC encode clock output optimization (low jitter)
set_property DRIVE 12 [get_ports {adc_enc}]
set_property SLEW FAST [get_ports {adc_enc}]

# Force ODDRE1 into IOB for consistent timing
set_property IOB TRUE [get_ports {adc_enc}]
