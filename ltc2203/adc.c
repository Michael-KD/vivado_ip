#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <ncurses.h>

// Base Address (Match your Vivado Address Editor)
#define PHY_ADDR  0x80030000 
#define MAP_SIZE  4096UL
#define MAP_MASK  (MAP_SIZE - 1)

// Register Offsets
#define REG_DATA  0
#define REG_CTRL  1
#define REG_PRE   2

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

    // --- DRAW STATIC UI ---
    attron(A_BOLD);
    mvprintw(0, 0,  "=== LTC2203 ADC CONTROLLER (2's COMPLEMENT) ===");
    attroff(A_BOLD);

    mvprintw(2, 2,  "ADC VALUE:      [     ]  (           )"); 
    mvprintw(3, 2,  "ADC OVERFLOW:   [    ]");
    
    // Bar graph background: Left is -10V, Middle is 0V, Right is +10V
    mvprintw(5, 2, "-10V [                                                            ] +10V");
    // Draw a small tick mark at the center (approx char 32 inside brackets) to mark 0V
    mvprintw(6, 32, "^ 0V"); 

    mvprintw(8, 0,  "=== HARDWARE REGISTERS ===");
    mvprintw(10, 2, "[O] Output Enable:   [   ]");
    mvprintw(11, 2, "[C] Clock Source:    [        ]");
    mvprintw(12, 2, "[P] Clock Prescaler: [   ]");
    mvprintw(13, 2, "    Calc. Frequency: [         ]");

    mvprintw(16, 0, "=== CONTROLS ===");
    mvprintw(17, 2, "'o' : Toggle Output Enable");
    mvprintw(18, 2, "'c' : Toggle Clock Source");
    mvprintw(19, 2, "'+' : Increase Speed");
    mvprintw(20, 2, "'-' : Decrease Speed");
    mvprintw(21, 2, "'q' : Quit");
    refresh();

    int running = 1;
    while (running) {
        // --- READ HARDWARE ---
        uint32_t raw_r0 = regs[REG_DATA];
        uint32_t raw_r1 = regs[REG_CTRL];
        uint32_t raw_r2 = regs[REG_PRE];

        // --- CRITICAL CHANGE: INTERPRET AS SIGNED INT16 ---
        // We cast the lower 16 bits directly to a signed short.
        // 0xFFFF becomes -1, 0x8000 becomes -32768.
        int16_t adc_val = (int16_t)(raw_r0 & 0xFFFF);
        
        int      adc_ovf = (raw_r0 >> 16) & 0x1;
        int      curr_oe = raw_r1 & 0x01;
        int      curr_cs = (raw_r1 >> 1) & 0x01;
        double freq_mhz  = 100.0 / (2.0 * (raw_r2 + 1));

        // --- CALCULATE VOLTAGE (LINEAR SCALING) ---
        // 32768 counts = 10.0V
        double voltage = ((double)adc_val / 32768.0) * 10.0;

        // --- DRAW DYNAMIC VALUES ---
        
        // 1. Raw Value (Signed Decimal)
        mvprintw(2, 19, "%+06d", adc_val);

        // 2. Real-world Voltage
        mvprintw(2, 30, "%+06.2f V", voltage);

        // 3. Overflow Status
        if(adc_ovf) {
            attron(A_REVERSE); 
            mvprintw(3, 19, "YES!");
            attroff(A_REVERSE);
        } else {
            mvprintw(3, 19, "NO  ");
        }

        // 4. Bar Graph Logic for Signed Data
        // We need to shift the signed range (-32768 to +32767) 
        // to an unsigned range (0 to 65535) for the bar calculation.
        // -32768 + 32768 = 0 (Left edge)
        // 0 + 32768      = 32768 (Middle)
        // +32767 + 32768 = 65535 (Right edge)
        
        long shifted_val = (long)adc_val + 32768;
        int bars = (shifted_val * 60) / 65535;

        // Sanity check to prevent drawing outside bounds
        if (bars < 0) bars = 0;
        if (bars > 60) bars = 60;

        move(5, 8); // Move inside the bracket
        for(int i=0; i<60; i++) {
            if(i < bars) addch('#');
            else addch(' ');
        }

        // 5. Register Settings
        mvprintw(10, 24, "%s", curr_oe ? "ON " : "OFF");
        mvprintw(11, 24, "%s", curr_cs ? "INT     " : "EXT(SMA)");
        mvprintw(12, 24, "%-3u", raw_r2);
        mvprintw(13, 24, "%.2f MHz", freq_mhz);

        refresh();

        // --- INPUT HANDLING ---
        int ch = getch();
        if (ch != ERR) {
            switch(ch) {
                case 'q': running = 0; break;
                case 'o': regs[REG_CTRL] = raw_r1 ^ 0x01; break;
                case 'c': regs[REG_CTRL] = raw_r1 ^ 0x02; break;
                case '+': if (raw_r2 > 0) regs[REG_PRE] = raw_r2 - 1; break;
                case '-': regs[REG_PRE] = raw_r2 + 1; break;
            }
        }
        usleep(200000); // 5 FPS
    }

    endwin();
    munmap(mapped_base, MAP_SIZE);
    close(memfd);
    return 0;
}