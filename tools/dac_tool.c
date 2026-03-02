#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <ncurses.h>

// --- CONFIGURATION ---
// CRITICAL: Update this to match the Address Editor in Vivado for the DAC peripheral
#define PHY_ADDR  0x80040000 
#define MAP_SIZE  4096UL
#define MAP_MASK  (MAP_SIZE - 1)

// Register Offsets (Based on your Verilog)
#define REG_DATA    0  // slv_reg0: Manual DAC Value (12-bit)
#define REG_CTRL    1  // slv_reg1: Control Bits (Mode, Enables)
#define REG_PRE     2  // slv_reg2: Clock Prescaler

// Control Bit Masks
#define MASK_MODE   (1 << 0) // Bit 0: 0=Passthrough, 1=Manual
#define MASK_EN0    (1 << 1) // Bit 1: Enable DAC 0 Clock
#define MASK_EN1    (1 << 2) // Bit 2: Enable DAC 1 Clock

int main() {
    int memfd;
    void *mapped_base, *virt_addr;
    volatile uint32_t *regs;

    // --- SETUP HARDWARE ---
    if ((memfd = open("/dev/mem", O_RDWR | O_SYNC)) == -1) {
        printf("Error: Could not open /dev/mem. Run as root.\n");
        return 1;
    }
    mapped_base = mmap(0, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, memfd, PHY_ADDR & ~MAP_MASK);
    if (mapped_base == (void *) -1) {
        printf("Error: mmap failed.\n");
        return 1;
    }
    virt_addr = mapped_base + (PHY_ADDR & MAP_MASK);
    regs = (volatile uint32_t *) virt_addr;

    // --- SETUP NCURSES ---
    initscr();
    cbreak();
    noecho();
    nodelay(stdscr, TRUE);
    curs_set(0);
    keypad(stdscr, TRUE); // Enable Arrow Keys

    // --- DRAW STATIC UI ---
    attron(A_BOLD);
    mvprintw(0, 0,  "=== LTC1666 DAC CONTROLLER (AXI) ===");
    attroff(A_BOLD);

    mvprintw(2, 2,  "DAC SOURCE:      [            ]");
    mvprintw(3, 2,  "DAC 0 CLOCK:     [     ]");
    mvprintw(4, 2,  "DAC 1 CLOCK:     [     ]");
    
    // Output Box
    mvprintw(6, 0,  "=== OUTPUT DATA ===");
    mvprintw(7, 2,  "MANUAL VALUE:    [      ] (0-4095)");
    mvprintw(8, 2,  "EST. VOLTAGE:    [      ] (0-4V Scale)");
    
    // Bar Graph
    mvprintw(10, 2, "0V [                                                           ] +4V");

    // Ramp Status
    mvprintw(12, 2, "RAMP MODE:       [     ]  Step: [          ]");

    // Timing Box
    mvprintw(14, 0, "=== TIMING ===");
    mvprintw(15, 2, "[P] Prescaler:   [      ]");
    mvprintw(16, 2, "    Calc Freq:   [          ] MHz");

    mvprintw(19, 0, "=== CONTROLS ===");
    mvprintw(20, 2, "'m'       : Toggle Mode (Manual / Passthrough)");
    mvprintw(21, 2, "'0' / '1' : Toggle DAC Channels");
    mvprintw(22, 2, "UP/DOWN   : Adjust Value (+/- 100)");
    mvprintw(23, 2, "LEFT/RIGHT: Fine Tune (+/- 1)");
    mvprintw(24, 2, "']' / '[' : Adjust Speed");
    mvprintw(25, 2, "'r'       : Toggle Ramp Mode (0->4095 sweep)");
    mvprintw(26, 2, "'q'       : Quit");
    refresh();

    // --- RAMP STATE ---
    int ramp_active = 0;
    uint32_t ramp_val = 0;
    int ramp_loops = 0;  // completed full sweeps

    int running = 1;
    while (running) {

        // --- RAMP MODE ---
        if (ramp_active) {
            // Write current ramp value
            regs[REG_DATA] = ramp_val;
            usleep(1); // ~1us settle time (kernel may round up to ~5-10us)

            // Advance
            ramp_val++;
            if (ramp_val > 4095) {
                ramp_val = 0;
                ramp_loops++;
            }

            // Update display only every 256 steps to keep ramp fast
            if ((ramp_val & 0xFF) == 0) {
                mvprintw(12, 20, "ON   ");
                mvprintw(12, 34, "%04u / %d", ramp_val, ramp_loops);
                int bars = (ramp_val * 60) / 4095;
                if (bars > 60) bars = 60;
                move(10, 5);
                for(int i=0; i<60; i++) {
                    if(i < bars) addch('#');
                    else addch(' ');
                }
                mvprintw(7, 20, "%04d", ramp_val);
                double voltage = ((double)ramp_val / 4095.0) * 4.0;
                mvprintw(8, 20, "%5.2f V", voltage);
                refresh();
            }

            // Non-blocking input check every step so we can quit/stop
            int ch = getch();
            if (ch != ERR) {
                switch(ch) {
                    case 'q': running = 0; break;
                    case 'r':
                        ramp_active = 0;
                        ramp_val = 0;
                        mvprintw(12, 20, "OFF  ");
                        mvprintw(12, 34, "          ");
                        refresh();
                        break;
                }
            }
            continue; // skip normal UI path during ramp
        }

        // --- NORMAL MODE ---

        // --- READ HARDWARE ---
        uint32_t raw_r0 = regs[REG_DATA]; // Value
        uint32_t raw_r1 = regs[REG_CTRL]; // Control
        uint32_t raw_r2 = regs[REG_PRE];  // Prescaler

        // Parse Control Bits
        int mode_manual = (raw_r1 & MASK_MODE);
        int en_0        = (raw_r1 & MASK_EN0);
        int en_1        = (raw_r1 & MASK_EN1);
        
        // Parse Value
        uint16_t dac_val = raw_r0 & 0x0FFF; // Mask to 12 bits
        
        // Calc Frequency
        double freq_mhz = 100.0 / (2.0 * (raw_r2 + 1));

        // --- UPDATE UI ---
        
        // 1. Status Labels
        mvprintw(2, 20, "%s", mode_manual ? "MANUAL (REG0)" : "PASSTHROUGH  ");
        
        if (en_0) { attron(A_REVERSE); mvprintw(3, 20, "ON   "); attroff(A_REVERSE); }
        else      { mvprintw(3, 20, "OFF  "); }

        if (en_1) { attron(A_REVERSE); mvprintw(4, 20, "ON   "); attroff(A_REVERSE); }
        else      { mvprintw(4, 20, "OFF  "); }

        // 2. Data Values
        mvprintw(7, 20, "%04d", dac_val);
        
        // Voltage Estimation (Unipolar: 0=0V, 4095=+4V)
        double voltage = ((double)dac_val / 4095.0) * 4.0;
        mvprintw(8, 20, "%5.2f V", voltage);

        // 3. Bar Graph
        // 0 to 4095 range mapping to 60 chars
        int bars = (dac_val * 60) / 4095;
        if (bars > 60) bars = 60;
        
        move(10, 5); // Inside brackets
        for(int i=0; i<60; i++) {
            if(i < bars) addch('#');
            else addch(' ');
        }

        // 4. Ramp status (off in normal mode)
        mvprintw(12, 20, "OFF  ");
        mvprintw(12, 34, "          ");

        // 5. Timing
        mvprintw(15, 20, "%-5u", raw_r2);
        mvprintw(16, 20, "%.2f", freq_mhz);

        refresh();

        // --- INPUT HANDLING ---
        int ch = getch();
        if (ch != ERR) {
            uint32_t next_val;
            switch(ch) {
                case 'q': running = 0; break;
                
                // Toggle Mode
                case 'm': regs[REG_CTRL] = raw_r1 ^ MASK_MODE; break;
                
                // Toggle Enables
                case '0': regs[REG_CTRL] = raw_r1 ^ MASK_EN0; break;
                case '1': regs[REG_CTRL] = raw_r1 ^ MASK_EN1; break;

                // Value Adjust (Manual Mode)
                case KEY_UP: 
                    next_val = dac_val + 100;
                    if(next_val > 4095) next_val = 4095;
                    regs[REG_DATA] = next_val;
                    break;
                case KEY_DOWN:
                    if(dac_val >= 100) next_val = dac_val - 100;
                    else next_val = 0;
                    regs[REG_DATA] = next_val;
                    break;
                case KEY_RIGHT:
                    if(dac_val < 4095) regs[REG_DATA] = dac_val + 1;
                    break;
                case KEY_LEFT:
                    if(dac_val > 0) regs[REG_DATA] = dac_val - 1;
                    break;

                // Speed Adjust
                case ']': // Slower (Increase divider)
                    regs[REG_PRE] = raw_r2 + 1; 
                    break;
                case '[': // Faster (Decrease divider)
                    if (raw_r2 > 0) regs[REG_PRE] = raw_r2 - 1; 
                    break;

                // Ramp Mode
                case 'r':
                    ramp_active = 1;
                    ramp_val = 0;
                    ramp_loops = 0;
                    break;
            }
        }
        usleep(100000); // 10 FPS is plenty for a controller
    }

    endwin();
    munmap(mapped_base, MAP_SIZE);
    close(memfd);
    return 0;
}