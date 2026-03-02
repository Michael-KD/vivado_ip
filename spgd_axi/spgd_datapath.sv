`timescale 1ns / 1ps

module spgd_datapath #(
    parameter NUM_CHANNELS = 8,
    parameter ADC_WIDTH = 16,
    parameter DAC_WIDTH = 16
)(
    input  logic clk,
    input  logic rst_n,

    // Soft reset (from processor) - resets u_reg to mid-scale
    input  logic soft_reset,

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
            // Sign-extend the 2's complement ADC data
            if (latch_j_plus)  j_plus_reg  <= {adc_data_in[ADC_WIDTH-1], adc_data_in};
            if (latch_j_minus) j_minus_reg <= {adc_data_in[ADC_WIDTH-1], adc_data_in};
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
            // Use signed arithmetic with extra bit to detect overflow/underflow
            logic signed [DAC_WIDTH+1:0] u_plus_full, u_minus_full;
            assign u_plus_full  = $signed({2'b0, u_reg[i]}) + $signed(delta_u);
            assign u_minus_full = $signed({2'b0, u_reg[i]}) - $signed(delta_u);

            // Saturate to valid DAC range [0, 2^DAC_WIDTH - 1]
            logic [DAC_WIDTH-1:0] u_plus, u_minus;
            always_comb begin
                // Saturate u_plus
                if (u_plus_full < 0)
                    u_plus = '0;
                else if (u_plus_full > {{2{1'b0}}, {DAC_WIDTH{1'b1}}})
                    u_plus = '1;
                else
                    u_plus = u_plus_full[DAC_WIDTH-1:0];

                // Saturate u_minus
                if (u_minus_full < 0)
                    u_minus = '0;
                else if (u_minus_full > {{2{1'b0}}, {DAC_WIDTH{1'b1}}})
                    u_minus = '1;
                else
                    u_minus = u_minus_full[DAC_WIDTH-1:0];
            end
            
            assign dac_data_out[i] = select_plus_minus ? u_plus : u_minus;

            // 3. DSP Update Calculation
            // Extract bits [31:16] - divides by 65536 instead of 4 billion
            logic signed [DAC_WIDTH-1:0] scaled_update;
            assign scaled_update = global_step_size[31:16]; 

            // Calculate with 1 extra bit (DAC_WIDTH + 1) to catch overflow/underflow
            logic signed [DAC_WIDTH+1:0] temp_next_u;
            assign temp_next_u = random_flips[i] ? 
                                ($signed({2'b00, u_reg[i]}) + $signed(scaled_update)) : 
                                ($signed({2'b00, u_reg[i]}) - $signed(scaled_update));

            logic [DAC_WIDTH-1:0] next_u;
            always_comb begin
                // Underflow clamp (less than 0)
                if (temp_next_u < 0) begin
                    next_u = '0; 
                // Overflow clamp (greater than max DAC value, e.g., 0xFFFF)
                end else if (temp_next_u > {2'b00, {DAC_WIDTH{1'b1}}}) begin
                    next_u = '1; // Sets all bits to 1
                // Safe range
                end else begin
                    next_u = temp_next_u[DAC_WIDTH-1:0];
                end
            end
            // 4. Commit the new baseline phase to the register
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    u_reg[i] <= {1'b1, {(DAC_WIDTH-1){1'b0}}}; // Start at mid-scale (2V for DAC)
                end else if (soft_reset) begin
                    u_reg[i] <= {1'b1, {(DAC_WIDTH-1){1'b0}}}; // Reset to mid-scale
                end else if (commit_new_u) begin
                    u_reg[i] <= next_u;
                end
            end
            
        end
    endgenerate

endmodule