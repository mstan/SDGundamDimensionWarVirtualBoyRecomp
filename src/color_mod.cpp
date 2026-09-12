#include "renderer.h"
#include "mod_runtime.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <string>
#include <unordered_map>

namespace {
using Mask = std::array<uint8_t, 64>;
std::unordered_map<uint64_t, Mask> materials;
std::unordered_map<uint64_t, Mask> catalog_materials;
std::unordered_map<uint64_t, Mask> shared_materials;
std::array<uint32_t, 256> palette{};

uint64_t key(unsigned map, unsigned kind, unsigned x, unsigned y, uint32_t hash) {
    return hash | (uint64_t(x) << 32) | (uint64_t(y) << 42)
        | (uint64_t(map) << 52) | (uint64_t(kind) << 60);
}

void render(const VbRenderFrame* frame, uint32_t* out, void*) {
    if (!frame->sources) return;
    for (unsigned i = 0; i < VB_RENDER_PIXELS; ++i) {
        const unsigned light = (frame->stock_argb[i] >> 16) & 255;
        if (!light) continue;
        const auto& s = frame->sources[i];
        if (!s.world || s.kind > 3) continue;
        const unsigned texel = s.v * 8 + s.u;
        auto found = materials.find(key(s.map, s.kind, s.x / 8, s.y / 8, s.tile_hash));
        unsigned ink = found == materials.end() ? 0 : found->second[texel];
        const unsigned category = s.kind == 3 ? 3 : 0;
        if (!ink) {
            auto authored = catalog_materials.find(key(0, category, s.x / 8, s.y / 8, s.tile_hash));
            if (authored != catalog_materials.end()) ink = authored->second[texel];
        }
        if (!ink) {
            auto shared = shared_materials.find(s.tile_hash | (uint64_t(category) << 32));
            if (shared != shared_materials.end()) ink = shared->second[texel];
        }
        if (!ink) continue;
        const unsigned rgb = palette[ink];
        const unsigned r = (rgb >> 16) & 255, g = (rgb >> 8) & 255, b = rgb & 255;
        const unsigned peak = std::max({r, g, b});
        if (!peak) continue;
        // Hue only. Preserve every native black gap and brightness-register fade.
        out[i] = 0xff000000u | ((r * light / peak) << 16)
            | ((g * light / peak) << 8) | (b * light / peak);
    }
}

void activate() {
    materials.clear();
    catalog_materials.clear();
    shared_materials.clear();
    palette.fill(0);
    char path[1024];
    if (vb_mod_asset("palette.txt", path, sizeof(path))) {
        std::ifstream input(path); unsigned ink, rgb;
        while (input >> std::dec >> ink >> std::hex >> rgb)
            if (ink > 0 && ink < palette.size() && rgb <= 0xffffff) palette[ink] = rgb;
    }
    if (vb_mod_asset("materials.txt", path, sizeof(path))) {
        std::ifstream input(path); unsigned map, kind, x, y, hash; std::string mask;
        while (input >> std::dec >> map >> kind >> x >> y >> std::hex >> hash >> mask) {
            if (map > 255 || kind > 3 || x > 1023 || y > 1023 || mask.size() != 64) continue;
            Mask values{}; bool valid = true;
            for (unsigned i = 0; i < 64; ++i) {
                const int digit = mask[i] >= '0' && mask[i] <= '9' ? mask[i] - '0'
                    : mask[i] >= 'a' && mask[i] <= 'f' ? mask[i] - 'a' + 10 : -1;
                if (digit < 0) { valid = false; break; }
                values[i] = uint8_t(digit);
            }
            if (valid) materials[key(map, kind, x, y, hash)] = values;
        }
    }
    for (bool shared : {false, true}) {
        if (!vb_mod_asset(shared ? "tiles.txt" : "catalog.txt", path, sizeof(path))) continue;
        std::ifstream input(path);
        unsigned category, x = 0, y = 0, hash;
        std::string mask;
        while (input >> std::dec >> category) {
            if (!shared && !(input >> x >> y)) break;
            if (!(input >> std::hex >> hash >> mask)) break;
            if ((category != 0 && category != 3) || x > 1023 || y > 1023 || mask.size() != 128) continue;
            Mask values{};
            bool valid = true;
            for (unsigned i = 0; i < 128; ++i) {
                const int digit = mask[i] >= '0' && mask[i] <= '9' ? mask[i] - '0'
                    : mask[i] >= 'a' && mask[i] <= 'f' ? mask[i] - 'a' + 10 : -1;
                if (digit < 0) { valid = false; break; }
                values[i / 2] = uint8_t((values[i / 2] << 4) | digit);
            }
            if (!valid) continue;
            if (shared) shared_materials[hash | (uint64_t(category) << 32)] = values;
            else catalog_materials[key(0, category, x, y, hash)] = values;
        }
    }
    vb_renderer_register("sd-gundam.reference-color", render, nullptr);
}

VB_MOD_CONSTRUCTOR(register_color) {
    // Capture ownership even while disabled, so toggling a paused frame works.
    vb_renderer_track_texels();
    vb_mod_register_exclusive_plugin("sd-gundam.reference-color", "video.renderer", activate);
}
}
