/*
 * sysctl_sim: the system card for cupc8.py without the hardware. The real
 * sysctl core (fw/sysctl/core) runs against the machine in models
 * (sysmachine.c) and speaks its USB protocol on a pseudo-terminal, which
 * cupc8.py opens like the card's USB serial port.
 *
 *   sysctl_sim [--flashed] [--cc MV] [--esp SLOT=HOST:PORT] [--dump DIR] [--reply-delay MS] [--console]
 *
 * It prints the pty's path, then serves until killed. --console serves the
 * console port (usb-console.md) on a second pty, whose path it prints next:
 * the port counts as open from the start (a pty has no DTR), so the core
 * polls the rings in the bridge model's SRAM and moves them to and from it. --flashed starts with
 * both FPGA flashes holding their bitstreams. --esp puts an ESP32 card in
 * SLOT whose UART is at HOST:PORT (Espressif QEMU in download mode); slot 2
 * always holds an RP2040 card (swdtarget.h). --cc sets the USB-C CC voltage.
 * --reply-delay holds every reply MS milliseconds, as a slow command (a chip
 * erase) does: a host killed after its request finds the reply arriving in
 * the next host's session (HOST-002 checks cupc8.py resyncs past it).
 * --dump writes, when it is stopped (SIGTERM or SIGINT), what the models
 * hold: rom.bin, fl0.bin, fl1.bin, card3.bin and ram.bin (the 512 KB SRAM),
 * for the tests to check.
 */
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#include "sysmachine.h"

static int pty = -1;
static const char *dump_dir;
static volatile sig_atomic_t stopping;

static void on_signal(int sig)
{
	(void)sig;
	stopping = 1;
}

static void dump(const char *name, const void *data, size_t n)
{
	char path[1024];
	snprintf(path, sizeof path, "%s/%s", dump_dir, name);
	FILE *f = fopen(path, "wb");
	if (!f || fwrite(data, 1, n, f) != n)
		perror(path);
	if (f)
		fclose(f);
}
static int esp_slot = -1, esp_fd = -1;
static char esp_host[64];
static int esp_port;

static int reply_delay_ms;

static int open_pty(void)
{
	int fd = posix_openpt(O_RDWR | O_NOCTTY);
	if (fd < 0 || grantpt(fd) || unlockpt(fd)) {
		perror("sysctl_sim: pty");
		exit(1);
	}
	struct termios t;
	tcgetattr(fd, &t);
	cfmakeraw(&t);
	tcsetattr(fd, TCSANOW, &t);
	printf("%s\n", ptsname(fd));
	fflush(stdout);
	/* keep the slave open ourselves, so a client closing it isn't a hangup */
	int keep = open(ptsname(fd), O_RDWR | O_NOCTTY);
	(void)keep;
	fcntl(fd, F_SETFL, O_NONBLOCK);
	return fd;
}

static void usb_out(const uint8_t *d, int n)
{
	while (n > 0) {
		ssize_t k = write(pty, d, (size_t)n);
		if (k < 0) {
			if (errno == EAGAIN) {
				usleep(100);
				continue;
			}
			return;
		}
		d += k;
		n -= (int)k;
	}
}

/* the ESP card's UART: a TCP connection to QEMU's serial port */
static void esp_open(uint32_t baud)
{
	if (esp_fd >= 0) {
		close(esp_fd);
		esp_fd = -1;
	}
	if (!baud || M.prog_slot != esp_slot)
		return;
	struct sockaddr_in a = { .sin_family = AF_INET, .sin_port = htons((uint16_t)esp_port) };
	inet_pton(AF_INET, esp_host, &a.sin_addr);
	esp_fd = socket(AF_INET, SOCK_STREAM, 0);
	if (connect(esp_fd, (struct sockaddr *)&a, sizeof a) < 0) {
		fprintf(stderr, "sysctl_sim: can't reach the ESP card at %s:%d\n", esp_host, esp_port);
		close(esp_fd);
		esp_fd = -1;
		return;
	}
	fcntl(esp_fd, F_SETFL, O_NONBLOCK);
}

