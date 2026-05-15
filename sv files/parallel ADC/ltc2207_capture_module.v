module ltc2207_capture_module (
    input              adc_clkout,  // ADC clock
    input              sample_in,   // External async sample trigger
    input              reset_in,    // External async reset
    input      [15:0]  din,        // ADC data input
    output     [15:0]  dout,        // Latched data output
    output             busy         // High while sampling in progress
);

    // ------------------------
    // Synchronize sample_in
    // ------------------------
    reg sample_sync1, sample_sync2;
    always @(posedge adc_clkout) begin
        sample_sync1 <= sample_in;
        sample_sync2 <= sample_sync1;
    end
    wire sample_s;
    assign sample_s = sample_sync2;

    // ------------------------
    // Synchronize reset_in
    // ------------------------
    reg reset_sync1, reset_sync2;
    always @(posedge adc_clkout) begin
        reset_sync1 <= reset_in;
        reset_sync2 <= reset_sync1;
    end
    wire reset_s = reset_sync2;

    // ------------------------
    // SR Latch
    // ------------------------
    wire latch_pulse;
    wire acquire = sample_s & ~busy;
    reg sr_q;
    always @(posedge adc_clkout or posedge reset_s) begin
        if (reset_s)
            sr_q <= 1'b0;
        else if (latch_pulse)
            sr_q <= 1'b0;
        else if (acquire)
            sr_q <= 1'b1;
    end
    assign busy = sr_q;

    // ------------------------
    // Falling Edge Counter
    // ------------------------
    reg [3:0] count;
    wire count_en = sr_q;
    wire count_rst = reset_s | ~sr_q;

    always @(negedge adc_clkout or posedge count_rst) begin
        if (count_rst)
            count <= 4'd0;
        else if (count_en)
            count <= count + 1'b1;
    end

    // ------------------------
    // Comparator
    // ------------------------
    wire a_eq_b = (count == 4'd7);

    // ------------------------
    // Latch Pulse (1-cycle)
    // ------------------------
    assign latch_pulse = a_eq_b & adc_clkout;

    // ------------------------
    // Data Latch if (latch_pulse)
    // ------------------------
    reg [15:0] dout_reg;
    always @(posedge adc_clkout or posedge reset_s) begin
        if (reset_s)
            dout_reg <= 16'd0;
        else begin
            dout_reg <= din;
        end
    end
    assign dout = dout_reg;

endmodule
