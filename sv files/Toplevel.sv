`timescale 1 ns / 1 ns
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 03/21/2025 06:25:20 PM
// Design Name: 
// Module Name: Toplevel
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


module Toplevel(
    input logic clk_in,
    input logic [15:0] DAC_in,
    input logic systemenable,
    input logic reset,
    input logic clk_reset,
    input logic [15:0] PM_index,
	input logic [15:0] g,
	input logic [15:0] orms,
	input logic [15:0] beta1,
	input logic [15:0] V2pi  /* ufix16_En12 */,
	input logic [15:0] max_iterations,
	input logic [3:0] epoch_bit_select,
    output logic clk_out,
    output logic ce_out,
    output logic [15:0] out_monitor,  /* ufix16_En11 */
    input  logic         dco,             
    input  logic [15:0]  data,           
    output vector_of_signed_logic_12 DAC_out [0:7] ,
    output logic [15:0] updated_dither_monitor1,
    output [7:0] wr,
    output logic         cnv,
    output logic         cnv2,
    output logic adc_fifo_wr_en0,
    output [2:0] state_out,
    output DAC_enable_out,
    output ADC1_enable_out,
    output logic [15:0] data_captured,
    output logic [15:0] PM0,
    output logic [15:0] PMP0,
    output logic [15:0] PMM0,
    output logic [15:0] dither0,
    output logic [15:0] delta_S
    );
    
    
	logic clk;
	logic clk_counter;
	logic clk_enable;
	logic flip_En;
	logic adc_fifo_wr_en;
	logic fifo_counter_reset;
	//logic  [15:0] g;
	logic [15:0] type_of_dither_to_load;
	logic [15:0] g_leakage;
	//logic [15:0] orms;
	//logic [15:0] max_iterations;
	//logic [15:0] V2pi;
	logic [15:0] system_check_enable;
	logic adc_clk;
	logic [24:0] adc_clk_counter;
	logic [5:0] adc_fifo_delay_counter;
	logic fifo_counter_start_en;
	logic [24:0] adc_clk_counter_cp;
	logic adc_clk_flip_En;
	logic adc_delay0;
	logic adc_delay1;
	logic adc_delay2;
	logic adc_delay3;
	logic cnv_delay0;
	logic edge_cnv;
	 
	assign clk_enable = 1'b1;
	assign type_of_dither_to_load = 16'b0100000000000000;
	//assign g = 16'b1000000000000000;
	assign g_leakage = 16'b1000000000000000;
	//assign orms = 16'b0100110011001101;
	//assign max_iterations = 16'b1111111111111111;
	//assign V2pi = 16'b0011101100110011;/*ufix16_12frac -*/
	always_ff @ (posedge clk_in) begin
	    if (clk_reset) begin
	        //clk <= 1'b1;
	        adc_clk_counter <= 1'b0;
	    end
	    else begin
	        //clk <= ~clk;
	        adc_clk_counter <= adc_clk_counter + 25'b1;
	        adc_clk_counter_cp <= adc_clk_counter;
	        if (adc_clk_flip_En == 1'b1) begin
	            adc_clk <= ~ adc_clk;
	        end
	    end
	    if (systemenable == 1'b1) begin
	        system_check_enable <= 16'b1000000000000000;
	        end
	    else begin
	        system_check_enable <= 16'b0000000000000000;
	        end
	end
	
	always_ff @ (posedge clk_in) begin
	    if (reset) begin
	        adc_fifo_wr_en <= 1'b0;
	        adc_delay0 <= 1'b0;
	        adc_delay1 <= 1'b0;
	        adc_delay2 <= 1'b0;
	        adc_delay3 <= 1'b0;
	        cnv_delay0 <= 1'b0;
	    end
	    else begin
	        adc_fifo_wr_en <= adc_delay0;
	        adc_delay0 <= adc_delay1;
	        adc_delay1 <= adc_delay2;
	        adc_delay2 <= adc_delay3;
	        adc_delay3 <= edge_cnv;
	        cnv_delay0 <= cnv;
	    end
	end
	
	assign edge_cnv = ~cnv && (cnv_delay0);
	/*
	always_ff @ (posedge clk_in) begin
	    if (reset) begin
	        adc_fifo_wr_en <= 1'b0;
	    end
	    else begin
	        if (flip_En) begin
	            adc_fifo_wr_en <= 1'b1;
	        end
	        else begin
	            adc_fifo_wr_en <= 1'b0;
	        end
	    end
	end
	
	always_ff @ (posedge clk_in) begin
	    if (reset) begin
	        fifo_counter_start_en <= 1'b0;
	    end
	    else begin
	        if (cnv) begin
	            fifo_counter_start_en <= 1'b1;
	        end
	        else begin
	        if (fifo_counter_reset) begin
	            fifo_counter_start_en <= 1'b0;
	            end
	        end
	    end
	end
	
	always_ff @ (posedge clk_in) begin
	    if (reset) begin
	        adc_fifo_delay_counter <= 5'b0;
	    end
	    else begin
	        if (fifo_counter_start_en) begin
	            adc_fifo_delay_counter <= adc_fifo_delay_counter + 5'b1;
	        end
	        else begin
	            adc_fifo_delay_counter <= 5'b0;
	        end
	    end
	end
	*/
	always_comb begin
	    adc_clk_flip_En = adc_clk_counter_cp[0] == 1'b1;
	    //flip_En = adc_fifo_delay_counter == 5'b00100;
	    //fifo_counter_reset = adc_fifo_delay_counter == 5'b00100;
	end
	// assign clk = adc_clk;
	assign clk = clk_in;
    Subsystem subsystem1
          (.*);
    assign clk_out = adc_clk;
    assign adc_fifo_wr_en0 = adc_fifo_wr_en;
    
    // assign clk_adc_out = clk;
endmodule