static void esp_write(const uint8_t *d, int n)
{
	if (esp_fd >= 0 && M.prog_slot == esp_slot && write(esp_fd, d, (size_t)n) < 0)
		perror("sysctl_sim: ESP write");
}

static int esp_read(uint8_t *d, int max)
{
	if (esp_fd < 0 || M.prog_slot != esp_slot)
		return 0;
	ssize_t n = read(esp_fd, d, (size_t)max);
	return n > 0 ? (int)n : 0;
}

int main(int argc, char **argv)
{
	bool flashed = false, with_console = false;
	int cc_mv = 0;
	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--flashed"))
			flashed = true;
		else if (!strcmp(argv[i], "--cc") && i + 1 < argc)
			cc_mv = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--reply-delay") && i + 1 < argc)
			reply_delay_ms = atoi(argv[++i]);
		else if (!strcmp(argv[i], "--console"))
			with_console = true;
		else if (!strcmp(argv[i], "--dump") && i + 1 < argc)
			dump_dir = argv[++i];
		else if (!strcmp(argv[i], "--esp") && i + 1 < argc &&
			 sscanf(argv[++i], "%d=%63[^:]:%d", &esp_slot, esp_host, &esp_port) == 3)
			;
		else {
			fprintf(stderr, "usage: sysctl_sim [--flashed] [--cc MV] [--esp SLOT=HOST:PORT] [--dump DIR] [--reply-delay MS] [--console]\n");
			return 2;
		}
	}
	power_on(flashed, flashed);
	M.chip.expect = NULL;                 /* any bitstream configures, as on the board */
	M.cpu.expect = NULL;
	M.adc[ADC_CC1] = cc_mv;
	signal(SIGTERM, on_signal);
	signal(SIGINT, on_signal);
	if (esp_slot >= 0) {
		M.uart_far.open = esp_open;
		M.uart_far.write = esp_write;
		M.uart_far.read = esp_read;
	}

	pty = open_pty();
	int con = with_console ? open_pty() : -1;
	M.con.open = with_console;

	struct timespec last;
	clock_gettime(CLOCK_MONOTONIC, &last);
	while (!stopping) {
		struct pollfd p = { .fd = pty, .events = POLLIN };
		poll(&p, 1, 1);
		uint8_t buf[4096];
		ssize_t n = read(pty, buf, sizeof buf);
		/* virtual time follows real time while idle */
		struct timespec now;
		clock_gettime(CLOCK_MONOTONIC, &now);
		uint64_t us = (uint64_t)(now.tv_sec - last.tv_sec) * 1000000u + (uint64_t)((now.tv_nsec - last.tv_nsec) / 1000);
		last = now;
		M.now += us;
		tick();
		/* a byte at a time: each reply goes out before the next frame's */
		for (ssize_t i = 0; i < n; i++) {
			M.usb_n = 0;
			sysctl_rx(&S, buf + i, 1);
			if (M.usb_n) {
				if (reply_delay_ms)
					usleep((useconds_t)reply_delay_ms * 1000);
				usb_out(M.usb, M.usb_n);
			}
		}
		if (con >= 0) {
			/* the console port: the PC's bytes in, the card's out */
			int room = (int)sizeof M.con.from_pc - M.con.from_pc_n;
			ssize_t k = read(con, M.con.from_pc + M.con.from_pc_n, (size_t)room);
			if (k > 0)
				M.con.from_pc_n += (int)k;
			M.con.room = 4096;
		}
		sysctl_poll(&S);
		if (con >= 0 && M.con.to_pc_n) {
			if (write(con, M.con.to_pc, (size_t)M.con.to_pc_n) < 0 && errno != EAGAIN)
				perror("sysctl_sim: console");
			M.con.to_pc_n = 0;
		}
	}
	if (dump_dir) {
		dump("rom.bin", M.rom.mem, sizeof M.rom.mem);
		dump("fl0.bin", M.fl0.mem, sizeof M.fl0.mem);
		dump("fl1.bin", M.fl1.mem, sizeof M.fl1.mem);
		dump("card3.bin", card2.flash, sizeof card2.flash);
		dump("ram.bin", M.br.ram, sizeof M.br.ram);
	}
	return 0;
}
