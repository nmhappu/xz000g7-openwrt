# TP-Link XZ000-G7 — OpenWrt Build Documentation

## Summary

This document records the conversion of a **TP-Link XZ000-G7** GPON ONT, running
**OpenWrt-galachip**, into a working replacement for a physical **Huawei EchoLife EG8141A5**.
In this deployment, the ISP/LCO OLT had already provisioned the subscriber line against the
identity of that Huawei unit. The XZ000-G7 was made to present the same identity, and the OLT
accepted and kept it.

> [!WARNING]
> **No guarantee of provisioning.** OLT vendors, firmware versions and ISP/LCO provisioning
> policies differ, including how many identity fields are bound and checked. A setup that works
> on one line may fail on another.
>
> **Use at your own risk.** Flashing, identity cloning and line changes are carried out entirely
> at your own risk. This includes the risk of a bricked device, service interruption, or a
> breach of your ISP's terms of service. Clone only the identity of a device you own, on a line
> provisioned to you.
>
> **No warranty.** This project is provided "as is". The author, **nmhappu**, gives no warranty
> of any kind, express or implied, and accepts no liability for any damage or loss arising from
> its use.

> [!CAUTION]
> **Rogue ONU risk.** A GPON line is a shared medium: every ONU behind the same splitter
> transmits upstream on one wavelength, in time slots assigned by the OLT. An ONU whose laser
> transmits outside its assigned slots, or stays on continuously, is a **rogue ONU**. It corrupts
> upstream traffic for **every subscriber on that PON port**, not only for this line.
>
> A rogue ONU can be created by accident while flashing or testing firmware, for example by an
> interrupted or partial flash, a wrong or incompatible image, a misconfigured optics/laser
> driver, or a bootloader or kernel that leaves the transmitter enabled. Two ONUs with the same
> serial on one PON also disrupt registration for that port.
>
> - **Disconnect the fibre** before entering U-Boot, flashing, or testing any new image.
> - Reconnect it only after the device boots cleanly and the identity and VLAN configuration
>   have been verified over SSH or the serial console.
> - If the ONU does not reach **O5** within a few minutes, or neighbouring subscribers report an
>   outage, **disconnect the fibre immediately**.
> - Rogue ONU behaviour can be detected by the OLT and may lead the ISP/LCO to isolate or block
>   the line.

### Scope

The EG8141A5 is the reference case, not the only supported target. The same method applies to
any physical ONU/modem whose identity can be read in full: vendor ID, GPON serial,
equipment ID, hardware and software versions, and, where used, the PLOAM password or LOID.
OpenWrt-galachip exposes these fields as configuration, which allows the identity of such a
device to be reproduced on the XZ000-G7.

The guide also documents the critical and minor flaws found in both the stock TP-Link firmware
and OpenWrt-galachip. Each of these, if left unaddressed, causes one of three failures:

| Failure | Cause | Firmware | Severity | Section |
|---|---|---|---|---|
| ONU does not provision correctly | Transmitted vendor and equipment ID cannot be changed | Stock | Critical | §2 |
| Connection does not persist | Equipment ID mismatch: OLT sends `Deactivate_ONU-ID` ~13 min after registration | Both | Critical | §5 |
| Connection does not persist | Second device with the same serial on the line (SN conflict) | Both | Critical | §1, §9 |
| PPPoE WAN fails (error 651) | Untagged frames tagged as VLAN 1 and dropped by the VLAN 155 GEM | OpenWrt | Critical | §6 |
| PPPoE WAN fails (error 651) | `omci.main.vlan_translate` is silently ignored | OpenWrt | Minor | §6 |
| ONT cannot dial PPPoE itself | No `pppd`/`pppoe` in the SNAPSHOT build | OpenWrt | Minor | §7 |
| Management IP unreachable | PPPoE session on the PC takes over the route to `192.168.1.1` | OpenWrt | Minor | §3 |
| Flashing fails or bricks the device | U-Boot does not service the hardware watchdog; key input during SPL starts YMODEM | OpenWrt | Minor | §2 |

### Status (reference deployment)

Registers at **O5 / ONU-ID 31**, reports EG8141A5 over OMCI, and the PPPoE WAN is up with a
public IP. All settings persist across reboot.

> [!NOTE]
> **Test environment.** This configuration was developed and verified on a **Kerala Vision**
> GPON line in Kerala, India, served through a local cable operator (LCO) from a Huawei-based OLT.
> Other ISPs may use different OLT vendors, identity-binding rules, VLAN IDs, and WAN
> authentication methods (for example LOID, PLOAM password, DHCP, or IPoE instead of PPPoE).
> Confirm the parameters that apply to your own line before using the values in this guide.

