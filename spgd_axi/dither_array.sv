`timescale 1ns / 1ps

module dither_array #(
    parameter NUM_CHANNELS = 8
)(
    input  logic clk,
    input  logic rst_n,
    input  logic enable_dither, // Pulses high for 1 clock cycle to get new values
    
    // Output is a packed array of 8 bits
    output logic [NUM_CHANNELS-1:0] random_flips 
);

    genvar i;
    generate
        for (i = 0; i < NUM_CHANNELS; i++) begin : gen_lfsr
            // Create a unique seed for each channel
            localparam bit [15:0] UNIQUE_SEED = 16'h1001 + (i * 16'h0100);
            
            lfsr_16bit #(
                .SEED(UNIQUE_SEED)
            ) u_lfsr (
                .clk(clk),
                .rst_n(rst_n),
                .enable(enable_dither),
                .coin_flip(random_flips[i])
            );
        end
    endgenerate

endmodule