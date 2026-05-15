`timescale 1ns / 1ps

// Hadamard-based dither generator
// Replaces the LFSR-based dither_array with deterministic Hadamard row cycling.
// Each pulse of advance_row selects the next row of the 8x8 Hadamard matrix.
// After all 8 rows are used (one epoch), the epoch counter increments.
// An optional sign flip is applied based on epoch_counter[epoch_bit_select],
// following the same scheme as select_vector_FixPt.sv in the Simulink reference.
module hadamard_dither #(
    parameter NUM_CHANNELS = 8
)(
    input  logic clk,
    input  logic rst_n,
    input  logic advance_row,          // Pulse to select next Hadamard row
    input  logic [3:0] epoch_bit_select,  // Which epoch counter bit controls sign flip

    output logic [NUM_CHANNELS-1:0] dither_signs,  // ±1 encoded: 1=+1, 0=-1
    output logic [2:0]  current_row,               // Diagnostic: current row index
    output logic [15:0] epoch_count                 // Diagnostic: epoch counter
);

    // ==========================================
    // Row Counter (0 → 7 → 0 ...)
    // ==========================================
    logic [2:0] row_counter;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            row_counter <= 3'd0;
        end else if (advance_row) begin
            row_counter <= row_counter + 3'd1; // wraps naturally at 3 bits
        end
    end

    assign current_row = row_counter;

    // ==========================================
    // Epoch Counter (increments every 8 rows)
    // ==========================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            epoch_count <= 16'd0;
        end else if (advance_row && (row_counter == 3'd7)) begin
            epoch_count <= epoch_count + 16'd1;
        end
    end

    // ==========================================
    // Hadamard ROM Lookup
    // ==========================================
    logic [NUM_CHANNELS-1:0] rom_row;

    hadamard_rom #(
        .NUM_CHANNELS(NUM_CHANNELS)
    ) u_rom (
        .row_index  (row_counter),
        .row_vector (rom_row)
    );

    // ==========================================
    // Optional Epoch-Based Sign Flip
    // ==========================================
    // When epoch_counter[epoch_bit_select] == 1, negate the entire row.
    // XOR with the selected epoch bit: flipping all bits inverts +1↔-1.
    logic epoch_flip;
    assign epoch_flip = epoch_count[epoch_bit_select];

    assign dither_signs = epoch_flip ? ~rom_row : rom_row;

endmodule
