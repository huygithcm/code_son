# fpm_core/CMakeLists.txt — build module Python "fpm" (pure C++ DLL/.pyd).
#
# Cấu hình (Windows, dùng vcpkg toolchain như INSTALL.md):
#   cmake -S fpm_core -B build_fpm -A x64 ^
#     -DCMAKE_TOOLCHAIN_FILE=C:/vcpkg/scripts/buildsystems/vcpkg.cmake ^
#     -DVCPKG_TARGET_TRIPLET=x64-windows ^
#     -DVCPKG_OVERLAY_TRIPLETS=%CD%/custom-triplets ^
#     -DCMAKE_PREFIX_PATH=%CD%/build/vcpkg_installed/x64-windows
#   cmake --build build_fpm --config Release
cmake_minimum_required(VERSION 3.15)
project(fpm LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenCV CONFIG REQUIRED)
find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
find_package(pybind11 CONFIG REQUIRED)

pybind11_add_module(fpm
    fpm_core.cpp
    fpm_match.cpp
    fpm_pybind.cpp
)
target_link_libraries(fpm PRIVATE ${OpenCV_LIBS})

# Copy OpenCV runtime DLLs cạnh .pyd để import được ngay (Windows).
if(WIN32)
    add_custom_command(TARGET fpm POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_RUNTIME_DLLS:fpm> $<TARGET_FILE_DIR:fpm>
        COMMAND_EXPAND_LISTS)
endif()
