# Japanese baseline validation

Validated locally on 2026-09-11 using the original Japanese cartridge and
independent instrumented Beetle. Framework: `5fdcf0c1ceeeb33963dacfc7daedfacba0449d91`;
recomp-ui: `bca0bcc3949ef6f9bbb6b7b021b1ba50c13db4cb`. Build: Release with
`SD_GUNDAM_FAST_BUILD=ON` (generated C at O1, runtime at Release optimization).

| Check | Result |
|---|---|
| Python recompiler suite | 80 passed, 5 optional oracle tests skipped |
| Runtime CTest | 5/5 passed |
| Native-only versus independent Beetle | 40/40 checkpoints, through frame 4,500; 280 byte audits |
| Native execution | 914,443,855 instructions, 8,642,948 dispatch entries |
| Interpreter/fallback execution | 0 / 0; no stopped execution |
| Boot verification gates | Determinism in hybrid, interpreter, and oracle; hybrid/interpreter equality; deliberate WRAM fault detected |
| Window integration | Keyboard input, exact stock presentation, Escape pause stability and resume passed |
| Launcher | Dashboard, settings, controller, and mods captures passed; verified ROM and Japan region inspected |

The comparison covers CPU, WRAM, SRAM, VRAM, VIP, devices, left video, right
video, presented video, and PCM audio. Hash comparisons are audited against
captured bytes. The route is committed as `tests/first-mission-route.json`.
It passes safety/alignment/auto-pause screens, title, Japanese story, and the
opening tactical mission with the unit action menu. It does not complete a
mission, exercise combat, or validate the full campaign, saving/loading, or endings.

## Artifact identities

- Original ROM SHA-256: `98d210dcbd1c5d836aa5bbf018eb26e971711b69b4423187bbb72178d5da9a92`.
- Runtime SHA-256: `82663bbca363bd13e4ec327de19bab3629a389f1d02d18bb06f0b13ef4cf25a0`.
- Oracle SHA-256: `f4ac5fe15b4a0b13d87a16657a76b5645f6e5a13e595a2661c0b01262d1c6a90`.
- Static discovery: 3,180 functions and 137,395 instruction addresses;
  no manual game-specific function seeds.

Private local evidence is in `validation/japanese-native-callback/`,
`validation/boot-gates-callback/`, `validation/window-japanese-callback/`,
and `validation/launcher-japanese/`. Earlier failed native runs are retained:
they exposed shared-tail table entries, indirect-call continuations, and
registered callbacks missing from discovery. Framework regression tests cover
those classes, including negative cases; the final result above uses regenerated
code, not hand-edited cartridge C. Earlier successful hybrid runs still used
fallback and are not the evidence for native-only success.

## Reproduce

After building as described in the README, use new output directories:

```powershell
.\tools\validate.ps1 -Framework '..\_wt-sd-gundam-vbrecomp' `
  -Python 'C:\Users\Matthew\AppData\Local\Programs\Python\Python312\python.exe' `
  -Route 'tests/first-mission-route.json' -NativeOnly `
  -Out 'validation/japanese-native-new'
.\tools\validate.ps1 -Framework '..\_wt-sd-gundam-vbrecomp' `
  -Python 'C:\Users\Matthew\AppData\Local\Programs\Python\Python312\python.exe' `
  -Gates -Out 'validation/boot-gates-new'
```

The runtime still defaults to hybrid execution for untested paths. A match on
this bounded route is not evidence that every game path is generated or correct.
