/*
 * zynq_server.c - TCP/JSON server for controlling AXI peripherals
 * 
 * Replaces the ncurses-based tools (adc_tool, dac_tool, spgd_tool) with a
 * network-accessible server that can be controlled from a remote GUI.
 *
 * Protocol: Newline-delimited JSON over TCP (port 5000)
 * 
 * Commands:
 *   {"cmd":"get_all"}
 *     -> Returns all register values for all devices
 *   
 *   {"cmd":"read","device":"adc|dac|spgd","reg":0-2}
 *     -> Returns single register value
 *   
 *   {"cmd":"write","device":"adc|dac|spgd","reg":0-2,"value":N}
 *     -> Writes value to register
 *
 *   {"cmd":"pulse","device":"spgd","bit":2}
 *     -> Pulses a control bit (for soft reset)
 *
 * Compile: arm-linux-gnueabihf-gcc -o zynq_server zynq_server.c -ljson-c
 * Run:     sudo ./zynq_server [port]
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <json-c/json.h>

// ============================================================================
// Hardware Configuration (Match Vivado Address Editor)
// ============================================================================

#define SPGD_ADDR   0x80000000
#define ADC_ADDR    0x80030000
#define DAC_ADDR    0x80040000

#define MAP_SIZE    4096UL
#define MAP_MASK    (MAP_SIZE - 1)

#define DEFAULT_PORT 5000
#define MAX_MSG_LEN  4096

// ============================================================================
// Global State
// ============================================================================

static volatile int running = 1;
static int server_fd = -1;

// Memory-mapped register pointers
static volatile uint32_t *spgd_regs = NULL;
static volatile uint32_t *adc_regs  = NULL;
static volatile uint32_t *dac_regs  = NULL;

static void *spgd_map = NULL;
static void *adc_map  = NULL;
static void *dac_map  = NULL;

static int mem_fd = -1;

// ============================================================================
// Hardware Access
// ============================================================================

static void *map_peripheral(uint32_t phy_addr) {
    void *mapped = mmap(0, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, 
                        mem_fd, phy_addr & ~MAP_MASK);
    if (mapped == MAP_FAILED) {
        perror("mmap");
        return NULL;
    }
    return mapped;
}

static int init_hardware(void) {
    mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (mem_fd < 0) {
        perror("open /dev/mem");
        fprintf(stderr, "Run as root (sudo).\n");
        return -1;
    }

    spgd_map = map_peripheral(SPGD_ADDR);
    adc_map  = map_peripheral(ADC_ADDR);
    dac_map  = map_peripheral(DAC_ADDR);

    if (!spgd_map || !adc_map || !dac_map) {
        fprintf(stderr, "Failed to map one or more peripherals.\n");
        return -1;
    }

    spgd_regs = (volatile uint32_t *)(spgd_map + (SPGD_ADDR & MAP_MASK));
    adc_regs  = (volatile uint32_t *)(adc_map  + (ADC_ADDR  & MAP_MASK));
    dac_regs  = (volatile uint32_t *)(dac_map  + (DAC_ADDR  & MAP_MASK));

    printf("Hardware mapped:\n");
    printf("  SPGD @ 0x%08X\n", SPGD_ADDR);
    printf("  ADC  @ 0x%08X\n", ADC_ADDR);
    printf("  DAC  @ 0x%08X\n", DAC_ADDR);

    return 0;
}

static void cleanup_hardware(void) {
    if (spgd_map) munmap(spgd_map, MAP_SIZE);
    if (adc_map)  munmap(adc_map, MAP_SIZE);
    if (dac_map)  munmap(dac_map, MAP_SIZE);
    if (mem_fd >= 0) close(mem_fd);
}

static volatile uint32_t *get_device_regs(const char *device) {
    if (!device) return NULL;
    if (strcmp(device, "spgd") == 0) return spgd_regs;
    if (strcmp(device, "adc")  == 0) return adc_regs;
    if (strcmp(device, "dac")  == 0) return dac_regs;
    return NULL;
}

// ============================================================================
// JSON Response Helpers
// ============================================================================

static char *make_error_response(const char *msg) {
    json_object *resp = json_object_new_object();
    json_object_object_add(resp, "status", json_object_new_string("error"));
    json_object_object_add(resp, "message", json_object_new_string(msg));
    const char *json_str = json_object_to_json_string(resp);
    char *str = strdup(json_str);
    json_object_put(resp);
    return str;
}

static char *make_ok_response(void) {
    json_object *resp = json_object_new_object();
    json_object_object_add(resp, "status", json_object_new_string("ok"));
    const char *json_str = json_object_to_json_string(resp);
    char *str = strdup(json_str);
    json_object_put(resp);
    return str;
}

static char *make_read_response(uint32_t value) {
    json_object *resp = json_object_new_object();
    json_object_object_add(resp, "status", json_object_new_string("ok"));
    json_object_object_add(resp, "value", json_object_new_int64(value));
    const char *json_str = json_object_to_json_string(resp);
    char *str = strdup(json_str);
    json_object_put(resp);
    return str;
}

static char *make_get_all_response(void) {
    json_object *resp = json_object_new_object();
    json_object_object_add(resp, "status", json_object_new_string("ok"));

    // SPGD registers
    json_object *spgd = json_object_new_object();
    json_object_object_add(spgd, "ctrl",   json_object_new_int64(spgd_regs[0]));
    json_object_object_add(spgd, "config", json_object_new_int64(spgd_regs[1]));
    json_object_object_add(spgd, "gamma",  json_object_new_int64(spgd_regs[2]));
    json_object_object_add(resp, "spgd", spgd);

    // ADC registers
    json_object *adc = json_object_new_object();
    json_object_object_add(adc, "data", json_object_new_int64(adc_regs[0]));
    json_object_object_add(adc, "ctrl", json_object_new_int64(adc_regs[1]));
    json_object_object_add(adc, "pre",  json_object_new_int64(adc_regs[2]));
    json_object_object_add(resp, "adc", adc);

    // DAC registers
    json_object *dac = json_object_new_object();
    json_object_object_add(dac, "data", json_object_new_int64(dac_regs[0]));
    json_object_object_add(dac, "ctrl", json_object_new_int64(dac_regs[1]));
    json_object_object_add(dac, "pre",  json_object_new_int64(dac_regs[2]));
    json_object_object_add(resp, "dac", dac);

    const char *json_str = json_object_to_json_string(resp);
    char *str = strdup(json_str);
    json_object_put(resp);
    return str;
}

// ============================================================================
// Command Handlers
// ============================================================================

static char *handle_get_all(json_object *req) {
    (void)req;
    return make_get_all_response();
}

static char *handle_read(json_object *req) {
    json_object *dev_item = NULL;
    json_object *reg_item = NULL;

    if (!json_object_object_get_ex(req, "device", &dev_item) ||
        !json_object_object_get_ex(req, "reg", &reg_item)) {
        return make_error_response("Missing 'device' or 'reg'");
    }

    if (!json_object_is_type(dev_item, json_type_string) ||
        !json_object_is_type(reg_item, json_type_int)) {
        return make_error_response("Invalid 'device' or 'reg' type");
    }

    const char *device = json_object_get_string(dev_item);
    int reg = json_object_get_int(reg_item);

    if (reg < 0 || reg > 2) {
        return make_error_response("Register index must be 0-2");
    }

    volatile uint32_t *regs = get_device_regs(device);
    if (!regs) {
        return make_error_response("Unknown device (use 'adc', 'dac', or 'spgd')");
    }

    return make_read_response(regs[reg]);
}

static char *handle_write(json_object *req) {
    json_object *dev_item = NULL;
    json_object *reg_item = NULL;
    json_object *val_item = NULL;

    if (!json_object_object_get_ex(req, "device", &dev_item) ||
        !json_object_object_get_ex(req, "reg", &reg_item) ||
        !json_object_object_get_ex(req, "value", &val_item)) {
        return make_error_response("Missing 'device', 'reg', or 'value'");
    }

    if (!json_object_is_type(dev_item, json_type_string) ||
        !json_object_is_type(reg_item, json_type_int) ||
        !json_object_is_type(val_item, json_type_int)) {
        return make_error_response("Invalid 'device', 'reg', or 'value' type");
    }

    const char *device = json_object_get_string(dev_item);
    int reg = json_object_get_int(reg_item);
    uint32_t value = (uint32_t)json_object_get_int64(val_item);

    if (reg < 0 || reg > 2) {
        return make_error_response("Register index must be 0-2");
    }

    volatile uint32_t *regs = get_device_regs(device);
    if (!regs) {
        return make_error_response("Unknown device (use 'adc', 'dac', or 'spgd')");
    }

    regs[reg] = value;
    return make_ok_response();
}

static char *handle_pulse(json_object *req) {
    json_object *dev_item = NULL;
    json_object *bit_item = NULL;

    if (!json_object_object_get_ex(req, "device", &dev_item) ||
        !json_object_object_get_ex(req, "bit", &bit_item)) {
        return make_error_response("Missing 'device' or 'bit'");
    }

    if (!json_object_is_type(dev_item, json_type_string) ||
        !json_object_is_type(bit_item, json_type_int)) {
        return make_error_response("Invalid 'device' or 'bit' type");
    }

    const char *device = json_object_get_string(dev_item);
    int bit = json_object_get_int(bit_item);

    if (bit < 0 || bit > 31) {
        return make_error_response("Bit index must be 0-31");
    }

    volatile uint32_t *regs = get_device_regs(device);
    if (!regs) {
        return make_error_response("Unknown device");
    }

    // Pulse the bit in control register (reg 0)
    uint32_t mask = 1U << bit;
    uint32_t orig = regs[0];
    regs[0] = orig | mask;
    usleep(100);
    regs[0] = orig & ~mask;

    return make_ok_response();
}

static char *process_request(const char *json_str) {
    json_object *req = json_tokener_parse(json_str);
    if (!req) {
        return make_error_response("Invalid JSON");
    }

    json_object *cmd_item = NULL;
    if (!json_object_object_get_ex(req, "cmd", &cmd_item) ||
        !json_object_is_type(cmd_item, json_type_string)) {
        json_object_put(req);
        return make_error_response("Missing 'cmd' field");
    }

    const char *cmd = json_object_get_string(cmd_item);
    char *response = NULL;

    if (strcmp(cmd, "get_all") == 0) {
        response = handle_get_all(req);
    } else if (strcmp(cmd, "read") == 0) {
        response = handle_read(req);
    } else if (strcmp(cmd, "write") == 0) {
        response = handle_write(req);
    } else if (strcmp(cmd, "pulse") == 0) {
        response = handle_pulse(req);
    } else {
        response = make_error_response("Unknown command");
    }

    json_object_put(req);
    return response;
}

// ============================================================================
// Network Server
// ============================================================================

static void handle_client(int client_fd, struct sockaddr_in *client_addr) {
    char client_ip[INET_ADDRSTRLEN];
    inet_ntop(AF_INET, &client_addr->sin_addr, client_ip, sizeof(client_ip));
    printf("Client connected: %s:%d\n", client_ip, ntohs(client_addr->sin_port));

    char buffer[MAX_MSG_LEN];
    int buf_pos = 0;

    while (running) {
        // Read data from client
        int bytes_read = recv(client_fd, buffer + buf_pos, sizeof(buffer) - buf_pos - 1, 0);
        if (bytes_read <= 0) {
            if (bytes_read == 0) {
                printf("Client disconnected: %s\n", client_ip);
            } else {
                perror("recv");
            }
            break;
        }

        buf_pos += bytes_read;
        buffer[buf_pos] = '\0';

        // Process complete lines (newline-delimited JSON)
        char *line_start = buffer;
        char *newline;
        while ((newline = strchr(line_start, '\n')) != NULL) {
            *newline = '\0';

            // Skip empty lines
            if (line_start[0] != '\0') {
                char *response = process_request(line_start);
                if (response) {
                    // Send response with newline
                    send(client_fd, response, strlen(response), 0);
                    send(client_fd, "\n", 1, 0);
                    free(response);
                }
            }

            line_start = newline + 1;
        }

        // Move remaining data to start of buffer
        int remaining = buf_pos - (line_start - buffer);
        if (remaining > 0) {
            memmove(buffer, line_start, remaining);
        }
        buf_pos = remaining;
    }

    close(client_fd);
}

static void signal_handler(int sig) {
    (void)sig;
    printf("\nShutting down...\n");
    running = 0;
    if (server_fd >= 0) {
        close(server_fd);
    }
}

static int start_server(int port) {
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        perror("socket");
        return -1;
    }

    // Allow address reuse
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(port);

    if (bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        perror("bind");
        close(server_fd);
        return -1;
    }

    if (listen(server_fd, 5) < 0) {
        perror("listen");
        close(server_fd);
        return -1;
    }

    printf("Server listening on port %d\n", port);
    printf("Press Ctrl+C to quit.\n\n");

    while (running) {
        struct sockaddr_in client_addr;
        socklen_t client_len = sizeof(client_addr);

        int client_fd = accept(server_fd, (struct sockaddr *)&client_addr, &client_len);
        if (client_fd < 0) {
            if (running) {
                perror("accept");
            }
            continue;
        }

        // Handle client (blocking, single client at a time)
        // For multiple clients, you'd fork() or use threads
        handle_client(client_fd, &client_addr);
    }

    close(server_fd);
    return 0;
}

// ============================================================================
// Main
// ============================================================================

int main(int argc, char *argv[]) {
    int port = DEFAULT_PORT;

    if (argc > 1) {
        port = atoi(argv[1]);
        if (port <= 0 || port > 65535) {
            fprintf(stderr, "Invalid port: %s\n", argv[1]);
            return 1;
        }
    }

    printf("=== Zynq AXI Peripheral Server ===\n\n");

    // Setup signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);

    // Initialize hardware
    if (init_hardware() < 0) {
        return 1;
    }

    // Start server
    int ret = start_server(port);

    // Cleanup
    cleanup_hardware();
    printf("Server stopped.\n");

    return ret;
}
