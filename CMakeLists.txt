cmake_minimum_required(VERSION 3.21)
project(T3DAnalogVelocity VERSION 0.2.3 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
find_package(Qt6 6.4 REQUIRED COMPONENTS Widgets)
find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
execute_process(COMMAND id -u OUTPUT_VARIABLE T3D_LOCAL_UID OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
add_executable(t3d_runtime_limiter app/runtime_limiter.cpp)
target_compile_options(t3d_runtime_limiter PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(t3d_runtime_limiter PRIVATE
    T3D_ALLOWED_UID=${T3D_LOCAL_UID}
    T3D_PYTHON="${Python3_EXECUTABLE}"
    T3D_BACKEND="${CMAKE_CURRENT_BINARY_DIR}/driver/backend.py"
    T3D_RUNTIME_CHECK="${CMAKE_CURRENT_BINARY_DIR}/driver/check_runtime.py")
qt_add_executable(t3d_analog app/main.cpp app/mainwindow.cpp app/mainwindow.h app/mainwindow.ui app/interface.cpp app/axissettingsdialog.ui app/telemetryplot.cpp app/telemetryplot.h)
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
    ENVIRONMENT "PYTHONPATH=${CMAKE_CURRENT_SOURCE_DIR}/driver;PYTHONDONTWRITEBYTECODE=1"
    TIMEOUT 45)
add_test(NAME gui_smoke COMMAND t3d_analog --smoke-test)
set_tests_properties(gui_smoke PROPERTIES ENVIRONMENT "QT_QPA_PLATFORM=offscreen" TIMEOUT 10)
