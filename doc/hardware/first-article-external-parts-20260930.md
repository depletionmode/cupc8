# External parts for the working first article

The JLC package supplies two assembled boards of each of the eight types. These external parts are separate; they are needed to demonstrate Main + CPU + IO + storage + WiFi + either GPU or eInk, with System for programming.

| Item | Required identity or condition | Quantity / use |
| --- | --- | --- |
| Main power supply and cable | 5 V USB-C source advertising 3 A, with a suitable cable. The 1.5 A mode disables radio and SD writes. | One per computer powered concurrently. Connect to Main USB-C, then use Main POWER. |
| System USB data cable and host | USB data connection matching the System connector; host supports RP2040 BOOTSEL and CDC serial. System USB VBUS senses connection but powers nothing. | One for initial System programming and the subsequent host programmer. System must be fitted to powered Main. |
| USB keyboard | Real keyboard supported by the IO firmware, within its declared 500 mA USB load budget. | One per computer being demonstrated. Actual descriptors and typing are checked after delivery. |
| microSD card | SPI-compatible card with a supported FAT16/FAT32 filesystem and suitable measured current. The firmware disables exFAT; arbitrary factory-formatted SDXC media are not qualified. | One per storage card in use. Preserve existing user media; prepare a separate intended card. Test SAVE, cold-power boot and LOAD. |
| HDMI display and cable | A sink compatible with the GPU's DVI video / 640 × 480 timing. No audio or HDCP claim. | For the GPU alternative; perform the specified per-unit 252 MHz / 1.20 V burn-in. |
| Selected eInk panel, driver module and cable | Waveshare 7.5-inch e-Paper HAT V2, 800 × 480, with Driver HAT Rev2.3 and the 9-wire cable; the selected module supports the documented fast/partial/4-grey operations. Use `eink750` firmware. | For the eInk alternative. See [panel specification and wiring](eink-card.md). Verify actual product revision and each J2 wire before power. |
| Alternative supported eInk panel | Good Display GDEY0583T81, 648 × 480, with the compatible driver adapter; use `eink` firmware. This is not permission to substitute the Waveshare 5.83-inch full-refresh-only glass for the selected panel. | Only if that actual panel is intentionally used; retain its separately scoped evidence. |
| WiFi antenna lead | KH-IPEX3-SMA-RG081-150mm, C709347, MHF III / IPEX generation 3 to SMA. A generation-1 U.FL lead does not mate. | Buy two loose leads for the two WiFi boards; plug in manually. |
| WiFi antenna | HJ-2.4GHz-SMA, C1509156, with mating SMA polarity as documented in [parts](parts.md). | Buy two loose antennas. These are not mounted BOM items. |
| Network access point and test server | Suitable 2.4 GHz network and a server reachable for the existing WiFi join/fetch test. | For actual radio/network acceptance. Native/QEMU success does not qualify physical RF or arbitrary APs. |
| Measurement samples and equipment | Items and counts in [the first-article plan](first-article-plan.md), including current limiting, voltage/current/temperature and receiving-pin waveform measurements. | Qty2 boards do not satisfy unchanged three-unit qualification rows or five/ten-part lot tests. Arrange additional samples before closing those rows. |

The mounted aggregate stock check covers 118 SKUs across the 16 assembled boards. The separate dated live antenna check passed on 2026-09-30: C709347 had 157 and C1509156 had 334, each against a minimum of two. These are snapshots, not reservations. No external purchases, manufacturer upload or order approval have been performed.
