#include <gpiod.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#define NUM_DATA_BITS 12
#define GPIOCHIP_NAME "gpiochip1"   // AXI GPIO @ 0x80000000

static int data_lines[NUM_DATA_BITS] = {
    0, 1, 2, 3, 4, 5,
    6, 7, 8, 9, 10, 11
};

static int clk_lines[2] = { 12, 13 };

int main(int argc, char *argv[])
{
    if (argc != 3) {
        printf("Usage: %s <channel 0|1> <value 0-4095>\n", argv[0]);
        return 1;
    }

    int channel = atoi(argv[1]);
    int value   = atoi(argv[2]);

    if (channel < 0 || channel > 1) {
        printf("Channel must be 0 or 1\n");
        return 1;
    }

    if (value < 0 || value > 4095) {
        printf("Value must be 0–4095\n");
        return 1;
    }

    printf("Driving DAC channel %d with value %d\n", channel, value);

    struct gpiod_chip *chip;
    struct gpiod_line *data[NUM_DATA_BITS];
    struct gpiod_line *clk;

    chip = gpiod_chip_open_by_name(GPIOCHIP_NAME);
    if (!chip) {
        perror("gpiod_chip_open_by_name");
        return 1;
    }

    /* Request data lines */
    for (int i = 0; i < NUM_DATA_BITS; i++) {
        data[i] = gpiod_chip_get_line(chip, data_lines[i]);
        if (!data[i]) {
            perror("gpiod_chip_get_line (data)");
            return 1;
        }

        if (gpiod_line_request_output(data[i], "dac-data", 0) < 0) {
            perror("gpiod_line_request_output (data)");
            return 1;
        }
    }

    /* Request clock line */
    clk = gpiod_chip_get_line(chip, clk_lines[channel]);
    if (!clk) {
        perror("gpiod_chip_get_line (clk)");
        return 1;
    }

    if (gpiod_line_request_output(clk, "dac-clk", 0) < 0) {
        perror("gpiod_line_request_output (clk)");
        return 1;
    }

    /* Drive DAC data */
    for (int bit = 0; bit < NUM_DATA_BITS; bit++) {
        int bitval = (value >> bit) & 1;
        gpiod_line_set_value(data[bit], bitval);
    }

    usleep(100);

    /* Pulse latch clock */
    gpiod_line_set_value(clk, 1);
    usleep(100);
    gpiod_line_set_value(clk, 0);

    printf("Done.\n");

    /* Cleanup */
    for (int i = 0; i < NUM_DATA_BITS; i++)
        gpiod_line_release(data[i]);

    gpiod_line_release(clk);
    gpiod_chip_close(chip);

    return 0;
}
