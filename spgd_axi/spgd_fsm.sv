`timescale 1ns / 1ps

module spgd_fsm (
    input  logic clk,
    input  logic rst_n,
    
    // AXI Control Signals from processor
    input  logic enable_loop,
    input  logic [15:0] settle_cycles, // programmable wait time
    
    // Control Signals to your Datapath
    output logic trigger_lfsr,
    output logic select_plus_minus,    // 1 = output u+du, 0 = output u-du
    output logic latch_j_plus,
    output logic latch_j_minus,
    output logic trigger_dsp_update,
    output logic commit_new_u
);

    // Define the states
    typedef enum logic [2:0] {
        IDLE          = 3'd0,
        GEN_PERTURB   = 3'd1,
        APPLY_PLUS    = 3'd2,
        WAIT_PLUS     = 3'd3,
        APPLY_MINUS   = 3'd4,
        WAIT_MINUS    = 3'd5,
        CALC_UPDATE   = 3'd6,
        COMMIT_UPDATE = 3'd7
    } state_t;

    state_t current_state, next_state;

    // Counter for the physical settling time
    logic [15:0] wait_counter;
    logic counter_done;

    // ==========================================
    // 1. State Register & Wait Counter
    // ==========================================
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            current_state <= IDLE;
            wait_counter  <= 16'd0;
        end else begin
            current_state <= next_state;
            
            // Manage the wait counter
            if (current_state == WAIT_PLUS || current_state == WAIT_MINUS) begin
                wait_counter <= wait_counter + 1;
            end else begin
                wait_counter <= 16'd0; // Reset counter in other states
            end
        end
    end

    assign counter_done = (wait_counter >= settle_cycles);

    // ==========================================
    // 2. Next State Logic
    // ==========================================
    always_comb begin
        // Default to staying in the current state
        next_state = current_state;

        case (current_state)
            IDLE: begin
                if (enable_loop) next_state = GEN_PERTURB;
            end
            
            GEN_PERTURB: begin
                next_state = APPLY_PLUS;
            end
            
            APPLY_PLUS: begin
                next_state = WAIT_PLUS;
            end
            
            WAIT_PLUS: begin
                if (counter_done) next_state = APPLY_MINUS;
            end
            
            APPLY_MINUS: begin
                next_state = WAIT_MINUS;
            end
            
            WAIT_MINUS: begin
                if (counter_done) next_state = CALC_UPDATE;
            end
            
            CALC_UPDATE: begin
                next_state = COMMIT_UPDATE;
            end
            
            COMMIT_UPDATE: begin
                if (enable_loop) next_state = GEN_PERTURB;
                else             next_state = IDLE;
            end
            
            default: next_state = IDLE;
        endcase
    end

    // ==========================================
    // 3. Output Logic
    // ==========================================
    always_comb begin
        trigger_lfsr       = 1'b0;
        select_plus_minus  = 1'b0; 
        latch_j_plus       = 1'b0;
        latch_j_minus      = 1'b0;
        trigger_dsp_update = 1'b0;
        commit_new_u       = 1'b0;

        case (current_state)
            GEN_PERTURB: trigger_lfsr = 1'b1;
            
            APPLY_PLUS:  select_plus_minus = 1'b1; // Mux selects (u + du)
            WAIT_PLUS:   select_plus_minus = 1'b1; // Hold mux during wait
            
            APPLY_MINUS: select_plus_minus = 1'b0; // Mux selects (u - du)
            WAIT_MINUS:  select_plus_minus = 1'b0; // Hold mux during wait
            
            CALC_UPDATE: trigger_dsp_update = 1'b1;
            
            COMMIT_UPDATE: commit_new_u = 1'b1;
            
            default: ; // All zero
        endcase

        // Latch the ADC values exactly on the last cycle of the wait states
        if (current_state == WAIT_PLUS && counter_done)  latch_j_plus = 1'b1;
        if (current_state == WAIT_MINUS && counter_done) latch_j_minus = 1'b1;
    end

endmodule