module ltc2387_16_interface (
    input  wire        dco,             // Data Clock Out (single-ended)
    input  wire        data1,           // Data Lane 1 (odd bits)
    input  wire        data2,           // Data Lane 2 (even bits)
    input  wire        cnv,             // Conversion start signal
    input  wire        reset,           // Active-high reset
    output wire [15:0] adc_data_out,    // Reconstructed 16-bit ADC output
    output wire        adc_data_valid,  // High when new data is valid
    input  wire        sys_clk          // System clock for output sync
);

    // FSM states
    localparam IDLE      = 2'd0;
    localparam WAIT_LAT  = 2'd1;
    localparam CAPTURE   = 2'd2;

    reg [1:0] state = IDLE;
    reg [3:0] bit_cnt = 0;
    reg [2:0] lat_cnt = 0;

    reg [7:0] shift_lane1 = 0;
    reg [7:0] shift_lane2 = 0;
    reg [15:0] adc_data = 0;
    reg        data_ready = 0;

    reg cnv_d = 0;
    wire cnv_rising = cnv & ~cnv_d;

    // Interleaving logic
    integer i;
    reg [15:0] reconstructed_data;

    always @* begin
        for (i = 0; i < 8; i = i + 1) begin
            reconstructed_data[2*i+1] = shift_lane1[i]; // D[15], D[13], ..., D[1]
            reconstructed_data[2*i]   = shift_lane2[i]; // D[14], D[12], ..., D[0]
        end
    end

    // Main state machine
    always @(posedge dco or posedge reset) begin
        if (reset) begin
            state       <= IDLE;
            bit_cnt     <= 0;
            lat_cnt     <= 0;
            shift_lane1 <= 0;
            shift_lane2 <= 0;
            adc_data    <= 0;
            data_ready  <= 0;
            cnv_d       <= 0;
        end else begin
            cnv_d <= cnv;

            case (state)
                IDLE: begin
                    data_ready <= 0;
                    if (cnv_rising) begin
                        state <= WAIT_LAT;
                        lat_cnt <= 0;
                    end
                end

                WAIT_LAT: begin
                    lat_cnt <= lat_cnt + 1;
                    if (lat_cnt == 3) begin
                        state <= CAPTURE;
                        bit_cnt <= 0;
                    end
                end

                CAPTURE: begin
                    shift_lane1 <= {shift_lane1[6:0], data1};
                    shift_lane2 <= {shift_lane2[6:0], data2};
                    bit_cnt <= bit_cnt + 1;

                    if (bit_cnt == 4'd7) begin  // 8 bits per lane
                        adc_data <= reconstructed_data;
                        data_ready <= 1;
                        state <= IDLE;
                    end else begin
                        data_ready <= 0;
                    end
                end
            endcase
        end
    end

    // Cross into sys_clk domain
    reg [15:0] adc_data_sync = 0;
    reg        adc_data_valid_sync = 0;

    always @(posedge sys_clk or posedge reset) begin
        if (reset) begin
            adc_data_sync <= 0;
            adc_data_valid_sync <= 0;
        end else begin
            if (data_ready) begin
                adc_data_sync <= adc_data;
                adc_data_valid_sync <= 1;
            end else begin
                adc_data_valid_sync <= 0;
            end
        end
    end

    assign adc_data_out = adc_data_sync;
    assign adc_data_valid = adc_data_valid_sync;

endmodule
