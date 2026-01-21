`timescale 1ns / 1ps

module math_accelerator(
    input wire clk,                  // System Clock (100 MHz)
    input wire signed [15:0] data_in,// From ADC (Signed 2's Comp)
    output reg [11:0] data_out       // To DAC (12-bit Unsigned)
    );

    // 1. Math Stage: Squaring
    // Input is 16-bit, so Square is 32-bit.
    // We use 'signed' math so -2V * -2V becomes +4V.
    reg signed [31:0] squared_result;
    
    always @(posedge clk) begin
        squared_result <= data_in * data_in;
    end

    // 2. Bit Selection (16-bit -> 12-bit Conversion)
    // We take the top 12 bits of the magnitude (Q30 down to Q19).
    // This maintains the standard 10V scale.
    // Full Scale Input (+/-10V) -> Full Scale Output (4095)
    
    always @(posedge clk) begin
        data_out <= squared_result[30:19];
    end

endmodule