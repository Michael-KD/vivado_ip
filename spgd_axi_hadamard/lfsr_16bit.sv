`timescale 1ns / 1ps

module lfsr_16bit #(
    // Every channel will need a different starting seed
    parameter bit [15:0] SEED = 16'h1234
)(
    input  logic clk,
    input  logic rst_n,      // Active low reset
    input  logic enable,     // Only shift when FSM GEN_PERTURB
    output logic coin_flip   // 0 or 1
);

    logic [15:0] lfsr_reg;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            lfsr_reg <= SEED;
        end else if (enable) begin
            // 16-bit Galois LFSR polynomial taps: 16, 14, 13, 11
            lfsr_reg[15] <= lfsr_reg[0];
            lfsr_reg[14] <= lfsr_reg[15] ^ lfsr_reg[0];
            lfsr_reg[13] <= lfsr_reg[14] ^ lfsr_reg[0];
            lfsr_reg[12] <= lfsr_reg[13];
            lfsr_reg[11] <= lfsr_reg[12] ^ lfsr_reg[0];
            lfsr_reg[10:0] <= lfsr_reg[11:1];
        end
    end

    // Output the LSB as our random coin flip
    assign coin_flip = lfsr_reg[0];

endmodule