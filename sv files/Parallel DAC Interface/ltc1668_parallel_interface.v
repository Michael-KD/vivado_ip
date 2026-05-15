module ltc1668_parallel_interface (
    input  wire        clk,         // System clock
    input  wire        reset,       // Active-high synchronous reset
    input  wire        start,       // Start write (1-cycle pulse)
    input  wire [15:0] dac_data,    // 16-bit DAC input
    output reg  [15:0] dac_out,     // 16-bit output to DAC
    output reg         wr,          // Write strobe (1-cycle rising edge pulse)
    output reg         dac_valid,   // High after data has settled
    output reg         busy         // High during write and settling
);

    // State encoding
    typedef enum reg [1:0] {
        IDLE    = 2'b00,
        WRITE   = 2'b01,
        SETTLE  = 2'b10
    } state_t;

    state_t state;

    // Settling delay parameter (based on your clk freq)
    parameter integer SETTLE_CYCLES = 5;
    reg [3:0] settle_cnt;

    always @(posedge clk) begin
        if (reset) begin
            state      <= IDLE;
            wr         <= 0;
            dac_out    <= 16'd0;
            dac_valid  <= 0;
            busy       <= 0;
            settle_cnt <= 0;
        end else begin
            case (state)
                IDLE: begin
                    wr        <= 0;
                    dac_valid <= 0;
                    busy      <= 0;
                    if (start) begin
                        dac_out <= dac_data;
                        wr      <= 1;         // Pulse WR high
                        busy    <= 1;
                        state   <= WRITE;
                    end
                end

                WRITE: begin
                    wr         <= 0;          // End WR pulse
                    settle_cnt <= SETTLE_CYCLES;
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
