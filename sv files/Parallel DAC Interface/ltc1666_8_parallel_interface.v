module ltc1666_8_parallel_interface #(
    parameter integer SETTLE_CYCLES = 10
)(
    input  wire        clk,
    input  wire        reset,
    input  wire        start,             // Start signal (1-cycle pulse)
    input  wire        broadcast,         // 1 = write to all DACs
    input  wire [2:0]  dac_index,         // Select DAC 0–7 (ignored in broadcast)
    input  wire [11:0] dac_data,          // 12-bit DAC data

    output reg  [11:0] dac_out,           // Shared data lines
    output reg         wr,                // Shared WR signal
    output reg  [7:0]  cs_n,              // Per-DAC active-low chip select
    output reg         dac_valid,         // Output becomes valid after settling
    output reg         busy               // Busy while writing or settling
);

    typedef enum reg [1:0] {
        IDLE   = 2'd0,
        WRITE  = 2'd1,
        SETTLE = 2'd2
    } state_t;

    state_t state;
    reg [3:0] settle_cnt;

    always @(posedge clk) begin
        if (reset) begin
            state      <= IDLE;
            wr         <= 0;
            dac_out    <= 12'd0;
            cs_n       <= 8'hFF;
            dac_valid  <= 0;
            busy       <= 0;
            settle_cnt <= 0;
        end else begin
            case (state)
                IDLE: begin
                    wr        <= 0;
                    dac_valid <= 0;
                    busy      <= 0;
                    cs_n      <= 8'hFF;

                    if (start) begin
                        dac_out <= dac_data;
                        wr      <= 1;
                        busy    <= 1;
                        if (broadcast)
                            cs_n <= 8'b00000000; // All DACs selected
                        else
                            cs_n <= ~(8'b1 << dac_index); // Select one
                        state <= WRITE;
                    end
                end

                WRITE: begin
                    wr         <= 0;
                    cs_n       <= 8'hFF;
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
