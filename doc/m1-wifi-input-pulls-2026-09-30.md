# M1 Wi-Fi input pull configuration, 2026-09-30

The pinned ESP-IDF v5.5.5 SPI pin setup configures direction and matrix connections without clearing existing GPIO pulls. `transport_spi_start` now explicitly selects `GPIO_FLOATING` on host-driven SCK GPIO6, MOSI GPIO7 and CS GPIO10 after `spi_slave_initialize` and before arming the first transaction. This removes an uncontrolled internal pull load from the proposed local level-buffer output. No frame callback code changed in this task. External board loads and silicon leakage still need their own qualification.

## Build and code evidence

Both cached-IDF real-card and QEMU configurations built successfully. Both merged 4 MB flash images were regenerated. Source, ELF, bin, sdkconfig, flash-image and audited IDF source SHA-256 values are recorded in `build/scratch-si/wifi-pulls-build-hashes.json`. Build logs are `wifi-pulls-card-build-cached.log`, `wifi-pulls-qemu-build-cached.log`, and `wifi-pulls-card-merge.log` in the same directory. The normal fetch wrapper was blocked by read-only SDK Git metadata before compilation; the direct build used the already verified v5.5.5 SDK without changing that metadata.

The real ELF startup disassembly contains all three GPIO pull calls after SPI initialization and before `arm`. `wifi-pulls-card-symbols.txt` and `wifi-pulls-card-disassembly.txt` record the inspection. Callback closure `arm`, `done`, `frames_received`, `frames_preload`, `put`, `spi_slave_queue_trans_isr`, and memcpy are in IRAM; memset is ROM address 0x40000354. Startup itself is flash code, outside the ISR closure.

Native frame-wrap/sanitizer regression passed (`wifi-pulls-frame-regression.log`). The fresh QEMU runtime regression was blocked before boot by `socket.socket` raising PermissionError under current environment restrictions (`wifi-pulls-qemu-regression.log`). Successful QEMU compilation is not a runtime pass. These results do not establish a silicon worst-case ISR readiness latency or a 20 us turnaround guarantee.
