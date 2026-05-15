`timescale 1ns / 1ps

module math_accelerator(
    input wire clk,                  // System Clock (100 MHz)
    input wire signed [15:0] data_in,// From ADC (Signed 2's Comp, ±10V)
    output reg [11:0] data_out       // To DAC (12-bit Unsigned, 0-4V)
    );

    // ==========================================================================
    // Simple Passthrough: 16-bit Signed to 12-bit Unsigned Conversion
    // ==========================================================================
    // ADC: 16-bit signed (-32768 to +32767) representing ±10V
    // DAC: 12-bit unsigned (0 to 4095) representing 0-4V
    //
    // Conversion: Add 32768 to shift signed range to unsigned, take upper 12 bits
    // ==========================================================================

    // Single pipeline stage: Convert and extract
    always @(posedge clk) begin
        // Add 32768 to convert signed to unsigned: [-32768,+32767] -> [0,65535]
        // Then take bits [15:4] for 12-bit output
        data_out <= (data_in + 16'sd32768) >> 4;
    end

endmodule