/*
 * IOC-002: real keyboards, recorded (tools/kbdrecord.py). Each recording's
 * boot reports go through the IO core as the card would receive them, and
 * the bytes it produces must be exactly what the terminal received while the
 * person typed the prompt.
 *
 *   test_recorded [dir]          (default test/io/recordings, from the repo root)
 */
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "iocard.h"

static int hex(const char *s, uint8_t *out, int max)
{
	int n = 0;
	while (s[0] && s[1] && n < max) {
		unsigned v;
		if (sscanf(s, "%2x", &v) != 1)
			break;
		out[n++] = (uint8_t)v;
		s += 2;
	}
	return n;
}

static iocard_t io;
static uint8_t got[4096];
static int ngot;

static void drain(void)
{
	for (;;) {
		uint8_t cmd[2] = { 0x01, 16 }, rd[18] = { 0xFE }, miso[18];
		card_frame(&io.card, cmd, NULL, 2);
		card_frame(&io.card, rd, miso, 18);
		int n = 0;
		for (int i = 2; i < 2 + miso[1] && i < 18; i++)
			if (miso[i] != 0xFF && ngot < (int)sizeof got) {
				got[ngot++] = miso[i];
				n++;
			}
		if (!n)
			return;
	}
}

static void start_prompt(void)
{
	io_init(&io);
	io_connected(&io, true);
	io.repeat_delay = 0;            /* the person didn't hold keys; the OS repeat is its own */
	ngot = 0;
}

static int check(const char *file, const char *prompt, const uint8_t *want, int nwant)
{
	drain();
	if (ngot == nwant && !memcmp(got, want, (size_t)nwant))
		return 0;
	printf("FAIL %s \"%s\": %d bytes, expected %d:", file, prompt, ngot, nwant);
	for (int i = 0; i < ngot; i++)
		printf(" %02x", got[i]);
	printf(" / want");
	for (int i = 0; i < nwant; i++)
		printf(" %02x", want[i]);
	printf("\n");
	return 1;
}

int main(int argc, char **argv)
{
	const char *dir = argc > 1 ? argv[1] : "test/io/recordings";
	DIR *d = opendir(dir);
	if (!d) {
		perror(dir);
		return 1;
	}
	int files = 0, prompts = 0, bad = 0;
	struct dirent *e;
	while ((e = readdir(d))) {
		size_t len = strlen(e->d_name);
		if (len < 5 || strcmp(e->d_name + len - 4, ".rec"))
			continue;
		char path[1024];
		snprintf(path, sizeof path, "%s/%s", dir, e->d_name);
		FILE *f = fopen(path, "r");
		if (!f)
			continue;
		files++;
		static char line[8192], prompt[512];
		uint8_t want[1024];
		int nwant = -1;
		while (fgets(line, sizeof line, f)) {
			line[strcspn(line, "\n")] = 0;
			if (!strncmp(line, "prompt ", 7)) {
				if (nwant >= 0) {
					bad += check(e->d_name, prompt, want, nwant);
					prompts++;
				}
				snprintf(prompt, sizeof prompt, "%.500s", line + 7);
				start_prompt();
				nwant = 0;
			} else if (!strncmp(line, "expect ", 7)) {
				nwant = hex(line + 7, want, sizeof want);
			} else if (!strncmp(line, "boot ", 5)) {
				unsigned ms;
				char h[64];
				uint8_t r[8];
				if (sscanf(line + 5, "%u %63s", &ms, h) == 2 && hex(h, r, 8) == 8) {
					io_poll(&io, ms);
					io_report(&io, r, ms);
					drain();
				}
			}
		}
		if (nwant >= 0) {
			bad += check(e->d_name, prompt, want, nwant);
			prompts++;
		}
		fclose(f);
	}
	closedir(d);
	printf("IOC-002 recorded keyboards: %d keyboards, %d prompts, %d failures\n", files, prompts, bad);
	return bad || !files ? 1 : 0;
}
