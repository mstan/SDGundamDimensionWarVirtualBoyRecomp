#include "mod_runtime.h"
#include "rom_patch.h"
#include "sd_gundam_translation.h"
#include <cstdio>
#include <cstdlib>

static void select_language(int english) {
    if (!vb_rom_patch_select(sd_gundam_text, sd_gundam_text_count, english)) {
        std::fputs("SD Gundam: translation data failed its exact byte guards.\n", stderr);
        std::abort();
    }
}
static void japanese() { select_language(0); }
static void english() { select_language(1); }
VB_MOD_CONSTRUCTOR(register_translation) {
    vb_mod_register_reset_callback(japanese);
    vb_mod_register_exclusive_plugin("sd-gundam.reference-english", "rom.assets", english);
}
