/*
 * zynq_server.c - TCP/JSON server for controlling AXI peripherals
 * 
 * Replaces the ncurses-based tools with a network-accessible server
 * that can be controlled from a remote GUI.
 *
 * Protocol: Newline-delimited JSON over TCP (port 5000)
 * 
 * Commands:
 *   {"cmd":"read_all","addresses":[2147680256, 2147745792]}
 *     -> Returns register 0-3 values for all requested addresses
 *   
 *   {"cmd":"read","addr":2147483648,"reg":0-3}
 *     -> Returns single register value
 *   
 *   {"cmd":"write","addr":2147483648,"reg":0-3,"value":N}
 *     -> Writes value to register
 *
 *   {"cmd":"pulse","addr":2147483648,"bit":2}
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
#include <setjmp.h>
#include <json-c/json.h>

#define MAP_SIZE    4096UL
#define MAP_MASK    (MAP_SIZE - 1)

#define DEFAULT_PORT 5000
#define MAX_MSG_LEN  65536 // Increased buffer length to handle read_all arrays

#define SERVER_VERSION "2.0"

// ============================================================================
// Global State
// ============================================================================

static volatile int running = 1;
static int server_fd = -1;
static int mem_fd = -1;
static volatile sig_atomic_t mmio_guard_active = 0;
static sigjmp_buf mmio_jmp_env;

struct mapped_region {
    uint32_t page_addr;
    void *map;
    struct mapped_region *next;
};

static struct mapped_region *mapped_regions = NULL;

static void sigbus_handler(int sig) {
    (void)sig;
    if (mmio_guard_active) {
        siglongjmp(mmio_jmp_env, 1);
    }
    running = 0;
}

// ============================================================================
// Hardware Access
// ============================================================================

static int init_hardware(void) {
    mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (mem_fd < 0) {
        perror("open /dev/mem");
        fprintf(stderr, "Run as root (sudo).\n");
        return -1;
    }
    printf("Hardware /dev/mem opened.\n");
    return 0;
}

static void cleanup_hardware(void) {
    struct mapped_region *curr = mapped_regions;
    while (curr) {
        struct mapped_region *next = curr->next;
        munmap(curr->map, MAP_SIZE);
        free(curr);
        curr = next;
    }
    if (mem_fd >= 0) close(mem_fd);
}

static volatile uint32_t *map_address(uint32_t target_addr) {
    if (mem_fd < 0) return NULL;
    uint32_t page_addr = target_addr & ~MAP_MASK;

    for (struct mapped_region *curr = mapped_regions; curr != NULL; curr = curr->next) {
        if (curr->page_addr == page_addr) {
            return (volatile uint32_t *)(curr->map + (target_addr & MAP_MASK));
        }
    }

    void *mapped = mmap(0, MAP_SIZE, PROT_READ | PROT_WRITE, MAP_SHARED, 
                        mem_fd, page_addr);
    if (mapped == MAP_FAILED) {
        perror("mmap");
        return NULL;
    }

    struct mapped_region *region = malloc(sizeof(struct mapped_region));
    if (!region) {
        munmap(mapped, MAP_SIZE);
        return NULL;
    }
    
    region->page_addr = page_addr;
    region->map = mapped;
    region->next = mapped_regions;
    mapped_regions = region;

    return (volatile uint32_t *)(mapped + (target_addr & MAP_MASK));
}

static int safe_read_reg(volatile uint32_t *regs, int reg, uint32_t *value) {
    if (!regs || !value || reg < 0) return -1;

    mmio_guard_active = 1;
    if (sigsetjmp(mmio_jmp_env, 1) != 0) {
        mmio_guard_active = 0;
        return -1;
    }

    *value = regs[reg];
    mmio_guard_active = 0;
    return 0;
}

static int safe_write_reg(volatile uint32_t *regs, int reg, uint32_t value) {
    if (!regs || reg < 0) return -1;

    mmio_guard_active = 1;
    if (sigsetjmp(mmio_jmp_env, 1) != 0) {
        mmio_guard_active = 0;
        return -1;
    }

    regs[reg] = value;
    mmio_guard_active = 0;
    return 0;
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

// ============================================================================
// Command Handlers
// ============================================================================

static char *handle_read_all(json_object *req) {
    json_object *addrs_array = NULL;
    if (!json_object_object_get_ex(req, "addresses", &addrs_array) ||
        !json_object_is_type(addrs_array, json_type_array)) {
        return make_error_response("Missing or invalid 'addresses' array");
    }

    json_object *resp = json_object_new_object();
    json_object_object_add(resp, "status", json_object_new_string("ok"));
    
    json_object *data_obj = json_object_new_object();

    int n_addrs = json_object_array_length(addrs_array);
    for (int i = 0; i < n_addrs; i++) {
        json_object *addr_item = json_object_array_get_idx(addrs_array, i);
        if (!json_object_is_type(addr_item, json_type_int)) continue;
        
        uint32_t addr = (uint32_t)json_object_get_int64(addr_item);
        volatile uint32_t *regs = map_address(addr);
        if (regs) {
            uint32_t r0, r1, r2, r3;
            if (safe_read_reg(regs, 0, &r0) != 0 ||
                safe_read_reg(regs, 1, &r1) != 0 ||
                safe_read_reg(regs, 2, &r2) != 0 ||
                safe_read_reg(regs, 3, &r3) != 0) {
                continue;
            }

            json_object *dev_data = json_object_new_object();
            json_object_object_add(dev_data, "0", json_object_new_int64(r0));
            json_object_object_add(dev_data, "1", json_object_new_int64(r1));
            json_object_object_add(dev_data, "2", json_object_new_int64(r2));
            json_object_object_add(dev_data, "3", json_object_new_int64(r3));
            
            char addr_str[32];
            snprintf(addr_str, sizeof(addr_str), "%u", addr);
            json_object_object_add(data_obj, addr_str, dev_data);
        }
    }

    json_object_object_add(resp, "data", data_obj);
    const char *json_str = json_object_to_json_string(resp);
    char *str = strdup(json_str);
    json_object_put(resp);
    return str;
}

static char *handle_read(json_object *req) {
    json_object *addr_item = NULL;
    json_object *reg_item = NULL;

    if (!json_object_object_get_ex(req, "addr", &addr_item) ||
        !json_object_object_get_ex(req, "reg", &reg_item)) {
        return make_error_response("Missing 'addr' or 'reg'");
    }

    if (!json_object_is_type(addr_item, json_type_int) ||
        !json_object_is_type(reg_item, json_type_int)) {
        return make_error_response("Invalid 'addr' or 'reg' type");
    }

    uint32_t addr = (uint32_t)json_object_get_int64(addr_item);
    int reg = json_object_get_int(reg_item);

    if (reg < 0 || reg > 1023) {
        return make_error_response("Register index out of bounds (0-1023)");
    }

    volatile uint32_t *regs = map_address(addr);
    if (!regs) {
        return make_error_response("Failed to map address");
    }

    uint32_t value = 0;
    if (safe_read_reg(regs, reg, &value) != 0) {
        return make_error_response("Bus fault while reading register");
    }

    return make_read_response(value);
}

static char *handle_read_fifo(json_object *req) {
    json_object *addr_item = NULL;
    json_object *reg_item = NULL;
    json_object *count_item = NULL;

    if (!json_object_object_get_ex(req, "addr", &addr_item) ||
        !json_object_object_get_ex(req, "reg", &reg_item) ||
        !json_object_object_get_ex(req, "count", &count_item)) {
        return make_error_response("Missing 'addr', 'reg', or 'count'");
    }

    uint32_t addr = (uint32_t)json_object_get_int64(addr_item);
    int reg = json_object_get_int(reg_item);
    int count = json_object_get_int(count_item);

    if (count <= 0 || count > 65536) {
        return make_error_response("Count must be between 1 and 65536");
    }
    if (reg < 0 || reg > 1023) {
        return make_error_response("Register index out of bounds (0-1023)");
    }

    volatile uint32_t *regs = map_address(addr);
    if (!regs) {
        return make_error_response("Failed to map address");
    }

    json_object *resp = json_object_new_object();
    json_object_object_add(resp, "status", json_object_new_string("ok"));
    
    json_object *data_array = json_object_new_array();
    
    // Read the exact same register 'count' times
    for (int i = 0; i < count; i++) {
        uint32_t value = 0;
        if (safe_read_reg(regs, reg, &value) != 0) {
            json_object_put(data_array);
            json_object_put(resp);
            return make_error_response("Bus fault while reading FIFO");
        }
        json_object_array_add(data_array, json_object_new_int64(value));
    }
    
    json_object_object_add(resp, "data", data_array);
    const char *json_str = json_object_to_json_string(resp);
    char *str = strdup(json_str);
    json_object_put(resp);
    return str;
}

static char *handle_write(json_object *req) {
    json_object *addr_item = NULL;
    json_object *reg_item = NULL;
    json_object *val_item = NULL;

    if (!json_object_object_get_ex(req, "addr", &addr_item) ||
        !json_object_object_get_ex(req, "reg", &reg_item) ||
        !json_object_object_get_ex(req, "value", &val_item)) {
        return make_error_response("Missing 'addr', 'reg', or 'value'");
    }

    if (!json_object_is_type(addr_item, json_type_int) ||
        !json_object_is_type(reg_item, json_type_int) ||
        !json_object_is_type(val_item, json_type_int)) {
        return make_error_response("Invalid 'addr', 'reg', or 'value' type");
    }

    uint32_t addr = (uint32_t)json_object_get_int64(addr_item);
    int reg = json_object_get_int(reg_item);
    uint32_t value = (uint32_t)json_object_get_int64(val_item);

    if (reg < 0 || reg > 3) {
        return make_error_response("Register index must be 0-3");
    }

    volatile uint32_t *regs = map_address(addr);
    if (!regs) {
        return make_error_response("Failed to map address");
    }

    if (safe_write_reg(regs, reg, value) != 0) {
        return make_error_response("Bus fault while writing register");
    }

    return make_ok_response();
}

static char *handle_pulse(json_object *req) {
    json_object *addr_item = NULL;
    json_object *bit_item = NULL;

    if (!json_object_object_get_ex(req, "addr", &addr_item) ||
        !json_object_object_get_ex(req, "bit", &bit_item)) {
        return make_error_response("Missing 'addr' or 'bit'");
    }

    if (!json_object_is_type(addr_item, json_type_int) ||
        !json_object_is_type(bit_item, json_type_int)) {
        return make_error_response("Invalid 'addr' or 'bit' type");
    }

    uint32_t addr = (uint32_t)json_object_get_int64(addr_item);
    int bit = json_object_get_int(bit_item);

    if (bit < 0 || bit > 31) {
        return make_error_response("Bit index must be 0-31");
    }

    volatile uint32_t *regs = map_address(addr);
    if (!regs) {
        return make_error_response("Failed to map address");
    }

    // Pulse the bit in control register (reg 0) - wait, your old code pulsed reg 0 for SPGD
    // If pulse is generally for reg 0 (which is also DAC value, SPGD ctrl, ADC value=read only).
    // Note: old code did regs[0] = orig | mask;
    uint32_t mask = 1U << bit;
    uint32_t orig = 0;

    if (safe_read_reg(regs, 0, &orig) != 0) {
        return make_error_response("Bus fault while reading control register");
    }
    if (safe_write_reg(regs, 0, orig | mask) != 0) {
        return make_error_response("Bus fault while pulsing control register");
    }
    usleep(100);
    if (safe_write_reg(regs, 0, orig & ~mask) != 0) {
        return make_error_response("Bus fault while restoring control register");
    }

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

    if (strcmp(cmd, "read_all") == 0) {
        response = handle_read_all(req);
    } else if (strcmp(cmd, "read") == 0) {
        response = handle_read(req);
    } else if (strcmp(cmd, "read_fifo") == 0) {
        response = handle_read_fifo(req);
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

        char *line_start = buffer;
        char *newline;
        while ((newline = strchr(line_start, '\n')) != NULL) {
            *newline = '\0';

            if (line_start[0] != '\0') {
                char *response = process_request(line_start);
                if (response) {
                    send(client_fd, response, strlen(response), 0);
                    send(client_fd, "\n", 1, 0);
                    free(response);
                }
            }
            line_start = newline + 1;
        }

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
    if (server_fd >= 0) close(server_fd);
}

static void install_signal_handlers(void) {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = signal_handler;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);

    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = sigbus_handler;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGBUS, &sa, NULL);
}

static int start_server(int port) {
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        perror("socket");
        return -1;
    }

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
            if (running) perror("accept");
            continue;
        }
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

    printf("=== Zynq AXI Peripheral Server (Dynamic) ===\n\n");
    printf("Version: %s\n\n", SERVER_VERSION);

    install_signal_handlers();

    if (init_hardware() < 0) return 1;

    int ret = start_server(port);

    cleanup_hardware();
    printf("Server stopped.\n");

    return ret;
}
