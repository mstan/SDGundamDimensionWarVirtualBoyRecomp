cmake_minimum_required(VERSION 3.20)
project(SDGundamDimensionWarVirtualBoyRecomp VERSION 0.1.2 LANGUAGES C CXX)
include(CTest)
set(VBRECOMP_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/vbrecomp" CACHE PATH "vbrecomp checkout")
set(RECOMP_UI_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/recomp-ui" CACHE PATH "recomp-ui checkout")
option(SD_GUNDAM_UI "Build the shared launcher and settings" ON)
option(SD_GUNDAM_FAST_BUILD "Use lighter optimization for generated cartridge code during development" OFF)
if(NOT EXISTS "${VBRECOMP_ROOT}/CMakeLists.txt")
    message(FATAL_ERROR "Initialize submodules or set VBRECOMP_ROOT.")
endif()
set(VBRECOMP_GAME sd_gundam CACHE STRING "Generated cartridge module" FORCE)
if(SD_GUNDAM_UI)
    if(NOT EXISTS "${RECOMP_UI_ROOT}/recomp_ui.cmake")
        message(FATAL_ERROR "Initialize submodules or set RECOMP_UI_ROOT.")
    endif()
    set(RECOMP_UI_ENABLE_MODS ON CACHE BOOL "Mod catalog" FORCE)
    include("${RECOMP_UI_ROOT}/recomp_ui.cmake")
endif()
add_subdirectory("${VBRECOMP_ROOT}" vbrecomp)
if(SD_GUNDAM_FAST_BUILD)
    if(MSVC)
        set(_generated_optimization /O1)
    else()
        set(_generated_optimization -O1)
    endif()
    get_target_property(_game_sources vb-runtime SOURCES)
    foreach(_source IN LISTS _game_sources)
        if(_source MATCHES "/generated/sd_gundam_(full|part_[0-9]+)\\.c$")
            set_property(SOURCE "${_source}" TARGET_DIRECTORY vb-runtime
                APPEND PROPERTY COMPILE_OPTIONS ${_generated_optimization})
        endif()
    endforeach()
endif()
set_property(SOURCE "${VBRECOMP_ROOT}/runtime/src/host.cpp" TARGET_DIRECTORY vb-runtime
    APPEND PROPERTY COMPILE_DEFINITIONS VB_GAME_REGION="Japan")
target_compile_definitions(vb-runtime PRIVATE
    VB_GAME_DEFAULT_INTERNAL_SCALE=4
    VB_GAME_ID="sd-gundam-dimension-war"
    VB_GAME_TITLE="SD Gundam: Dimension War Recompiled"
    VB_GAME_SHA256="98d210dcbd1c5d836aa5bbf018eb26e971711b69b4423187bbb72178d5da9a92"
    VB_GAME_CRC32=0x44788197u)
set_target_properties(vb-runtime PROPERTIES OUTPUT_NAME SDGundamDimensionWarVirtualBoyRecomp)
if(SD_GUNDAM_UI)
    add_custom_target(sd-gundam-assets
        COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:vb-runtime>/assets/img"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/boxart.tga"
            "$<TARGET_FILE_DIR:vb-runtime>/assets/img/boxart.tga"
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${CMAKE_CURRENT_SOURCE_DIR}/assets/NOTICE.md"
            "$<TARGET_FILE_DIR:vb-runtime>/assets/GAME-ART-NOTICE.md"
        VERBATIM)
    add_dependencies(vb-runtime sd-gundam-assets)
endif()
find_package(Python3 COMPONENTS Interpreter REQUIRED)
set(SD_GUNDAM_ROM "${CMAKE_CURRENT_SOURCE_DIR}/roms/sd_gundam.vb" CACHE FILEPATH "Original Japanese cartridge for guarded text assets")
set(_text_header "${CMAKE_CURRENT_SOURCE_DIR}/generated/sd_gundam_translation.h")
add_custom_command(OUTPUT "${_text_header}" "${CMAKE_CURRENT_SOURCE_DIR}/dist/sd-gundam-english-0.1.0.vbmod"
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/build_translation.py"
        --rom "${SD_GUNDAM_ROM}" --framework "${VBRECOMP_ROOT}"
    DEPENDS tools/build_translation.py translations/english.json mods/english/manifest.toml
        "${SD_GUNDAM_ROM}" "${CMAKE_CURRENT_SOURCE_DIR}/generated/sd_gundam_dispatch.c"
    VERBATIM)
# vb-runtime is defined in the framework subdirectory. An explicit target
# carries the root-directory generator into its build graph on a clean clone.
add_custom_target(sd-gundam-english-package
    DEPENDS "${_text_header}" "${CMAKE_CURRENT_SOURCE_DIR}/dist/sd-gundam-english-0.1.0.vbmod")
add_dependencies(vb-runtime sd-gundam-english-package)
target_sources(vb-runtime PRIVATE src/translation_mod.cpp src/color_mod.cpp src/widescreen_mod.cpp src/widescreen_scene.cpp "${_text_header}")
add_custom_target(sd-gundam-color-package ALL
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/build_color.py"
    BYPRODUCTS "${CMAKE_CURRENT_SOURCE_DIR}/dist/sd-gundam-color-0.2.2.vbmod"
    DEPENDS tools/build_color.py mods/color/manifest.toml mods/color/palette.txt mods/color/materials.txt
        mods/color/catalog.txt mods/color/tiles.txt
    VERBATIM)
add_custom_target(sd-gundam-widescreen-package ALL
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/tools/build_widescreen.py"
    BYPRODUCTS "${CMAKE_CURRENT_SOURCE_DIR}/dist/sd-gundam-widescreen-0.1.0.vbmod"
    DEPENDS tools/build_widescreen.py mods/widescreen/manifest.toml
    VERBATIM)
