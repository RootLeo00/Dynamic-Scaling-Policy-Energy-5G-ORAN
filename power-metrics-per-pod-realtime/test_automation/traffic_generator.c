#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <time.h>

// Convert Mbps to bytes per second
int mbps_to_bytes_per_second(double mbps) {
    return (int)(mbps * 1000000 / 8);
}

// Sleep for the specified duration (in seconds)
void sleep_for_seconds(double seconds) {
    struct timespec ts;
    ts.tv_sec = (time_t)seconds;
    ts.tv_nsec = (seconds - ts.tv_sec) * 1e9;
    nanosleep(&ts, NULL);
}

// Main function to replay traffic
int main() {
    const char *file_path = "/root/testing_dat_1.csv";
    const char *target_ip = "12.1.1.100";
    const char *bind_interface = "tun0";
    int target_port = 2152;
    int interval = 1;

    // Load Mbps values from CSV
    FILE *file = fopen(file_path, "r");
    if (!file) {
        perror("Failed to open CSV file");
        return 1;
    }

    double mbps_values[1000];
    int value_count = 0;
    while (fscanf(file, "%lf", &mbps_values[value_count]) == 1) {
        value_count++;
    }
    fclose(file);

    // Create UDP socket
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("Socket creation failed");
        return 1;
    }

    // Bind to the specified interface
    if (setsockopt(sock, SOL_SOCKET, SO_BINDTODEVICE, bind_interface, strlen(bind_interface)) < 0) {
        perror("Failed to bind to interface");
        close(sock);
        return 1;
    }

    struct sockaddr_in target_addr;
    memset(&target_addr, 0, sizeof(target_addr));
    target_addr.sin_family = AF_INET;
    target_addr.sin_port = htons(target_port);
    inet_pton(AF_INET, target_ip, &target_addr.sin_addr);

    printf("Sending data to %s:%d via %s\n", target_ip, target_port, bind_interface);

    // Send traffic
    for (int i = 0; i < value_count; i++) {
        int byte_rate = mbps_to_bytes_per_second(mbps_values[i]);
        int packet_size = 1400;
        int packets_per_second = byte_rate / packet_size;

        clock_t start_time = clock();
        for (int j = 0; j < packets_per_second; j++) {
            sendto(sock, "a", packet_size, 0, (struct sockaddr *)&target_addr, sizeof(target_addr));
        }

        double elapsed = (double)(clock() - start_time) / CLOCKS_PER_SEC;
        if (elapsed < interval) {
            sleep_for_seconds(interval - elapsed);
        }
    }

    printf("Traffic replay complete.\n");
    close(sock);
    return 0;
}