#include "viewport.h"
#include "memory.h"
#include "cpu_state.h"
#include "stub_abort.h"
#include <cstring>
#include <cmath>

namespace {
// The native renderer copies its completed OAM at FFF04586. Latch the matching
// camera, live unit records and occupancy grid at that handoff, never from a
// later presentation frame. This observer changes no guest state.
constexpr unsigned begin = 0x400, bytes = 0x3128, marker = 0x53444757;
struct Metadata { unsigned magic; unsigned char wram[bytes]; } pending{};
uint32_t observe(const CPUState* cpu, uint32_t address, uint32_t, unsigned) {
    if (cpu && cpu->pc == 0xfff04586 && (address & VB_PHYS_MASK) == 0x3e000) {
        std::memcpy(pending.wram, vb_wram_data() + begin, bytes);
        pending.magic = marker;
    }
    return 0;
}
void capture(uint8_t* destination, unsigned size) {
    if (size == sizeof(pending)) std::memcpy(destination, &pending, size);
}
unsigned word(const uint8_t* p) { return p[0] | (unsigned(p[1]) << 8); }
unsigned dword(const uint8_t* p) { return word(p) | (word(p + 2) << 16); }
int signed_word(const uint8_t* p) { return int(int16_t(word(p))); }
bool span(unsigned offset, unsigned size) { return offset <= vb_rom_size() && size <= vb_rom_size() - offset; }
int depth_from_parallax(int p) {
    constexpr int values[] = {-3, -1, 1, 2, 3, 5};
    for (int d = 0; d < 6; ++d) if (values[d] == p) return d;
    return -1;
}
int layer_for(const VbViewportScene* scene, int depth) {
    int layer = -1, current = 5;
    for (int i = 31; i >= 0; --i) {
        const auto* world = scene->worlds + i * 16;
        if (world[0] & 64) break;
        if (!(world[0] & 0xc000)) continue;
        unsigned mode = (world[0] >> 12) & 3;
        if (mode == 2 && (world[0] & 15) == 2) {
            int d = depth_from_parallax(int(int16_t(world[2])));
            if (d >= 0) current = d;
        } else if (mode != 3) continue;
        if (current < depth) break;
        layer = i;
    }
    return layer;
}
void sprite(VbViewportLayout* layout, int layer, int eye, int x, int y,
            unsigned w, unsigned h, const uint16_t* cells, const uint16_t* chars, unsigned count) {
    if (layout->sprite_count >= VB_VIEWPORT_MAX_SPRITES)
        vb_stub_abort_simple("widescreen sprite capacity exceeded", 0);
    layout->sprites[layout->sprite_count++] = {layer, eye, x, y, w, h, count, cells, chars};
}
}

void sd_gundam_track_scene() {
    if (!vb_memory_register_write_observer(observe) || !vb_viewport_track_extra(sizeof(pending), capture))
        vb_stub_abort_simple("widescreen scene observation unavailable", 0);
}

void sd_gundam_expand_units(const VbViewportScene* scene, int width, VbViewportLayout* layout) {
    if (scene->extra_size != sizeof(Metadata)) return;
    Metadata metadata;
    std::memcpy(&metadata, scene->extra, sizeof(metadata));
    if (metadata.magic != marker) return;
    const auto* rom = vb_rom_data();
    const auto* data = metadata.wram;
    const int camera_x = int(int8_t(data[0x420 - begin]));
    const int camera_y = int(int8_t(data[0x421 - begin]));
    const int margin = (width - 384) / 2;
    // Six live records per force; occupancy confirms a unit is still present.
    for (int actor = 0; actor < 12; ++actor) {
        const auto* unit = data + 0x42c - begin + actor * 20;
        unsigned descriptor = dword(unit) & 0xfffff;
        if (descriptor < 0xe8000 || descriptor >= 0xf2000 || !span(descriptor, 88)) continue;
        int x = unit[13], y = unit[14], height = unit[15];
        if (x >= 32 || y >= 32 || height >= 3) continue;
        const auto* cell = data + 0x51c - begin + x * 384 + y * 12 + height * 4;
        if (cell[0] != 1 || cell[1] != (actor / 6) * 15 + actor % 6) continue;
        int depth = camera_y + 5 - y, column = x - camera_x;
        if (depth < 0 || depth >= 6) continue;
        const auto* projection = rom + 0xdd5c8 + depth * 22;
        // Already submitted units retain the original VIP draw and source data.
        if (column >= 0 && column < 11 && signed_word(projection + column * 2)) continue;
        int first = 0, last = 10;
        while (!signed_word(projection + first * 2)) ++first;
        while (!signed_word(projection + last * 2)) --last;
        double pitch = double(signed_word(projection + last * 2) - signed_word(projection + first * 2)) / (last - first);
        int center = int(std::round(191 + (column - 5) * pitch));
        unsigned type = dword(rom + descriptor + 4);
        if (type >= 6) continue;
        unsigned scale = 2 - depth / 2;
        unsigned w = rom[0xdd670 + type * 6 + scale * 2], h = rom[0xdd671 + type * 6 + scale * 2];
        if (!w || !h || w > 64 || h > 64) continue;
        x = center - int(w) * 4;
        y = signed_word(rom + 0xdd64c + (depth * 3 + height) * 2) - int(h) * 8;
        int parallax = int(int8_t(rom[0xdd5c2 + 5 - depth]));
        if (x + int(w) * 8 + std::abs(parallax) <= -margin || x - std::abs(parallax) >= 384 + margin) continue;
        int layer = layer_for(scene, depth);
        if (layer < 0) continue;
        constexpr unsigned bank_fields[] = {6, 4, 2};
        constexpr unsigned map_fields[][2] = {{12,12}, {10,11}, {8,9}};
        unsigned bank_field = bank_fields[scale];
        unsigned bank = dword(rom + descriptor + bank_field * 4) & 0xfffff;
        unsigned count = dword(rom + descriptor + (bank_field + 1) * 4);
        if (count > 2048 || !span(bank, count * 16)) continue;
        for (int eye = 0; eye < 2; ++eye) {
            unsigned map = dword(rom + descriptor + map_fields[scale][eye] * 4) & 0xfffff;
            if (!span(map, w * h * 2)) continue;
            int eye_x = x + (eye ? parallax : -parallax);
            sprite(layout, layer, eye, eye_x, y, w, h,
                reinterpret_cast<const uint16_t*>(rom + map), reinterpret_cast<const uint16_t*>(rom + bank), count);
            if (unit[12] == 1)
                sprite(layout, layer, eye, eye_x, y, 1, 1,
                    reinterpret_cast<const uint16_t*>(rom + 0xdd7e2), scene->chars, 2048);
            if (actor < 6 && unit[17] == 2)
                sprite(layout, layer, eye, eye_x - 8, y, 1, 1,
                    reinterpret_cast<const uint16_t*>(rom + 0xdd7e6), scene->chars, 2048);
        }
    }
}
