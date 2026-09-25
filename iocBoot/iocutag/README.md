# UTAG filtering demo (simple)

A simulated device streams a 1024-sample waveform plus a 32-bit tag word
over the pscdrv protocol. The IOC copies the tag into each record's UTAG,
and a client subscribes to the *same* PV several times with different
pvAccess `utag` filters, so each subscription only sees the updates whose
tag matches.

```
sim.py (fake device, TCP :5678)  -->  pscdemo IOC (st.cmd, sim.db)  -->  Phoebus (demo.bob)
   sends sec/nsec/tag + waveform        WF, Utag-I, CNT records            same PV, different utag filters
```

Files: `sim.py` (device simulator), `sim.db` (records), `st.cmd` (IOC
startup), `demo.bob` (Phoebus screen).

## Requirements

- This branch includes a small driver change (`coreApp/src/devcommon.cpp`) that adds
  `info("TagFromBlock", ...)`, which sets a record's UTAG from the received block.
  The demo needs it.
- EPICS Base 7.0.x with QSRV1 (pva2pva) built in. Tested with 7.0.10.
- libevent >= 2.0.19 (needed by pscdrv).
- Python 3 with `numpy`. Optional: `uvloop` (`pip install uvloop`); without it the
  simulator reaches only about 95 Hz instead of 120.
- Phoebus (tested with 5.0.2) to view `demo.bob`.

## Build

From the top of this pscdrv checkout, point `configure/RELEASE.local` at your
Base, then build:

```
echo 'EPICS_BASE=/path/to/epics-base' > configure/RELEASE.local
make
```

## Run

Use three terminals, all from `iocBoot/iocutag/`.

1. Simulated device:

   ```
   python3 sim.py --bind 127.0.0.1:5678
   ```

2. IOC:

   ```
   ./st.cmd
   ```

   It should print `thesim: Connected`.

3. Screen. Point pvAccess at the local IOC, then open the display:

   ```
   export EPICS_PVA_ADDR_LIST=127.0.0.1
   export EPICS_PVA_AUTO_ADDR_LIST=NO
   /path/to/phoebus/phoebus.sh -resource $PWD/demo.bob
   ```

Beam and auto-toggle start on. Use the Period presets to slow the flip.

Without Phoebus, from any terminal:

```
caget TST:Utag-I
caput TST:Period-SP 2000
```

## Controls and tag values

The device sends a tag word with every update: `0x10` = LBEG, `0x20` = MPEG,
`0` = beam off. It also sends `value`
(111 / 222 / 0) and a per-tick counter `seq`.

| control      | PV                | effect                                              |
|--------------|-------------------|-----------------------------------------------------|
| Beam         | `TST:BEAM`        | beam on/off (off sends tag 0)                       |
| Src          | `TST:SRC`         | LBEG / MPEG                                         |
| Auto-toggle  | `TST:AUTO`        | flip the source automatically                       |
| Period       | `TST:Period-SP`   | ms between auto flips (rounds to whole ticks); presets 100 ms / 1 s / 3 s |

`st.cmd` turns beam and auto-toggle on at startup. The simulator ticks at
120 Hz by default (`--rate`), so a 100 ms period flips every 12 updates.

## Filters used by the screen

A filter is `{utag:{M:<mask>,V:<value>}}` appended to the PV name; an update
is shown only when `(tag & M) == V`. `M` and `V` must be uppercase.

| panel      | filter                 | matches          |
|------------|------------------------|------------------|
| ALL        | none                   | every update     |
| FILTER-A   | `{utag:{M:48,V:16}}`   | LBEG (0x10)      |
| FILTER-B   | `{utag:{M:48,V:32}}`   | MPEG (0x20)      |

Example: `pvmonitor 'TST:Val-I.{utag:{M:48,V:16}}'`

## How it works

- `sim.py` sends one message per tick: an 8-byte header (`PS`, msg id, body
  length), a 20-byte trailer (`sec`, `nsec`, `tag`, `value`, `seq`, big-endian),
  then 1024 big-endian int32 waveform samples.
- In `sim.db`, `Val-I` and `WF` take their timestamp and UTAG from the trailer
  (`TimeFromBlock` / `TagFromBlock`), so they can be filtered. `Utag-I` reads
  the tag as a normal value so it keeps updating live.
- `Seq-I` feeds `Drop-I` / `DropTotal-I` / `Rate-I`, the pipeline health panel.
- `Period-SP` sends message 2 to the simulator; `Period-RB` reads back the
  last value sent.
