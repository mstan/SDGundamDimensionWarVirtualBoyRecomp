# English localization reference

Implementation follows validation of the original Japanese game (Beads
`beads-vb.4.1` then `beads-vb.4.2`). Translation, color, and possible widescreen
are separate optional modifications; Japanese red presentation is the baseline.

The owner supplied `sdgundampatch.zip`, containing `sdgundampatch.ips` with no
readme or author attribution. The archive is kept in ignored `reference/`.
`tools/inspect_inputs.py` audits it without altering the cartridge on disk.

- Japanese ROM: 1,048,576 bytes, CRC32 `44788197`.
- ROM SHA-256: `98d210dcbd1c5d836aa5bbf018eb26e971711b69b4423187bbb72178d5da9a92`.
- IPS SHA-256: `4e3da3a54d520d9d14d5c98b4feeb5d39eca81587ee79b2c0ca48cfe61d45e67`.
- 35 records, 1,016 changed bytes, offsets `0x0f98e4` through `0x0f9d6f`.
- Applied in memory, the reference image hashes to
  `a143fb582956ce1f2214c0122a6cdd1f832bc82fb598c4d8a6b21102ccaab906`.

The patched independent Beetle reference completes the 19-checkpoint story
route through frame 2,200. At frame 2,000 the Japanese dialogue is replaced
by readable English ("G Force endeavors to recover MS units.") using the game's
own glyph rendering. No patch records lie outside the small range above.
This confirms the story surface; it does **not** establish whole-game language
coverage or provide new font assets.

Reproduce the private reference with `python tools/inspect_inputs.py
--write-reference-rom`, then capture `reference/sd_gundam_english.vb` with
`tools/capture_route.py --mode oracle`. The compiled Japanese game continues
to require the original ROM. The patched reference is never an input to its
baseline build and remains ignored.

## Reference method

Use the sibling `snesrecomp/GundamWingEndlessDuelSNESRecomp` files:

- `docs/LOCALIZATION_PLAYBOOK.md`: asset interception, exact guards, language
  restoration, screen coverage, and visual validation pitfalls.
- `docs/TRANSLATION_TILEMAP_REFERENCE.md`: recover glyph mappings, editable
  string tables, row geometry, and strict generators.
- `scripts/analyze_reference_ips.py`, `scripts/decode_reference_tilemaps.py`,
  and `scripts/check_localization.py`: examples of the audit/generation loop.

Recover the VB asset format from this cartridge and live VIP state. Do not copy
SNES tile encodings or addresses. Classify every IPS span against reachable
code, text, tilemaps, and graphics. Capture the Japanese and reference-patched
surfaces through independent Beetle runs before implementing a runtime mod.

The game must draw its own translated assets. Use exact source-byte guards,
editable source strings/glyph maps, strict size/unsupported-glyph checks, and
reversible activation. Avoid framebuffer text overlays and pixel-based screen
detection. Runtime ROM data patches also need an audit for instruction bytes
and codegen-embedded constants, which cannot be changed by writing the live
ROM alone. Shared patch support belongs in vbrecomp; game assets and mappings
belong here.

## Runtime integration findings

The current mod host activates plugins before `vb_memory_init` loads the ROM.
An activation callback therefore cannot immediately change cartridge assets.
Prepare the selected language plan during activation, then apply it at a
documented point after ROM validation and before the game consumes the assets.
`vb_rom_data()` currently exposes a read-only view; shared guarded patch support
needs an explicit API instead of casting away const in game code.

The native emitter embeds instruction operands. Audit patch spans against the
generated instruction-address table and ROM disassembly before treating them
as data-only patches. Verify the complete translated runtime against the
independently patched reference, then disable the mod and compare against the
Japanese baseline again. The startup hook, restoration, editable text/glyph
sources, package manifest, and coverage report are the next implementation
milestone, not part of the Japanese bring-up.
