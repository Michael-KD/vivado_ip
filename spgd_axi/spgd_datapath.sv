`timescale 1ns / 1ps

module spgd_datapath #(
    parameter NUM_CHANNELS = 8,
    parameter ADC_WIDTH = 16,
    parameter DAC_WIDTH = 16
)(
    input  logic clk,
    input  logic rst_n,

    // Control Signals (From FSM)
    input  logic select_plus_minus,
    input  logic latch_j_plus,
    input  logic latch_j_minus,
    input  logic trigger_dsp_update,
    input  logic commit_new_u,

    // LFSR Array Input
    input  logic [NUM_CHANNELS-1:0] random_flips,

    // Algorithm parameters (from processor)
    input  logic [DAC_WIDTH-1:0] perturb_amp, // delta_u magnitude (unsigned)
    input  logic signed [31:0]   gamma_lr,    // Learning rate (signed fixed-point)

    // Hardware Interfaces
    input  logic [ADC_WIDTH-1:0] adc_data_in,
    output logic [DAC_WIDTH-1:0] dac_data_out [NUM_CHANNELS] // unpacked array of 8 DAC values
);

    // ==========================================
    // ADC Latching & Global Math (Delta J)
    // ==========================================
    // We add an extra bit to prevent overflow during subtraction
    logic signed [ADC_WIDTH:0] j_plus_reg;
    logic signed [ADC_WIDTH:0] j_minus_reg;
    logic signed [ADC_WIDTH:0] delta_j;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            j_plus_reg  <= '0;
            j_minus_reg <= '0;
        end else begin
            // Zero-extend the unsigned ADC data to signed
            if (latch_j_plus)  j_plus_reg  <= {1'b0, adc_data_in};
            if (latch_j_minus) j_minus_reg <= {1'b0, adc_data_in};
        end
    end

    // Combinational subtraction (J_plus - J_minus)
    assign delta_j = j_plus_reg - j_minus_reg;

    // The base step size: (gamma * Delta J)
    // We calculate this ONCE globally to save DSP slices
    logic signed [63:0] global_step_size;
    
    always_ff @(posedge clk) begin
        if (trigger_dsp_update) begin
            global_step_size <= gamma_lr * delta_j;
        end
    end

    // ==========================================
    // Parallel Per-Channel ALUs & Registers
    // ==========================================
    // The baseline phase registers (u)
    logic [DAC_WIDTH-1:0] u_reg [NUM_CHANNELS];
    
    genvar i;
    generate
        for (i = 0; i < NUM_CHANNELS; i++) begin : gen_channel_alu
            
            // 1. Determine the perturbation for this specific channel (+A or -A)
            logic signed [DAC_WIDTH:0] delta_u;
            assign delta_u = random_flips[i] ? {1'b0, perturb_amp} : -{1'b0, perturb_amp};

            // 2. Output Multiplexer (to physical DAC)
            // If FSM says PLUS: output = u + delta_u
            // If FSM says MINUS: output = u - delta_u
            logic [DAC_WIDTH-1:0] u_plus, u_minus;
            assign u_plus  = u_reg[i] + delta_u;
            assign u_minus = u_reg[i] - delta_u;
            
            assign dac_data_out[i] = select_plus_minus ? u_plus : u_minus;

            // 3. DSP Update Calculation
            logic signed [DAC_WIDTH-1:0] scaled_update;
            assign scaled_update = global_step_size[47:32]; 

            // Calculate with 1 extra bit (DAC_WIDTH + 1) to catch overflow/underflow
            logic signed [DAC_WIDTH:0] temp_next_u;
            assign temp_next_u = random_flips[i] ? 
                                 ({1'b0, u_reg[i]} + scaled_update) : 
                                 ({1'b0, u_reg[i]} - scaled_update);

            logic [DAC_WIDTH-1:0] next_u;
            always_comb begin
                // Underflow clamp (less than 0)
                if (temp_next_u < 0) begin
                    next_u = '0; 
                // Overflow clamp (greater than max DAC value, e.g., 0xFFFF)
                end else if (temp_next_u > {1'b0, {DAC_WIDTH{1'b1}}}) begin
                    next_u = '1; // Sets all bits to 1
                // Safe range
                end else begin
                    next_u = temp_next_u[DAC_WIDTH-1:0];
                end
            end
            // 4. Commit the new baseline phase to the register
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    u_reg[i] <= '0; // Start at 0V
                end else if (commit_new_u) begin
                    u_reg[i] <= next_u;
                end
            end
            
        end
    endgenerate

endmodule