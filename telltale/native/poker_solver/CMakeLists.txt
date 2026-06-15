cmake_minimum_required(VERSION 3.16)
project(telltale_poker_solver LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(telltale_poker_solver SHARED
    bindings.cpp
    evaluator.cpp
    equity.cpp
    action_policy.cpp
)

target_include_directories(telltale_poker_solver PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