**Steps that matter:**
1. **Back up** the stock flash (§4).
2. **Flash** OpenWrt-galachip via U-Boot/TFTP over a serial console (USB-to-TTL or ESP32/Arduino, §2–3).
3. **Clone the identity:** vendor `HWTC`, serial, *and* equipment-ID, or the OLT drops the ONU
   after ~13 min (§5).
4. **Tag VLAN 155** on the ONT so untagged downstream traffic reaches the Internet GEM (§6).
5. **Dial PPPoE** from the downstream device (§7).

Restore to stock: §10.

---

## 1. Hardware & identity

| Item | Value |
|---|---|
| Device | TP-Link **XZ000-G7 v1.0** GPON ONT |
| SoC | **Galachip GC1601** — FA626TE ARMv5TE @ 533 MHz, 32 MB RAM |
| Flash | 4 MiB SPI-NOR (EN25QH32B) |
| Cloned device | **Huawei EchoLife EG8141A5** GPON Terminal |
| GPON serial | `48575443XXXXXXXX` (= `HWTC` + 8 hex digits from the original unit's label) |
| Vendor ID | `HWTC` (Huawei) |
| Equipment ID | `EG8141A5` |
| ISP data VLAN | **155** (Internet).  VLAN 77 = secondary service on this OLT |
| PPPoE user/pass | `<PPPOE_USER>` / `<PPPOE_PASS>` |

> The serial, vendor and model were taken from the **label of the real EG8141A5**
> (SN on the clone matches the real unit exactly). The real unit must stay **powered off**
> — two devices with the same serial on the line = OLT deactivates one for SN conflict.

---

## 2. Firmware: openwrt-galachip

- Project: **github.com/yesrab/openwrt-galachip** (R1.1 release, OpenWrt SNAPSHOT `r37842-871094233c`)
- Images: [`firmware/openwrt-galachip/`](../firmware/openwrt-galachip/)
- Why: stock TP-Link firmware never let the real transmitted **vendor/equipment-ID** change.
  OpenWrt-galachip exposes the full OMCI identity as settable config, which is what makes the
  clone possible.

### Flash procedure (U-Boot over TFTP)
Access the U-Boot console over serial with a USB-to-TTL adapter or an ESP32/Arduino bridge (see §3). PC serves the images with a
TFTP server ([`scripts/tftp_serve2.py`](../scripts/tftp_serve2.py), blksize-OACK + robust EOF — handles the exact-128 KB
`u-boot-with-spl.bin`). PC IP on the ONT LAN = `192.168.1.11`.

```sh
# from the repository root (UDP/69 needs an elevated shell)
python scripts/tftp_serve2.py 69 firmware/openwrt-galachip
```

```
# in U-Boot, one continuous pass (OpenWrt U-Boot does not service the HW watchdog):
go 41000000            # chainload the new u-boot.bin loaded via tftp
run upgrade_uboot      # writes bootloader  (verify "131072 byte(s) were the same")
reset
# after reset: passively WAIT for "stop autoboot", do NOT spam keys during SPL (triggers YMODEM)
run upgrade_tftp       # writes firmware (~3.47 MB)
boot
```
Boots `OpenWrt SNAPSHOT r37842` from flash. Access afterward: **SSH** (dropbear) and
**LuCI** at `http://192.168.1.1`.

---

## 3. Access methods

| Method | How |
|---|---|
| **SSH** | `ssh root@192.168.1.1` — passwordless (key installed). Primary method. |
| **LuCI web** | `http://192.168.1.1` — OMCI page at `/cgi-bin/luci/admin/pon/omci/config` |
| **Serial console** (U-Boot / recovery) | USB-to-TTL adapter (recommended) or an ESP32/Arduino bridge. 115200 8N1. See below. |

### Serial console wiring

The ONT's UART is **3.3 V**. Never connect 5 V TX to the ONT RX, and never connect the
adapter's VCC pin. The ONT runs on its own power supply.

**Option A: USB-to-TTL adapter (recommended)**

Any 3.3 V USB-UART adapter works (CP2102, CH340, FT232RL, PL2303). Set FT232/CH340 boards
with a voltage jumper to **3.3 V**.

| Adapter | ONT |
|---|---|
| TX | RX |
| RX | TX |
| GND | GND |

Open the adapter's COM port at **115200 8N1** in PuTTY, Tera Term or `screen`.

**Option B: ESP32 / Arduino as a USB-UART bridge (alternative)**

Use this if you don't have an adapter. The board passes bytes between its USB serial port
and a second UART wired to the ONT.

| ESP32 | ONT |
|---|---|
| GPIO17 (TX2) | RX |
| GPIO16 (RX2) | TX |
| GND | GND |

```cpp
// ESP32 passthrough: USB Serial <-> Serial2 (ONT)
void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, 16, 17);   // RX=16, TX=17
}
void loop() {
  while (Serial.available())  Serial2.write(Serial.read());
  while (Serial2.available()) Serial.write(Serial2.read());
}
```

*Arduino variant:* a 3.3 V board with a spare hardware UART (e.g. Leonardo/Micro `Serial1`, or
a Mega in 3.3 V mode) works with the same sketch, using `Serial1` in place of `Serial2`. On a 5 V
board (Uno/Nano), put a level shifter or a resistor divider on the Arduino TX → ONT RX line.
Another Uno option is to hold the ATmega in reset (RESET→GND) and use its USB chip directly as a
plain USB-TTL adapter: **D1 (TX) → ONT TX** and **D0 (RX) → ONT RX**. The labels refer to the
ATmega's side, so the wires don't cross. The 5 V level warning still applies.

> **Note:** while a PPPoE session is dialed **from the PC**, the ONT management IP
> (`192.168.1.1`) becomes unreachable — the PPPoE session takes over the PC's path to it.
> Disconnect PPPoE (`rasdial "Broadband Connection" /DISCONNECT`) to SSH/LuCI in, or use the
> serial console (independent of the network).

---

## 4. Backup (do this before any change)

Full 4 MB chip image + the stock firmware region (for restore):

```
# on the ONT (no dd/sha256sum on device — use cat):
cat /dev/mtdblock0 > /tmp/flash.bin
# push to the PC TFTP receiver (on the PC: python scripts/tftp_recv.py <port> backup/g7-flash.bin):
tftp -p -l /tmp/flash.bin -r g7-flash.bin 192.168.1.11 <port>
```
Store the images in `backup/` at the repository root. This folder is listed in `.gitignore`;
do not commit it, because the dump contains the device's own identity and configuration.
- `g7-flash.bin` — full 4 MB chip; record its SHA256 to verify later restores
- `g7-stock-firmware.bin` — 3866624-byte firmware region, used by `run restore_stock`

---

## 5. Identity configuration — **the key step**

This is what makes the OLT accept and *keep* the ONU. The OLT does **dual-parameter binding**:
it checks **vendor/serial (HWTC)** AND the **equipment-ID (model)**. A mismatch (e.g. model
still `XZ000-G7`) makes the OLT register the ONU, then send `Deactivate_ONU-ID` ~13 min later.
Setting the full Huawei EG8141A5 identity fixes it.

```sh
# --- OMCI identity (over SSH) ---
uci set omci.main.serial='48575443XXXXXXXX'        # HWTC + serial from the original unit
uci set omci.main.vendor_id='HWTC'
uci set omci.main.equipment_id='EG8141A5'
uci set omci.main.hardware_version='EG8141A5'
uci set omci.main.software_version_0='V5R021C00S100'
uci set omci.main.software_version_1='V5R021C00S100'

# --- OLT interoperability profile: Huawei (options: generic/nokia/huawei/zte) ---
uci set omci.main.olt_profile='huawei'
uci set omci.main.olt_profile_force='huawei'

uci commit omci
omcictl config set version 'EG8141A5'              # ONU-G version attribute
reboot
```

The **same fields are editable in LuCI** at `/cgi-bin/luci/admin/pon/omci/config`
(olt_profile, equipment_id, hardware/software_version, omcc_version, password,
loid/loid_password, onu_type, uni_count).

**Verify it's live on the wire after it registers:**
```sh
omcictl mib show 257 0x0000 | grep equipment_id     # -> EG8141A5
omcictl mib show 256 0x0000 | grep -E 'vendor_id|version|serial'
```

---

## 6. VLAN service mode — **the data-path fix**

The OLT runs Internet as **transparent VLAN 155** (it expects tagged-155 on the UNI, and tags
any *untagged* frame as VLAN 1 — which the VLAN-155 Internet GEM then drops → PPPoE error 651).
To present **untagged** internet to your downstream device, the ONT must tag it to 155 itself:

```sh
uci set omci.vlan.mode='tagged'      # modes: transparent / tagged / olt / routed
uci set omci.vlan.vid='155'
uci set omci.vlan.prio='0'
uci commit omci
/etc/init.d/omci-vlan restart
```
This sets `omci.main.untag_vlan=155` via switch offload. Verify:
```sh
xponctl -i pon0 get untag_vlan      # -> sfu_offload=1  sfu_untag_vlan=155
```
> The old `omci.main.vlan_translate='155:0'` option is a **dead setting this firmware ignores** —
> use `omci.vlan` mode=tagged instead.

**Bridge:** `br-lan = lan1 + pon0` (pure transparent media-converter). The ONT does no
routing/NAT — a downstream device does the WAN authentication.

---

## 7. PPPoE dial-up (from the PC / downstream router)

The openwrt-galachip SNAPSHOT has **no pppd/pppoe** — the ONT cannot dial PPPoE itself; it is a
bridge by design, so the downstream device dials. From the Windows PC on the ONT's LAN port:

```powershell
rasdial "Broadband Connection" <PPPOE_USER> <PPPOE_PASS>
# disconnect:  rasdial "Broadband Connection" /DISCONNECT
```
"Broadband Connection" = a WAN Miniport (PPPoE) entry (Type 5). No VLAN tagging needed on the PC
— the ONT tags VLAN 155 (§6).

**Result observed:** `Successfully connected`, WAN IP `100.67.x.x` (carrier CGNAT), public IP
assigned, ping 8.8.8.8 ≈ 17 ms.

For production, plug your own router into the ONT's Ethernet port and set its WAN to PPPoE with
the same credentials.

---

## 8. Diagnostics reference (OpenWrt)

| Command | Shows |
|---|---|
| `grep -oE 'state=O[0-9] onu_id=[0-9]+' /sys/kernel/debug/gc1601-pon/gpon_state` | GPON state (O5 = registered), ONU-ID |
| `cat /sys/kernel/debug/gc1601-pon/gpon_state` | full PLOAM state, OMCI services, optics flags |
| `cat /sys/kernel/debug/gc1601-pon/ploam_log` | raw PLOAM messages (ring buffer) |
| `cat /sys/kernel/debug/gc1601-pon/gpon_events` | SN/ranging grant counters |
| `omci-report` | PLOAM conversation + **Deactivate_ONU-ID history** |
| `omcictl mib list` / `omcictl mib show CLASS [ENT]` | OLT-provisioned OMCI MEs |
| `omcictl config list` / `omcictl config set KEY VALUE` | ONU identity config |
| `xponctl -i pon0 get <name>` | driver state incl. DDM optics (tx/rx power, temp, bias) |

**Optics health reference (good):** `tx_nw ≈ 1.8 mW`, `rx_nw ≈ 8600 nW`, `alarms=0`,
`los_events=0`. (`tx_nw=0` momentarily right after boot = sensor not yet keyed up — ignore.)

---

## 9. Known behaviour / notes

- **"Optical" layer carries no model identity.** The OLT only sees PLOAM (serial + password)
  and OMCI. The ONU's transceiver EEPROM/DDM is local and never sent upstream — nothing optical
  can give the clone away. All model identity lives in OMCI (§5).
- **Re-registration flap is normal** after any omcid reload or reboot: the ONU drops to O3 and
  climbs back to O5 within ~1 min.
- **Load:** OpenWrt vs stock is a wash for an ONT — data forwarding is hardware-offloaded (CPU
  not in the path); idle load avg ≈ 0.2, plenty of free RAM. Firmware load does **not** affect
  registration/deactivation (that's an OLT decision).
- **If it still deactivates with a perfect EG8141A5 identity:** check the real EG8141A5 is
  powered off (SN conflict), and that the LCO has the ONU permanently authorised (not just a
  temporary auto-find). Remaining OMCI fingerprints to match if needed: `vendor_product_code`
  (ONU2-G), capability counts (`uni_count`, `pots_count`), Huawei proprietary MEs.

---

## 10. Restore to stock

From U-Boot (serial console):
```
run restore_stock      # uses the g7-stock-firmware.bin backup
```

---

## Acknowledgements

This project builds on the work of the following open-source projects. Sincere thanks to their
authors and contributors.

| Project | Contribution to this work |
|---|---|
| [**yesrab/openwrt-galachip**](https://github.com/yesrab/openwrt-galachip) | OpenWrt port for the Galachip GC1601 / TP-Link XZ000-G7, including the configurable OMCI identity, VLAN service modes, and PON diagnostics. The firmware images in [`firmware/openwrt-galachip/`](../firmware/openwrt-galachip/) are from its R1.1 release. Without this port, the identity clone would not be possible. |
| [**OpenWrt**](https://github.com/openwrt/openwrt) | The base Linux distribution: UCI configuration, LuCI web interface, dropbear SSH. |
| [**U-Boot**](https://github.com/u-boot/u-boot) | Bootloader used for TFTP flashing, upgrade, and restore. |
| [**Arduino core for ESP32**](https://github.com/espressif/arduino-esp32) | Framework for the ESP32 serial passthrough sketch (§3). |

The firmware images are redistributed unmodified and remain under their original licenses
(OpenWrt and U-Boot are GPL-2.0). Refer to the upstream repositories for source code and license
terms.

---

*Device is the owner's own hardware on their own line; credentials above are the owner's own.*
