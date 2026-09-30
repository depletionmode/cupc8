"""Exercise the real ESP frame queue at byte/header wraps and overflow.

Only the platform attributes and critical-section primitives are stubbed;
this verifies byte preservation, not ISR concurrency or silicon timing.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''
#include <assert.h>
#include <string.h>
#include "frames.h"
static unsigned char expected[8192], observed[8192];
static int want, got, queued, completed;
static uint8_t status(card_t *c) { (void)c; return 0xff; }
void card_select(card_t *c, bool selected) {
    (void)c;
    if (!selected) completed++;
}
uint8_t card_next_miso(card_t *c) { (void)c; return 0; }
void card_mosi(card_t *c, uint8_t b) { (void)c; observed[got++] = b; }
static void drain(void) {
    assert(frames_poll() == queued);
    assert(completed == queued && got == want);
    assert(!memcmp(expected, observed, want));
    want = got = queued = completed = 0;
}
static bool send(int len, unsigned seed) {
    unsigned char frame[513];
    for (int i = 0; i < len; i++) frame[i] = (unsigned char)(seed + i * 37);
    frame[0] = 0x10; /* command, not READ */
    bool accepted = frames_received(frame, len);
    if (accepted) {
        memcpy(expected + want, frame, len); want += len; queued++;
    }
    return accepted;
}
int main(void) {
    card_ops_t ops = {.status = status};
    card_t card = {.ops = &ops, .resp_ready = true, .resp_len = 3,
                   .resp = {0x81, 0x42, 0x23}};
    frames_init(&card);
    unsigned char preload[512];
    assert(frames_preload(preload, sizeof preload) == 5);
    assert(preload[0] == 0x7f && preload[1] == 3 && preload[2] == 0x81);
    /* Put the two-byte header at ring index 4095, then force payload wrap. */
    for (int i = 0; i < 7; i++) assert(send(512, i));
    drain();
    assert(send(495, 1)); drain();
    assert(send(1, 2)); drain();
    for (int i = 0; i < 7; i++) assert(send(512, i));
    drain();
    assert(send(488, 3)); drain();
    assert(send(20, 4)); drain();
    /* Frequent payload and two-byte length-header wraps, preserving order. */
    unsigned seed = 1;
    for (int i = 0; i < 3000; i++) {
        seed = seed * 1664525u + 1013904223u;
        int len = 1 + (int)(seed % 512);
        assert(send(len, seed));
        assert(frames_preload(preload, sizeof preload) == 1);
        if (i % 3 == 2) drain();
    }
    drain();
    for (int i = 0; i < 7; i++) assert(send(512, i));
    assert(!send(512, 99)); /* no partial overwrite on full queue */
    assert(!send(513, 99));
    drain();
    assert(frames_received(NULL, 0));
    assert(frames_received(NULL, -1));
    assert(frames_poll() == 0);
    assert(frames_preload(preload, sizeof preload) == 5);
    frames_busy(true);
    assert(frames_preload(preload, sizeof preload) == 1);
    frames_busy(false);
    assert(frames_preload(preload, sizeof preload) == 5);
    return 0;
}
'''


class WifiFrames(unittest.TestCase):
    def test_real_queue_wrap_overflow_and_preload(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            (tmp / 'freertos').mkdir()
            (tmp / 'esp_attr.h').write_text('#define IRAM_ATTR\n')
            (tmp / 'freertos/FreeRTOS.h').write_text(
                'typedef int portMUX_TYPE;\n#define portMUX_INITIALIZER_UNLOCKED 0\n'
                '#define portENTER_CRITICAL_SAFE(p) ((void)(p))\n'
                '#define portEXIT_CRITICAL_SAFE(p) ((void)(p))\n'
                '#define portENTER_CRITICAL(p) ((void)(p))\n'
                '#define portEXIT_CRITICAL(p) ((void)(p))\n')
            source = tmp / 'queue.c'
            source.write_text(HARNESS)
            binary = tmp / 'queue'
            subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            '-I' + str(tmp), '-I' + str(ROOT / 'fw/common'),
                            '-I' + str(ROOT / 'fw/wifi/port/esp32c3/main'),
                            str(source), str(ROOT / 'fw/wifi/port/esp32c3/main/frames.c'),
                            '-o', str(binary)], check=True, capture_output=True)
            env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
            subprocess.run([str(binary)], check=True, env=env, capture_output=True)


if __name__ == '__main__':
    unittest.main()
