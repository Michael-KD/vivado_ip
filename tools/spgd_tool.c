#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <ncurses.h>

// Base Address (Match your Vivado Address Editor)
#define PHY_ADDR  0x80000000 
#define MAP_SIZE  4096UL
#define MAP_MASK  (MAP_SIZE - 1)

// Register Offsets (32-bit words)
#define REG_CTRL   0 // slv_reg0: [0]=enable
#define REG_CONFIG 1 // slv_reg1: [15:0]=settle, [31:16]=amp
#define REG_GAMMA  2 // slv_reg2: [31:0]=gamma_lr

int main() {
    int memfd;
    void *mapped_base, *virt_addr;
    volatile uint32_t *regs;

    // --- SETUP HARDWARE ---
    if ((memfd = open("/dev/mem", O_RDWR | O_SYNC)) == -1) {
        printf("Error: Run as root (sudo).\n");
        return 1;
    }
    mapped_base = mmap(0, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, memfd, PHY_ADDR & ~MAP_MASK);
    if (mapped_base == (void *) -1) return 1;
    virt_addr = mapped_base + (PHY_ADDR & MAP_MASK);
    regs = (volatile uint32_t *) virt_addr;

    // --- SETUP NCURSES ---
    initscr();
    cbreak();
    noecho();
    nodelay(stdscr, TRUE);
    curs_set(0);
    keypad(stdscr, TRUE);

    // --- DRAW STATIC UI ---
    attron(A_BOLD);
    mvprintw(0, 0,  "=== SPGD CONTROLLER ===");
    attroff(A_BOLD);

    mvprintw(2, 2,  "STATUS:         [   ]");
    mvprintw(3, 2,  "PASSTHROUGH:    [   ]");
    mvprintw(4, 2,  "AUTO-RESET:     [   ]");
    mvprintw(6, 2,  "SETTLE CYCLES:  [      ]"); 
    mvprintw(7, 2,  "PERTURB AMP:    [      ]");
    mvprintw(8, 2,  "GAMMA (LR):     [          ]");
    mvprintw(9, 2,  "RESET PERIOD:   [      ] ms");

    mvprintw(12, 0, "=== CONTROLS ===");
    mvprintw(13, 2, "'e'       : Toggle Enable Loop");
    mvprintw(14, 2, "'t'       : Toggle Passthrough Mode");
    mvprintw(15, 2, "'r'       : One-shot DAC Reset (mid-scale)");
    mvprintw(16, 2, "'R'       : Toggle Auto-Reset Mode");
    mvprintw(17, 2, "'s' / 'S' : -/+ Settle Cycles (10)");
    mvprintw(18, 2, "'p' / 'P' : -/+ Perturb Amp   (100)");
    mvprintw(19, 2, "'g' / 'G' : -/+ Gamma LR      (100)");
    mvprintw(20, 2, "'d' / 'D' : -/+ Reset Period   (50 ms)");
    mvprintw(21, 2, "'q'       : Quit");
    refresh();

    int running = 1;
    int auto_reset = 0;         // Auto-reset mode off by default
    int reset_period_ms = 500;  // Default auto-reset period (ms)
    int loop_elapsed_ms = 0;    // Tracks time since last reset
    while (running) {
        // --- READ HARDWARE ---
        uint32_t raw_ctrl   = regs[REG_CTRL];
        uint32_t raw_config = regs[REG_CONFIG];
        uint32_t raw_gamma  = regs[REG_GAMMA];

        // --- PARSE FIELDS ---
        int enabled       = raw_ctrl & 0x1;
        int passthrough   = (raw_ctrl >> 1) & 0x1;
        int settle_cycles = raw_config & 0xFFFF;
        int perturb_amp   = (raw_config >> 16) & 0xFFFF;
        int gamma_lr      = raw_gamma; // Assuming integer representation or fixed point

        // --- DRAW DYNAMIC VALUES ---
        
        // 1. Status
        if (enabled) {
            attron(A_REVERSE | A_BOLD);
            mvprintw(2, 19, "ON ");
            attroff(A_REVERSE | A_BOLD);
        } else {
            mvprintw(2, 19, "OFF");
        }

        // 2. Passthrough Mode
        if (passthrough) {
            attron(A_REVERSE | A_BOLD);
            mvprintw(3, 19, "ON ");
            attroff(A_REVERSE | A_BOLD);
        } else {
            mvprintw(3, 19, "OFF");
        }

        // 3. Auto-Reset Mode
        if (auto_reset) {
            attron(A_REVERSE | A_BOLD);
            mvprintw(4, 19, "ON ");
            attroff(A_REVERSE | A_BOLD);
        } else {
            mvprintw(4, 19, "OFF");
        }

        // 4. Parameters
        mvprintw(6, 19, "%-6d", settle_cycles);
        mvprintw(7, 19, "%-6d", perturb_amp);
        mvprintw(8, 19, "%-10d", gamma_lr);
        mvprintw(9, 19, "%-6d", reset_period_ms);

        refresh();

        // --- INPUT HANDLING ---
        int ch = getch();
        if (ch != ERR) {
            switch(ch) {
                case 'q': running = 0; break;
                
                // Toggle Enable
                case 'e': 
                    regs[REG_CTRL] = raw_ctrl ^ 0x01; 
                    break;

                // Toggle Passthrough Mode
                case 't': 
                    regs[REG_CTRL] = raw_ctrl ^ 0x02; 
                    break;

                // Settle Cycles (Lower 16 of REG_CONFIG)
                case 's': { // Decrease
                    int new_val = (settle_cycles >= 10) ? settle_cycles - 10 : 0;
                    regs[REG_CONFIG] = (perturb_amp << 16) | new_val;
                    break;
                }
                case 'S': { // Increase
                    int new_val = (settle_cycles <= 0xFFF5) ? settle_cycles + 10 : 0xFFFF;
                    regs[REG_CONFIG] = (perturb_amp << 16) | new_val;
                    break;
                }

                // Perturbation Amplitude (Upper 16 of REG_CONFIG)
                case 'p': { // Decrease
                    int new_val = (perturb_amp >= 100) ? perturb_amp - 100 : 0;
                    regs[REG_CONFIG] = (new_val << 16) | settle_cycles;
                    break;
                }
                case 'P': { // Increase
                    int new_val = (perturb_amp <= 0xFF00) ? perturb_amp + 100 : 0xFFFF;
                    regs[REG_CONFIG] = (new_val << 16) | settle_cycles;
                    break;
                }

                // Gamma / Learning Rate (REG_GAMMA)
                case 'g': // Decrease
                    if (gamma_lr > 100) regs[REG_GAMMA] = gamma_lr - 100;
                    else regs[REG_GAMMA] = 0;
                    break;
                case 'G': // Increase
                    regs[REG_GAMMA] = gamma_lr + 100;
                    break;

                // One-shot DAC soft reset (pulse bit 2)
                case 'r': {
                    regs[REG_CTRL] = raw_ctrl | 0x04;  // Set bit 2
                    usleep(1000);                       // Hold ~1us
                    regs[REG_CTRL] = raw_ctrl & ~0x04;  // Clear bit 2
                    break;
                }

                // Toggle auto-reset mode
                case 'R':
                    auto_reset = !auto_reset;
                    loop_elapsed_ms = 0;
                    break;

                // Adjust reset period
                case 'd': // Decrease
                    if (reset_period_ms > 50) reset_period_ms -= 50;
                    break;
                case 'D': // Increase
                    reset_period_ms += 50;
                    break;
            }
        }
        // --- AUTO-RESET LOGIC ---
        if (auto_reset) {
            loop_elapsed_ms += 50; // Each loop iteration is ~50ms
            if (loop_elapsed_ms >= reset_period_ms) {
                uint32_t cur_ctrl = regs[REG_CTRL];
                regs[REG_CTRL] = cur_ctrl | 0x04;   // Assert soft_reset (bit 2)
                usleep(1000);                        // Brief pulse
                regs[REG_CTRL] = cur_ctrl & ~0x04;   // Deassert soft_reset
                loop_elapsed_ms = 0;
            }
        }

        usleep(50000); // 20 FPS
    }

    endwin();
    munmap(mapped_base, MAP_SIZE);
    close(memfd);
    return 0;
}
