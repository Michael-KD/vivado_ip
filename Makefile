CC = gcc
CFLAGS = -Wall
LDFLAGS = -lncurses

all: adc_tool dac_tool

adc_tool: adc_tool.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

dac_tool: dac_tool.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f adc_tool dac_tool
