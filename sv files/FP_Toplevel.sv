`timescale 1ns / 1ps
import Subsystem_pkg::* ;
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/26/2025 02:42:53 PM
// Design Name: 
// Module Name: FP_Toplevel
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////
module FP_Toplevel(
	input  wire [4:0]   okUH,
	output wire [2:0]   okHU,
	inout  wire [31:0]  okUHU,
	inout  wire         okAA,
 
	input  logic         dco_in,                     
    input  logic [15:0]  data,
    output logic         cnv,
    output vector_of_signed_logic_12 DAC_out_pin [0:6],
    output [7:0] wr_ch0       ,
    output [7:0] wr_ch1,
    output logic ADC_output_enable ,
    output logic ADC_clk_select
	);
//main logic wires to be passed to Toplevel
logic clk_in;
logic [15:0] debug;
//logic cnv;
logic cnv2;
logic [7:0] wr;
logic [7:0] wr_delayed0;
logic [7:0] wr_delayed1;
logic [7:0] wr_shifted0;
logic [7:0] wr_shifted1;
logic [15:0] DAC_in;
logic dco;
logic dco_ibuf;
logic systemenable;
logic reset;
logic clk_reset;
logic clk_out;
logic ce_out;
logic [15:0] PM_index;
logic [15:0] g;
logic [15:0] orms;
logic [15:0] beta1;
logic [15:0] max_iterations;
logic [15:0] out_monitor;
logic [15:0] updated_dither_monitor1;
logic [15:0] dout;
logic [15:0] dout1;
logic [15:0] dout2;
logic [15:0] data_captured;
logic [15:0] PM0;
logic [15:0] PMP0;
logic [15:0] PMM0;
logic [15:0] dither0;
logic [15:0] delta_S;
logic [2:0] state_out;
logic [15:0] V2pi;
logic [3:0] epoch_bit_select;
logic DAC_enable_out;
logic ADC1_enable_out;
logic adc_fifo_wr_en0;
logic adc_fifo_rd_en0;
logic PM_fifo_rd_en0;
logic PMP_fifo_rd_en0;
logic PMM_fifo_rd_en0;
logic dither_adc_fifo_rd_en0;
logic gated_read0;
logic gated_read1;
logic gated_read2;
logic [11:0] fifo_status_counter;
logic full;
logic full1;
logic full2;
logic empty;
logic empty1;
logic empty2;
logic gated_read_PMP;
logic [15:0] dout_PMP;
logic full_PMP;
logic empty_PMP;
logic gated_read_PMM;
logic [15:0] dout_PMM;
logic full_PMM;
logic empty_PMM;
logic manual_wr;
logic epA5read;
logic epA4read;
logic epA3read;
logic epA2read;
logic epA1read;
vector_of_signed_logic_12 DAC_out [0:7];
vector_of_signed_logic_12 DAC_out_4_slots [0:3];

// Target interface bus:
wire         okClk;
wire [112:0] okHE;
wire [64:0]  okEH;

// Endpoint connections:
wire [31:0]  ep00wire;
wire [31:0]  ep01wire;
wire [31:0]  ep02wire;
wire [31:0]  ep03wire;
wire [31:0]  ep04wire;
wire [31:0]  ep05wire;
wire [31:0]  ep06wire;
wire [31:0]  ep07wire;
wire [31:0]  ep20wire;
reg  [31:0]  ep21wire;
reg  [31:0]  ep22wire;
reg  [31:0]  ep23wire;
reg  [31:0]  ep24wire;
reg  [31:0]  ep25wire;
reg  [31:0]  ep26wire;
logic [31:0] epA5pipe;
logic [31:0] epA4pipe;
logic [31:0] epA3pipe;
logic [31:0] epA2pipe;
logic [31:0] epA1pipe;

//assign DAC_out_pin = DAC_out[1:7];
assign DAC_out_pin[2:4] = DAC_out_4_slots[1:3];
assign DAC_out_pin[0] = DAC_out_4_slots[0];
assign clk_in = okClk;
assign wr_ch0 = wr_shifted0;
assign wr_ch1 = wr_shifted1;
assign PMM_fifo_rd_en0 = epA5read;
assign PMP_fifo_rd_en0 = epA4read;
assign adc_fifo_rd_en0 = epA3read;
assign PM_fifo_rd_en0 = epA2read;
assign dither_adc_fifo_rd_en0 = epA1read;
assign debug = {15'b0, cnv};
assign gated_read0 = adc_fifo_rd_en0 && (~empty);
assign gated_read1 = PM_fifo_rd_en0 && (~empty1);
assign gated_read2 = dither_adc_fifo_rd_en0 && (~empty2);
assign gated_read_PMP = PMP_fifo_rd_en0 && (~empty_PMP);
assign gated_read_PMM = PMM_fifo_rd_en0 && (~empty_PMM);
assign ADC_output_enable = 1'b1;
assign ADC_clk_select = 1'b0;

//assign led[0] = ~dco_in;
// assign clk_adc_out = 1'b0;

assign clk_reset = ep00wire[0];
assign reset = ep00wire[1];
assign systemenable = ep00wire[2];
assign g = ep01wire[15:0];
assign orms = ep02wire[15:0];
assign max_iterations = ep03wire[15:0];
assign V2pi = ep04wire[15:0]; 
assign manual_wr = ep05wire[0]; 
assign beta1 = 16'b0;
assign PM_index = ep06wire[15:0];
assign epoch_bit_select = ep07wire[3:0];
assign ep20wire[0] = clk_out;
assign ep21wire[15:0] = out_monitor;
assign ep22wire[11:0] = DAC_out_pin[1]; //updated_dither_monitor1
assign ep22wire[27:16] = DAC_out_pin[2]; //updated_dither_monitor2
assign ep23wire[11:0] = DAC_out_pin[3]; //updated_dither_monitor3
assign ep23wire[27:16] = DAC_out_pin[4]; //updated_dither_monitor4
assign ep24wire[2:0] = state_out;
assign ep25wire[15:0] =  data;
assign ep26wire[0] = full;
assign epA5pipe[15:0] = dout_PMM;
assign epA4pipe[15:0] = dout_PMP;
assign epA3pipe[15:0] = dout;
assign epA2pipe[15:0] = dout1;
assign epA1pipe[15:0] = dout2;


//assign differential signal conversion for clk and dco
//OBUFDS #(.IOSTANDARD("LVDS_25")) obufds_clk_inst(.I(dco), .O(dco_p), .OB(dco_n));
//OBUFDS #(.IOSTANDARD("LVDS_25")) obufds_clk_inst(.I(dco), .O(dco_p), .OB(dco_n));
//IBUF ibuf_inst(.I(dco_in), .O(dco_ibuf));
//BUFG bufg_inst(.I(dco_ibuf), .O(dco));
assign dco = dco_in;
/*
logic [3:0] channel_write_cnt;
logic [1:0] DAC_write_states;
always_ff @ (posedge clk_in or posedge reset) begin
    if (reset) begin
        DAC_write_states <= 2'b0;
    end
    else begin
        if (DAC_write_states == 2'b00) begin
            if (wr == 8'b11111111) begin
                DAC_write_states <= 2'b01;
            end
            else begin
                DAC_write_states <= 2'b00;
            end
        end
        else if (DAC_write_states == 2'b01) begin
            DAC_write_states <= 2'b11;
        end
        else if (DAC_write_states == 2'b10) begin
            DAC_write_states <= 2'b00;
        end
        else begin
            if (channel_write_cnt == 5'b1) begin
                DAC_write_states <= 2'b10;
            end
            else begin
                DAC_write_states <= 2'b11;
            end
        end
    end
end

always_ff @ (posedge clk_in or posedge reset) begin
    if (reset) begin
        wr_delayed0 <= 8'b0;
        wr_delayed1 <= 8'b0;
        wr_shifted0 <= 8'b0;
        wr_shifted1 <= 8'b0;
        DAC_out_4_slots <= '{4{12'sb000000000000}};
        channel_write_cnt <= 5'b0;
    end
    else begin
        if (DAC_write_states == 2'b00) begin
            DAC_out_4_slots <= DAC_out_4_slots;
            wr_delayed0 <= 8'b0;
            wr_delayed1 <= 8'b0;
            channel_write_cnt <= 5'b0;
        end
        else if (DAC_write_states == 2'b01) begin
            DAC_out_4_slots <= DAC_out[0:3];
            wr_delayed0 <= 8'b11111111;
            wr_delayed1 <= 8'b0;
            channel_write_cnt <= 5'b00111;
        end
        else if (DAC_write_states == 2'b10) begin
            DAC_out_4_slots <= DAC_out[4:7];
            wr_delayed0 <= 8'b0;
            wr_delayed1 <= 8'b11111111;
            channel_write_cnt <= 5'b0;
        end
        else begin
            DAC_out_4_slots <= DAC_out_4_slots;
            wr_delayed0 <= 8'b0;
            wr_delayed1 <= 8'b0;
            channel_write_cnt <= channel_write_cnt - 5'b1;
        end
        if (manual_wr) begin
            wr_shifted0 <= wr_delayed0;
            wr_shifted1 <= wr_delayed1;
        end
        else begin
            wr_shifted0 <= 8'b0;
            wr_shifted1 <= 8'b0;
        end
    end
end
*/
logic [127:0] wr_delay_block;
logic wr_edge;
logic wr_delay;
assign wr_edge = wr[0] && ~wr_delay;
always_ff @ (posedge clk_in or posedge reset) begin
    if (reset) begin
        wr_delay <= 1'b0;
        wr_delayed0 <= 8'b0;
        wr_delayed1 <= 8'b0;
        wr_shifted0 <= 8'b0;
        wr_shifted1 <= 8'b0;
        DAC_out_4_slots <= '{4{12'sb000000000000}};
        wr_delay_block <= 128'b0;
    end
    else begin
        wr_delay <= wr[0];
        wr_delay_block[0] <= wr_edge;
        for (int i = 1; i < 128; i++) begin
            wr_delay_block[i] <= wr_delay_block[i-1];
        end
        if (wr_delay_block[7]) begin
            //DAC_out_4_slots <= DAC_out[4:7];
            DAC_out_4_slots[0] <= DAC_out[1];
            DAC_out_4_slots[1] <= DAC_out[3];
            DAC_out_4_slots[2] <= DAC_out[5];
            DAC_out_4_slots[3] <= DAC_out[7];
            /* DAC_out_4_slots[0] <= DAC_out[7];
            DAC_out_4_slots[1] <= DAC_out[5];
            DAC_out_4_slots[2] <= DAC_out[3];
            DAC_out_4_slots[3] <= DAC_out[1];*/
            wr_delayed0 <= 8'b0;
            wr_delayed1 <= 8'b0;
        end
        else if (wr_delay_block[15]) begin
            wr_delayed0 <= 8'b0;
            wr_delayed1 <= 8'b11111111;
        end
        else if (wr_delay_block[19]) begin
            //DAC_out_4_slots <= DAC_out[0:3];
            DAC_out_4_slots[0] <= DAC_out[0];
            DAC_out_4_slots[1] <= DAC_out[2];
            DAC_out_4_slots[2] <= DAC_out[4];
            DAC_out_4_slots[3] <= DAC_out[6];
            /*DAC_out_4_slots[0] <= DAC_out[6];
            DAC_out_4_slots[1] <= DAC_out[4];
            DAC_out_4_slots[2] <= DAC_out[2];
            DAC_out_4_slots[3] <= DAC_out[0];*/
            wr_delayed0 <= 8'b0;
            wr_delayed1 <= 8'b0;
        end
        else if (wr_delay_block[27]) begin
            wr_delayed0 <= 8'b11111111;
            wr_delayed1 <= 8'b0;
        end
        else begin
            wr_delayed0 <= 8'b0;
            wr_delayed1 <= 8'b0;
        end
            
        if (manual_wr) begin
            wr_shifted0 <= wr_delayed0;
            wr_shifted1 <= wr_delayed1;
        end
        else begin
            wr_shifted0 <= 8'b0;
            wr_shifted1 <= 8'b0;
        end
    end
end
//Instantiate FIFO for adc data memory
fifo_generator_0 adc_fifo_1 (
  .clk(clk_in),      // input wire clk
  .srst(reset),    // input wire srst
  .din(data_captured),      // input wire [15 : 0] din
  .wr_en(adc_fifo_wr_en0),  // input wire wr_en
  .rd_en(gated_read0),  // input wire rd_en
  .dout(dout),    // output wire [15 : 0] dout
  .full(full),    // output wire full
  .empty(empty)  // output wire empty
);

fifo_generator_0 PM_fifo_1 (
  .clk(clk_in),      // input wire clk
  .srst(reset),    // input wire srst
  .din(PM0),      // input wire [15 : 0] din
  .wr_en(adc_fifo_wr_en0),  // input wire wr_en
  .rd_en(gated_read1),  // input wire rd_en
  .dout(dout1),    // output wire [15 : 0] dout
  .full(full1),    // output wire full
  .empty(empty1)  // output wire empty
);

fifo_generator_0 dither_fifo_1 (
  .clk(clk_in),      // input wire clk
  .srst(reset),    // input wire srst
  .din(dither0),      // input wire [15 : 0] din
  .wr_en(adc_fifo_wr_en0),  // input wire wr_en
  .rd_en(gated_read2),  // input wire rd_en
  .dout(dout2),    // output wire [15 : 0] dout
  .full(full2),    // output wire full
  .empty(empty2)  // output wire empty
);



fifo_generator_0 PM_plus_fifo_1 (
  .clk(clk_in),      // input wire clk
  .srst(reset),    // input wire srst
  .din(PMP0),      // input wire [15 : 0] din
  .wr_en(adc_fifo_wr_en0),  // input wire wr_en
  .rd_en(gated_read_PMP),  // input wire rd_en
  .dout(dout_PMP),    // output wire [15 : 0] dout
  .full(full_PMP),    // output wire full
  .empty(empty_PMP)  // output wire empty
);


fifo_generator_0 PM_minus_fifo_1 (
  .clk(clk_in),      // input wire clk
  .srst(reset),    // input wire srst
  .din(PMM0),      // input wire [15 : 0] din
  .wr_en(adc_fifo_wr_en0),  // input wire wr_en
  .rd_en(gated_read_PMM),  // input wire rd_en
  .dout(dout_PMM),    // output wire [15 : 0] dout
  .full(full_PMM),    // output wire full
  .empty(empty_PMM)  // output wire empty
);
// Instantiate the okHost and connect endpoints.
wire [65*12-1:0]  okEHx;
okHost okHI(
	.okUH(okUH),
	.okHU(okHU),
	.okUHU(okUHU),
	.okAA(okAA),
	.okClk(okClk),
	.okHE(okHE), 
	.okEH(okEH)
);

Toplevel top1 (.*);

okWireOR # (.N(12)) wireOR (okEH, okEHx);

okWireIn     ep00 (.okHE(okHE),                             .ep_addr(8'h00), .ep_dataout(ep00wire));
okWireIn     ep01 (.okHE(okHE),                             .ep_addr(8'h01), .ep_dataout(ep01wire));
okWireIn     ep02 (.okHE(okHE),                             .ep_addr(8'h02), .ep_dataout(ep02wire));
okWireIn     ep03 (.okHE(okHE),                             .ep_addr(8'h03), .ep_dataout(ep03wire));
okWireIn     ep04 (.okHE(okHE),                             .ep_addr(8'h04), .ep_dataout(ep04wire));
okWireIn     ep05 (.okHE(okHE),                             .ep_addr(8'h05), .ep_dataout(ep05wire));
okWireIn     ep06 (.okHE(okHE),                             .ep_addr(8'h06), .ep_dataout(ep06wire));
okWireIn     ep07 (.okHE(okHE),                             .ep_addr(8'h07), .ep_dataout(ep07wire));
okWireOut    ep20 (.okHE(okHE), .okEH(okEHx[ 0*65 +: 65 ]), .ep_addr(8'h20), .ep_datain(ep20wire));
okWireOut    ep21 (.okHE(okHE), .okEH(okEHx[ 1*65 +: 65 ]), .ep_addr(8'h21), .ep_datain(ep21wire));
okWireOut    ep22 (.okHE(okHE), .okEH(okEHx[ 2*65 +: 65 ]), .ep_addr(8'h22), .ep_datain(ep22wire));
okWireOut    ep23 (.okHE(okHE), .okEH(okEHx[ 3*65 +: 65 ]), .ep_addr(8'h23), .ep_datain(ep23wire));
okWireOut    ep24 (.okHE(okHE), .okEH(okEHx[ 4*65 +: 65 ]), .ep_addr(8'h24), .ep_datain(ep24wire));
okWireOut    ep25 (.okHE(okHE), .okEH(okEHx[ 5*65 +: 65 ]), .ep_addr(8'h25), .ep_datain(ep25wire));
okWireOut    ep26 (.okHE(okHE), .okEH(okEHx[ 6*65 +: 65 ]), .ep_addr(8'h26), .ep_datain(ep26wire));

okPipeOut pipeOutA5 (.okHE(okHE), .okEH(okEHx[ 11*65 +: 65 ]),.ep_addr(8'ha5), .ep_datain(epA5pipe), .ep_read(epA5read)); //adc data
okPipeOut pipeOutA4 (.okHE(okHE), .okEH(okEHx[ 10*65 +: 65 ]),.ep_addr(8'ha4), .ep_datain(epA4pipe), .ep_read(epA4read)); //adc data
okPipeOut pipeOutA3 (.okHE(okHE), .okEH(okEHx[ 7*65 +: 65 ]),.ep_addr(8'ha3), .ep_datain(epA3pipe), .ep_read(epA3read)); //adc data
okPipeOut pipeOutA2 (.okHE(okHE), .okEH(okEHx[ 8*65 +: 65 ]),.ep_addr(8'ha2), .ep_datain(epA2pipe), .ep_read(epA2read)); //phase shifter 0 data
okPipeOut pipeOutA1 (.okHE(okHE), .okEH(okEHx[ 9*65 +: 65 ]),.ep_addr(8'ha1), .ep_datain(epA1pipe), .ep_read(epA1read)); //dither 0 data

endmodule


