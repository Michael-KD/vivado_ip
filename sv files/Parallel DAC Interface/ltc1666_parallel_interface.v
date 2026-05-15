module ltc1666_parallel_interface (
    input  wire        clk,         // System clock
    input  wire        reset,       // Synchronous reset
    input  wire        start,       // Start write (1-cycle pulse)
    input  wire [15:0] dac_data,    // 12-bit input to write to DAC
    output reg  [11:0] dac_out,     // 12-bit parallel output to DAC
    output reg         wr,          // Write strobe (1-cycle pulse)
    output reg         dac_valid,   // High when DAC output is valid
    output reg         busy         // High during write + settling
);

    // FSM states
    wire [11:0] trun_dac_data;
    assign trun_dac_data = dac_data[13:2]; /* ufix12_En10 [8] */
    
    parameter IDLE    = 2'b00;
    parameter WRITE   = 2'b01;
    parameter SETTLE  = 2'b10;

    reg [1:0] state;

    // Delay parameters
    parameter integer SETTLE_CYCLES = 10; // Adjust for clock frequency
    reg [7:0] settle_cnt; // Supports up to 15 cycles; expand if needed

    always @(posedge clk) begin
        if (reset) begin
            state      <= IDLE;
            wr         <= 0;
            dac_valid  <= 0;
            busy       <= 0;
            dac_out    <= 12'd0;
            settle_cnt <= 0;
        end else begin
            case (state)
                IDLE: begin
                    wr        <= 0;
                    dac_valid <= 0;
                    busy      <= 0;
                    if (start) begin
                        dac_out    <= trun_dac_data;
                        wr         <= 1;         // Pulse WR
                        busy       <= 1;
                        state      <= WRITE;
                    end
                end

                WRITE: begin
                    wr         <= 1;             // End WR pulse
                    settle_cnt <= SETTLE_CYCLES; // Begin settling
                    state      <= SETTLE;
                end

                SETTLE: begin
                    if (settle_cnt == 0) begin
                        dac_valid <= 1;
                        busy      <= 0;
                        state     <= IDLE;
                    end else begin
                        settle_cnt <= settle_cnt - 1;
                    end
                end
            endcase
        end
    end

endmodule
