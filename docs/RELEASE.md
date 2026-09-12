# SD Gundam: Dimension War Recompiled 0.1.0

**Early prototype. Bugs are expected.** Later missions and endings have not
received a complete playthrough. This is the first Windows x64 prerelease.

## Download and play

1. Extract the entire `SDGundamDimensionWarVirtualBoyRecomp-windows-x64.zip`.
2. Run `SDGundamDimensionWarVirtualBoyRecomp.exe`, select your own original
   Japanese `.vb` cartridge, and press **Play**.
3. Open **Mods**, select **Install .vbmod**, and choose any included package.
   Enable **English story text**, **Gundam reference colors**, or **Adaptive
   widescreen** independently. Restart after changing language.

The default is Japanese, original red, and native aspect ratio. Widescreen
offers 16:9, 21:9, 32:9 and Adaptive (fit window). The accepted tactical
starfield continuation fills wide margins using native-sized star motifs.
The ZIP and separate mod downloads contain identical packages:

| Package | Version |
|---|---|
| English | 0.1.0 |
| Reference color | 0.2.2 |
| Adaptive widescreen | 0.1.0 |

Required cartridge: 1,048,576 bytes, CRC32 `44788197`, SHA-256
`98d210dcbd1c5d836aa5bbf018eb26e971711b69b4423187bbb72178d5da9a92`.
No ROM, reference patch archive, personal settings or saves are included.
`SHA256SUMS.txt` covers all four downloads. `build-info.json` in the ZIP
identifies source commits, build settings and binary/package hashes.

Keyboard: arrows and WASD are the two directional pads; X/Z are A/B, Q/E are
L/R, Enter is Start and Right Shift is Select. Escape opens settings. The
launcher supports controllers and remapping. Battery saves persist across
restarts and English/Japanese changes; see [save validation](SAVES.md).

When updating, close the game and retain `vbrecomp.cfg`, `keybinds.ini`,
`saves/` and `mods/`. Install newer mod packages through Mods as needed.

## Scope and validation

The Japanese and English opening routes match the independent oracle; save
persistence, color, both eyes, expanded grid/unit rendering, window resizing
and mod settings have targeted validation. The accepted starfield passes
native-state and both-eye replay checks and changes only identified star
pixels in the checked comparison. See [publication checks](PUBLICATION.md),
[color](COLOR.md) and [widescreen](WIDESCREEN.md) for the exact coverage.

The release is a fully optimized build with recomp-ui enabled and development
TCP/CPU tracing disabled. Package checks verify committed dependency pins,
mod contents/defaults, DLL dependencies and the absence of private artifacts.
The extracted bundle is checked with the developer toolchain removed from
PATH, including the launcher and a normal game process.

## Rebuild the package

After a production build with `tools/build.ps1 -Production`, commit source
changes and run `python tools/package-release.py`. This uses only the explicit
runtime, assets, public documentation, notices and three mod packages. It
does not copy a development profile. The package script accepts `--framework`,
`--ui`, `--toolchain`, `--build` and `--out` for separate checkouts.

Central release issue: `beads-vb.4.10`.
