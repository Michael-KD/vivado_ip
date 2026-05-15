`timescale 1ns / 1ps

// 8x8 Hadamard matrix ROM (Sylvester construction)
// Each row is an orthogonal ±1 perturbation vector.
// Output encoding: bit=1 means +1, bit=0 means -1.
module hadamard_rom #(
    parameter NUM_CHANNELS = 8
)(
    input  logic [2:0] row_index,
    output logic [NUM_CHANNELS-1:0] row_vector
);

    // Standard 8x8 Hadamard matrix (Sylvester/Walsh construction)
    // Row 0: [+1 +1 +1 +1 +1 +1 +1 +1]
    // Row 1: [+1 -1 +1 -1 +1 -1 +1 -1]
    // Row 2: [+1 +1 -1 -1 +1 +1 -1 -1]
    // Row 3: [+1 -1 -1 +1 +1 -1 -1 +1]
    // Row 4: [+1 +1 +1 +1 -1 -1 -1 -1]
    // Row 5: [+1 -1 +1 -1 -1 +1 -1 +1]
    // Row 6: [+1 +1 -1 -1 -1 -1 +1 +1]
    // Row 7: [+1 -1 -1 +1 -1 +1 +1 -1]
    //
    // Matches the Hadamard matrix from dither_gen_FixPt.sv in the
    // Simulink reference (parameter a0, stored row-major).

    always_comb begin
        case (row_index)
            3'd0: row_vector = 8'b11111111;
            3'd1: row_vector = 8'b10101010;
            3'd2: row_vector = 8'b11001100;
            3'd3: row_vector = 8'b10011001;
            3'd4: row_vector = 8'b11110000;
            3'd5: row_vector = 8'b10100101;
            3'd6: row_vector = 8'b11000011;
            3'd7: row_vector = 8'b10010110;
            default: row_vector = 8'b11111111;
        endcase
    end

endmodule
