# =============================================================================
# Clock Definitions
# =============================================================================

create_clock -period 40.000 -name adc_dco_clk [get_ports adc_dco]

set_clock_groups -asynchronous \
   -group [get_clocks adc_dco_clk] \
   -group [get_clocks -include_generated_clocks -of_objects [get_pins -hierarchical -filter {NAME =~ *zynq_ultra_ps_e_0/pl_clk0}]]

# =============================================================================
# False Paths for CDC (Toggle Handshake)
# =============================================================================

set_false_path -from [get_cells -hierarchical -filter {NAME =~ *adc_toggle_reg*}] \
              -to   [get_cells -hierarchical -filter {NAME =~ *toggle_sync1_reg*}]

set_false_path -from [get_cells -hierarchical -filter {NAME =~ *adc_captured_raw_reg*}] \
              -to   [get_cells -hierarchical -filter {NAME =~ *adc_data_stable_reg*}]

# =============================================================================
# Clock Output Constraints (Programmable Dividers)
# =============================================================================

set_false_path -to [get_ports adc_enc]
set_false_path -to [get_ports clk_0]
set_false_path -to [get_ports clk_1]

# =============================================================================
# DAC Pin Assignments & Constraints (CORRECTED)
# =============================================================================

set_property PACKAGE_PIN L1 [get_ports {dac_data[0]}]
set_property PACKAGE_PIN K7 [get_ports {dac_data[1]}]
set_property PACKAGE_PIN T6 [get_ports {dac_data[2]}]
set_property PACKAGE_PIN R6 [get_ports {dac_data[3]}]
set_property PACKAGE_PIN J1 [get_ports {dac_data[4]}]
set_property PACKAGE_PIN H3 [get_ports {dac_data[5]}]
set_property PACKAGE_PIN H4 [get_ports {dac_data[6]}]
set_property PACKAGE_PIN J9 [get_ports {dac_data[7]}]
set_property PACKAGE_PIN K9 [get_ports {dac_data[8]}]
set_property PACKAGE_PIN J7 [get_ports {dac_data[9]}]
set_property PACKAGE_PIN H7 [get_ports {dac_data[10]}]
set_property PACKAGE_PIN N9 [get_ports {dac_data[11]}]

set_property PACKAGE_PIN K4 [get_ports {dac_oe}]
set_property IOSTANDARD LVCMOS18 [get_ports {dac_oe}]


set_property PACKAGE_PIN N8 [get_ports {clk_0}]
set_property PACKAGE_PIN K1 [get_ports {clk_1}]


set_property IOSTANDARD LVCMOS18 [get_ports {dac_data[*]}]
set_property IOSTANDARD LVCMOS18 [get_ports {clk_0}]
set_property IOSTANDARD LVCMOS18 [get_ports {clk_1}]

set_property DRIVE 12 [get_ports {clk_0}]
set_property DRIVE 12 [get_ports {clk_1}]
set_property SLEW FAST [get_ports {clk_0}]
set_property SLEW FAST [get_ports {clk_1}]

# =============================================================================
# ADC Pin Assignments & Constraints (CORRECTED)
# =============================================================================

set_property PACKAGE_PIN A8  [get_ports {adc_data[0]}]
set_property PACKAGE_PIN AH7 [get_ports {adc_data[1]}]
set_property PACKAGE_PIN A9  [get_ports {adc_data[2]}]
set_property PACKAGE_PIN A6  [get_ports {adc_data[3]}]
set_property PACKAGE_PIN A7  [get_ports {adc_data[4]}]
set_property PACKAGE_PIN A4  [get_ports {adc_data[5]}]
set_property PACKAGE_PIN B4  [get_ports {adc_data[6]}]
set_property PACKAGE_PIN AH8 [get_ports {adc_data[7]}]
set_property PACKAGE_PIN B3  [get_ports {adc_data[8]}]
set_property PACKAGE_PIN AC8 [get_ports {adc_data[9]}]
set_property PACKAGE_PIN C1  [get_ports {adc_data[10]}]
set_property PACKAGE_PIN AE8 [get_ports {adc_data[11]}]
set_property PACKAGE_PIN AE9 [get_ports {adc_data[12]}]
set_property PACKAGE_PIN B1  [get_ports {adc_data[13]}]
set_property PACKAGE_PIN AB8 [get_ports {adc_data[14]}]
set_property PACKAGE_PIN F1  [get_ports {adc_data[15]}]

set_property IOSTANDARD LVCMOS18 [get_ports {adc_data[*]}]

set_input_delay -clock adc_dco_clk -min 1.0 [get_ports {adc_data[*]}]
set_input_delay -clock adc_dco_clk -max 3.0 [get_ports {adc_data[*]}]

# =============================================================================
# ADC Control Pin Assignments & Constraints (UPDATED)
# =============================================================================

set_property PACKAGE_PIN D5 [get_ports {adc_enc}]
set_property PACKAGE_PIN C6 [get_ports {adc_oe}]
set_property PACKAGE_PIN E5 [get_ports {clk_sel}]
set_property PACKAGE_PIN A3 [get_ports {adc_dco}]

set_property IOSTANDARD LVCMOS18 [get_ports {adc_enc}]
set_property IOSTANDARD LVCMOS18 [get_ports {adc_oe}]
set_property IOSTANDARD LVCMOS18 [get_ports {clk_sel}]
set_property IOSTANDARD LVCMOS18 [get_ports {adc_dco}]

set_property DRIVE 12 [get_ports {adc_enc}]
set_property SLEW FAST [get_ports {adc_enc}]
