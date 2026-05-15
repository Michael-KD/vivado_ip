module multi_ltc1666_interface #(
    parameter integer N = 8,                 // Number of DACs
    parameter integer SETTLE_CYCLES = 10     // DAC settle time (in cycles)
)(
    input  wire                     clk,
    input  wire                     reset,
    input  wire                     start,           // Start write
    input  wire                     broadcast,       // 1 = write to all DACs
    input  wire [$clog2(N)-1:0]     dac_index,       // Select DAC 0..N-1
    input  wire [11:0]              dac_data,        // Data to write

    output reg  [11:0]              dac_out,         // Shared parallel DAC bus
    output reg                      wr,              // Shared WR line
    output reg  [N-1:0]             cs_n,            // Active-low DAC enables
    output reg                      dac_valid,       // High when output is valid
    output reg                      busy             // Active during write/settle
);

    typedef enum reg [1:0] {
        IDLE   = 2'd0,
        WRITE  = 2'd1,
        SETTLE = 2'd2
    } state_t;

    state_t state;
    reg [$clog2(SETTLE_CYCLES+1)-1:0] settle_cnt;

    integer i;

    always @(posedge clk) begin
        if (reset) begin
            state      <= IDLE;
            wr         <= 0;
            dac_out    <= 12'd0;
            cs_n       <= {N{1'b1}}; // All inactive
            dac_valid  <= 0;
            busy       <= 0;
            settle_cnt <= 0;
        end else begin
            case (state)
                IDLE: begin
                    wr        <= 0;
                    dac_valid <= 0;
                    busy      <= 0;
                    cs_n      <= {N{1'b1}};

                    if (start) begin
                        dac_out <= dac_data;
                        wr      <= 1;
                        busy    <= 1;

                        if (broadcast)
                            cs_n <= {N{1'b0}}; // All DACs selected
                        else
                            cs_n <= ~(1'b1 << dac_index); // Select one DAC

                        state <= WRITE;
                    end
                end

                WRITE: begin
                    wr         <= 0;
                    cs_n       <= {N{1'b1}}; // Deactivate all
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
