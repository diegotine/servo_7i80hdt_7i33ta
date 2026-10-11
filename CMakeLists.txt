cmake_minimum_required(VERSION 3.21)
project(T3DAnalogVelocity VERSION 0.2.5 LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)
find_package(Qt6 6.4 REQUIRED COMPONENTS Widgets)
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter Development.Module)
execute_process(COMMAND id -u OUTPUT_VARIABLE T3D_LOCAL_UID OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(t3d_runtime_limiter app/runtime_limiter.cpp app/cpu_clock.cpp)
target_compile_options(t3d_runtime_limiter PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(t3d_runtime_limiter PRIVATE
    T3D_ALLOWED_UID=${T3D_LOCAL_UID}
    T3D_ALLOWED_UID_TEXT="${T3D_LOCAL_UID}"
    T3D_PYTHON="${Python3_EXECUTABLE}"
    T3D_BACKEND="${CMAKE_CURRENT_BINARY_DIR}/driver/backend.py"
    T3D_RUNTIME_CHECK="${CMAKE_CURRENT_BINARY_DIR}/driver/check_runtime.py")
qt_add_executable(t3d_analog app/main.cpp app/mainwindow.cpp app/mainwindow.h app/mainwindow.ui app/interface.cpp app/axissettingsdialog.ui app/telemetryplot.cpp app/telemetryplot.h app/pinoutimage.cpp app/pinoutimage.h app/resources.qrc)
target_link_libraries(t3d_analog PRIVATE Qt6::Widgets)
target_include_directories(t3d_analog PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/app)
target_compile_options(t3d_analog PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(t3d_analog PRIVATE T3D_PYTHON="${Python3_EXECUTABLE}")
target_compile_definitions(t3d_analog PRIVATE T3D_VERSION="${PROJECT_VERSION}")
add_custom_target(runtime_files ALL
    COMMAND ${CMAKE_COMMAND} -E make_directory $<TARGET_FILE_DIR:t3d_analog>/driver
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        ${CMAKE_CURRENT_SOURCE_DIR}/driver/mesa7i80hdt.py
        ${CMAKE_CURRENT_SOURCE_DIR}/driver/servo.py
        ${CMAKE_CURRENT_SOURCE_DIR}/driver/backend.py
        ${CMAKE_CURRENT_SOURCE_DIR}/driver/loopback.py
        ${CMAKE_CURRENT_SOURCE_DIR}/driver/timing.py
        ${CMAKE_CURRENT_SOURCE_DIR}/driver/run_backend.py
        ${CMAKE_CURRENT_SOURCE_DIR}/driver/check_runtime.py
        $<TARGET_FILE_DIR:t3d_analog>/driver
    COMMAND ${CMAKE_COMMAND} -E copy_if_different ${CMAKE_CURRENT_SOURCE_DIR}/config.example.json $<TARGET_FILE_DIR:t3d_analog>/config.example.json
    COMMAND ${CMAKE_COMMAND} -E copy_if_different ${CMAKE_CURRENT_SOURCE_DIR}/TESTE_LOOPBACK.md $<TARGET_FILE_DIR:t3d_analog>/TESTE_LOOPBACK.md)
add_dependencies(t3d_analog runtime_files)
enable_testing()
add_test(NAME driver_and_servo
    COMMAND ${Python3_EXECUTABLE} -m unittest discover -s tests -v)
set_tests_properties(driver_and_servo PROPERTIES
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    ENVIRONMENT "PYTHONPATH=${CMAKE_CURRENT_BINARY_DIR}/driver;PYTHONDONTWRITEBYTECODE=1"
    TIMEOUT 45)
add_test(NAME gui_smoke COMMAND t3d_analog --smoke-test)
set_tests_properties(gui_smoke PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen" TIMEOUT 10)

option(T3D_SANITIZERS "Instrument native modules with ASan and UBSan (validation only)" OFF)
# The .py files remain authoritative; .pxd adds native storage for servo state.
execute_process(COMMAND ${Python3_EXECUTABLE} -c "import Cython; print(Cython.__version__)"
    RESULT_VARIABLE CYTHON_STATUS OUTPUT_VARIABLE CYTHON_VERSION OUTPUT_STRIP_TRAILING_WHITESPACE)
if(NOT CYTHON_STATUS EQUAL 0 OR CYTHON_VERSION VERSION_LESS "3.2")
    message(FATAL_ERROR "Cython >=3.2 required. Fedora: install python3-cython and python3-devel")
endif()
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/native")
foreach(module servo mesa7i80hdt loopback timing backend)
    set(generated "${CMAKE_CURRENT_BINARY_DIR}/native/${module}.c")
    set(extra_deps)
    if(module STREQUAL "servo")
        list(APPEND extra_deps "${CMAKE_CURRENT_SOURCE_DIR}/driver/servo.pxd")
    endif()
    add_custom_command(OUTPUT "${generated}"
        COMMAND ${Python3_EXECUTABLE} -m cython -3 --warning-extra --annotate
            -X annotation_typing=False -X infer_types=False
            --module-name ${module} -o "${generated}" "${CMAKE_CURRENT_SOURCE_DIR}/driver/${module}.py"
        DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/driver/${module}.py" ${extra_deps}
        VERBATIM)
    Python3_add_library(native_${module} MODULE WITH_SOABI "${generated}")
    set_target_properties(native_${module} PROPERTIES AUTOMOC OFF AUTOUIC OFF
        OUTPUT_NAME ${module} LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/driver")
    if(T3D_SANITIZERS)
        target_compile_options(native_${module} PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(native_${module} PRIVATE -fsanitize=address,undefined)
    endif()
    add_dependencies(t3d_analog native_${module})
endforeach()

add_test(NAME native_compatibility
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_native_compat.py -v)
set_tests_properties(native_compatibility PROPERTIES
    ENVIRONMENT "PYTHONPATH=${CMAKE_CURRENT_BINARY_DIR}/driver;PYTHONDONTWRITEBYTECODE=1"
    TIMEOUT 15)

Python3_add_library(native_rtcore MODULE WITH_SOABI native/rtcore.cpp)
set_target_properties(native_rtcore PROPERTIES AUTOMOC OFF AUTOUIC OFF
    OUTPUT_NAME _rtcore LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/driver")
target_compile_definitions(native_rtcore PRIVATE T3D_VERSION="${PROJECT_VERSION}")
target_compile_options(native_rtcore PRIVATE -Wall -Wextra -Wpedantic -ffp-contract=off -g)
if(T3D_SANITIZERS)
    target_compile_options(native_rtcore PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(native_rtcore PRIVATE -fsanitize=address,undefined)
endif()
add_dependencies(t3d_analog native_rtcore)

add_executable(test_native_motion tests/test_motion.cpp)
set_target_properties(test_native_motion PROPERTIES AUTOMOC OFF AUTOUIC OFF)
target_include_directories(test_native_motion PRIVATE native)
target_compile_options(test_native_motion PRIVATE -Wall -Wextra -Wpedantic -ffp-contract=off)
add_test(NAME native_motion COMMAND test_native_motion)
