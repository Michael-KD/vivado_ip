CC = gcc
CFLAGS = -Wall
LDFLAGS = -lncurses

all: adc_tool dac_tool spgd_tool

# Network server (compile on Zynq: make zynq_server)
zynq_server: zynq_server.c
	$(CC) $(CFLAGS) -o $@ $< -ljson-c

adc_tool: adc_tool.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

dac_tool: dac_tool.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

spgd_tool: spgd_tool.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f adc_tool dac_tool spgd_tool zynq_server

.PHONY: all clean
