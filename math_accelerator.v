`timescale 1ns / 1ps

module math_accelerator(
    input wire clk,                  // System Clock (100 MHz)
    input wire signed [15:0] data_in,// From ADC (Signed 2's Comp, ±10V)
    output reg [11:0] data_out       // To DAC (12-bit Unsigned, 0-10V)
    );

    // ==========================================================================
    // Simple 4x Gain Passthrough with Bipolar-to-Unipolar Conversion
    // ==========================================================================
    // ADC: 16-bit signed (-32768 to +32767) representing ±10V
    // DAC: 12-bit unsigned (0 to 4095) representing 0-10V
    //
    // Pipeline Stage 1: Apply 4x gain (left shift by 2)
    // Pipeline Stage 2: Convert bipolar to unipolar and extract 12 bits
    // ==========================================================================

    // Stage 1: 4x Gain (arithmetic shift preserves sign)
    reg signed [17:0] scaled_data;  // 18-bit to hold 4x of 16-bit signed
    
    always @(posedge clk) begin
        scaled_data <= data_in <<< 2;  // 4x gain via left shift
    end

    // Stage 2: Bipolar-to-Unipolar Conversion + 12-bit Extraction
    // Add 32768 to shift range: [-32768, +32767] -> [0, 65535]
    // Then take upper 12 bits: [15:4] for proper scaling
    reg [17:0] unsigned_data;
    
    always @(posedge clk) begin
        // Convert signed to unsigned by adding offset
        unsigned_data <= scaled_data + 18'sd32768;
        
        // Extract 12 MSBs with saturation
        if (unsigned_data[16])  // Overflow check
            data_out <= 12'd4095;
        else if (unsigned_data[15:4] > 12'd4095)
            data_out <= 12'd4095;
        else
            data_out <= unsigned_data[15:4];
    end

endmodule