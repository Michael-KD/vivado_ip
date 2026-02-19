`timescale 1ns / 1ps

module spgd_top #(
    parameter NUM_CHANNELS = 8,
    parameter ADC_WIDTH    = 16,
    parameter DAC_WIDTH    = 16
)(
    // System Clocks and Resets
    input  logic clk,
    input  logic rst_n,

    // Inputs from the processor
    input  logic        enable_loop,
    input  logic [15:0] settle_cycles,
    input  logic [15:0] perturb_amp,
    input  logic [31:0] gamma_lr,

    // Hardware Interfaces
    input  logic [ADC_WIDTH-1:0] adc_data_in,
    
    // Flattened array for Vivado IP Packager compatibility
    output logic [(NUM_CHANNELS*DAC_WIDTH)-1:0] dac_data_flat_out
);

    // FSM to Datapath & LFSR
    logic trigger_lfsr;
    logic select_plus_minus;
    logic latch_j_plus;
    logic latch_j_minus;
    logic trigger_dsp_update;
    logic commit_new_u;

    // LFSR to Datapath
    logic [NUM_CHANNELS-1:0] random_flips;

    // Unpacked DAC array from Datapath (easier to read)
    logic [DAC_WIDTH-1:0] dac_data_array [NUM_CHANNELS];

    // Flatten the output array for the IP block boundary
    genvar i;
    generate
        for (i = 0; i < NUM_CHANNELS; i++) begin : gen_flatten
            assign dac_data_flat_out[(i*DAC_WIDTH) +: DAC_WIDTH] = dac_data_array[i];
        end
    endgenerate

    // State Machine
    spgd_fsm u_fsm (
        .clk                (clk),
        .rst_n              (rst_n),
        .enable_loop        (enable_loop),
        .settle_cycles      (settle_cycles),
        .trigger_lfsr       (trigger_lfsr),
        .select_plus_minus  (select_plus_minus),
        .latch_j_plus       (latch_j_plus),
        .latch_j_minus      (latch_j_minus),
        .trigger_dsp_update (trigger_dsp_update),
        .commit_new_u       (commit_new_u)
    );

    // LFSR Array
    dither_array #(
        .NUM_CHANNELS(NUM_CHANNELS)
    ) u_lfsr_array (
        .clk           (clk),
        .rst_n         (rst_n),
        .enable_dither (trigger_lfsr),
        .random_flips  (random_flips)
    );

    // Datapath
    spgd_datapath #(
        .NUM_CHANNELS(NUM_CHANNELS),
        .ADC_WIDTH(ADC_WIDTH),
        .DAC_WIDTH(DAC_WIDTH)
    ) u_datapath (
        .clk                (clk),
        .rst_n              (rst_n),
        .select_plus_minus  (select_plus_minus),
        .latch_j_plus       (latch_j_plus),
        .latch_j_minus      (latch_j_minus),
        .trigger_dsp_update (trigger_dsp_update),
        .commit_new_u       (commit_new_u),
        .random_flips       (random_flips),
        .perturb_amp        (perturb_amp),
        .gamma_lr           (gamma_lr),
        .adc_data_in        (adc_data_in),
        .dac_data_out       (dac_data_array)
    );

endmodule