#include "viewport.h"
#include "mod_runtime.h"
#include "stub_abort.h"
#include <cstring>
#include <cmath>

void sd_gundam_track_scene();
void sd_gundam_expand_units(const VbViewportScene*, int, VbViewportLayout*);

namespace {
struct GridContext {
    VbViewportScene scene;
    int y = -1, count = 0, center = 0;
    double pitch = 0;
};
GridContext grid[32];
unsigned grid_pixel(const VbViewportScene& scene, int x, int y) {
    const unsigned cell = scene.dram[4096 + (y / 8) * 64 + x / 8];
    const int u = (x & 7) ^ ((cell & 0x2000) ? 7 : 0);
    const int v = (y & 7) ^ ((cell & 0x1000) ? 7 : 0);
    return (scene.chars[(cell & 2047) * 8 + v] >> (u * 2)) & 3;
}
int grid_outside(int x, int y, int* sample_x, int* sample_y, void* opaque) {
    auto& cache = *static_cast<GridContext*>(opaque);
    if (cache.y != y) {
        cache.y = y; cache.count = 0;
        int first = 0, last = 0;
        for (int i = 0; i < 384; ++i) if (grid_pixel(cache.scene, i, y)) {
            if (!cache.count) first = i;
            if (!cache.count || std::abs(i - 192) < std::abs(cache.center - 192)) cache.center = i;
            last = i; ++cache.count;
        }
        cache.pitch = cache.count > 1 ? double(last - first) / (cache.count - 1) : 0;
    }
    if (!cache.count) return 0;
    if (cache.count == 384) *sample_x = (x % 384 + 384) % 384;
    else {
        // Extrapolate the native perspective lattice one scanline at a time.
        // Only its offscreen continuation changes; center pixels stay exact.
        if (cache.count < 3 || cache.pitch < 2) return 0;
        const double line = std::round((x - cache.center) / cache.pitch);
        if (x != int(std::round(cache.center + line * cache.pitch))) return 0;
        *sample_x = cache.center;
    }
    *sample_y = y;
    return 1;
}
int signed_bits(unsigned v, unsigned bits) {
    const unsigned sign = 1u << (bits - 1);
    return int((v & ((1u << bits) - 1)) ^ sign) - int(sign);
}
int classify(const VbViewportScene* scene, void*) {
    bool tactical_backdrop = false, terrain = false, battle_sheet = false, hud = false;
    for (int i = 31; i >= 0; --i) {
        const auto* w = scene->worlds + i * 16;
        if (w[0] & 64) break;
        if (!(w[0] & 0xc000)) continue;
        const unsigned mode = (w[0] >> 12) & 3, map = w[0] & 15;
        if (mode == 0 && map == 4 && w[1] == 8 && w[7] == 383 && w[8] == 226)
            tactical_backdrop = true;
        if (mode == 2 && map == 2 && !(w[0] & 0xf00)) terrain = true;
        if (mode == 2 && (map == 4 || map == 6) && (w[0] & 0x300) == 0x100)
            battle_sheet = true;
        if (mode == 0 && map == 0 && w[1] == 0 && w[7] == 383 && w[8] == 223)
            hud = true;
    }
    if (battle_sheet && hud) return 2;
    return tactical_backdrop && terrain ? 1 : 0;
}
bool star(const uint16_t* chars, unsigned tile) {
    const auto* bytes = reinterpret_cast<const unsigned char*>(chars + tile * 8);
    uint32_t hash = 2166136261u;
    for (int i = 0; i < 16; ++i) hash = (hash ^ bytes[i]) * 16777619u;
    // Observed battle star variants; content identity excludes glyphs/effects
    // that later occupy the same CHR slots. No new stars are synthesized.
    return hash == 0x477976c5 || hash == 0xb326d6ff || hash == 0xf62dc8ed || hash == 0x44521394;
}
void arrange(const VbViewportScene* scene, int kind, int width, VbViewportLayout* layout, void*) {
    if (kind == 1) {
        sd_gundam_expand_units(scene, width, layout);
        for (int i = 31; i >= 0; --i) {
            const auto* w = scene->worlds + i * 16;
            if (w[0] & 64) break;
            if ((w[0] & 0x3fff) != 1 || w[1] != 0 || w[7] != 383 || w[8] != 167
                || w[3] != 55 || (w[6] != 0 && w[6] != 168)) continue;
            grid[i].scene = *scene; grid[i].y = -1;
            layout->worlds[i].outside = grid_outside;
            layout->worlds[i].outside_context = &grid[i];
        }
        return;
    }
    if (kind != 2) return;
    const int margin = (width - 384) / 2;
    for (int i = 31; i >= 0; --i) {
        const auto* w = scene->worlds + i * 16;
        if (w[0] & 64) break;
        if ((w[0] & 0x300f) == 0 && w[1] == 0 && w[7] == 383 && w[8] == 223)
            layout->worlds[i] = {0, 32, 128, 256, -margin, 0, margin, nullptr, nullptr};
    }
    for (unsigned i = 0; i < 1024; ++i) {
        const auto* o = scene->objects + i * 4;
        if (!(o[1] & 0xc000) || !star(scene->chars, o[3] & 2047)) continue;
        const int x = signed_bits(o[0], 10);
        layout->object_shift[i] = (x - 192) * (width - 384) / 384;
    }
}
void activate() {
    char aspect[32];
    if (!vb_mod_option("aspect", aspect, sizeof(aspect)))
        vb_stub_abort_simple("widescreen aspect option unavailable", 0);
    unsigned n = 16;
    if (!std::strcmp(aspect, "21:9")) n = 21;
    else if (!std::strcmp(aspect, "32:9")) n = 32;
    if (!vb_viewport_register("sd-gundam.adaptive-view", n, 9,
        !std::strcmp(aspect, "adaptive"), classify, arrange, nullptr))
        vb_stub_abort_simple("widescreen viewport registration failed", 0);
}
VB_MOD_CONSTRUCTOR(register_widescreen) {
    vb_viewport_track();
    sd_gundam_track_scene();
    vb_mod_register_exclusive_plugin("sd-gundam.adaptive-view", "video.viewport", activate);
}
}
