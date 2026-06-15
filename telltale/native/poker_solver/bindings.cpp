#include "action_policy.hpp"
#include "equity.hpp"
#include "evaluator.hpp"

#include <cstring>
#include <exception>
#include <sstream>

namespace {

/**
 * Writes the output to the given buffer.
 * Returns 0 on success, -1 if the output buffer is null or too small, and the required buffer size (including null terminator) if the buffer is too small.
 */
int write_output(const std::string& value, char* output, int output_length) {
    if (output == nullptr || output_length <= 0) {
        return -1;
    }
    if (static_cast<int>(value.size()) + 1 > output_length) {
        return static_cast<int>(value.size()) + 1;
    }
    std::memcpy(output, value.c_str(), value.size() + 1);
    return 0;
}

/**
 * Returns a JSON string representing an error.
 * The JSON string will be in the format of: {"error":"<error message>"}
 */
std::string error_json(const std::exception& error) {
    return std::string("{\"error\":\"") + error.what() + "\"}";
}

/**
 * Splits a CSV string into a vector of strings.
 * The strings will be in the order they appear in the CSV string.
 * The strings will be trimmed of whitespace.
 */
std::vector<std::string> split_csv(const char* values) {
    std::vector<std::string> items;
    if (values == nullptr || values[0] == '\0') {
        return items;
    }
    std::stringstream stream(values);
    std::string item;
    while (std::getline(stream, item, ',')) {
        if (!item.empty()) {
            items.push_back(item);
        }
    }
    return items;
}

}

extern "C" int telltale_evaluate7(const char* cards_csv, char* output, int output_length) {
    try {
        return write_output(telltale::poker::rank_to_json(telltale::poker::evaluate_7(telltale::poker::parse_cards_csv(cards_csv))), output, output_length);
    } catch (const std::exception& error) {
        return write_output(error_json(error), output, output_length);
    }
}

extern "C" int telltale_compare7(const char* cards_a_csv, const char* cards_b_csv, char* output, int output_length) {
    try {
        const auto left = telltale::poker::evaluate_7(telltale::poker::parse_cards_csv(cards_a_csv));
        const auto right = telltale::poker::evaluate_7(telltale::poker::parse_cards_csv(cards_b_csv));
        return write_output("{\"comparison\":" + std::to_string(telltale::poker::compare_ranks(left, right)) + "}", output, output_length);
    } catch (const std::exception& error) {
        return write_output(error_json(error), output, output_length);
    }
}

extern "C" int telltale_estimate_equity(
    const char* hero_csv,
    const char* board_csv,
    int num_opponents,
    const char* dead_csv,
    int iterations,
    unsigned long long seed,
    char* output,
    int output_length
) {
    try {
        const auto result = telltale::poker::estimate_equity(
            telltale::poker::parse_cards_csv(hero_csv),
            telltale::poker::parse_cards_csv(board_csv),
            num_opponents,
            telltale::poker::parse_cards_csv(dead_csv),
            iterations,
            seed
        );
        return write_output(telltale::poker::equity_to_json(result), output, output_length);
    } catch (const std::exception& error) {
        return write_output(error_json(error), output, output_length);
    }
}

extern "C" int telltale_estimate_equity_vs_range(
    const char* hero_csv,
    const char* board_csv,
    const char* range_csv,
    const char* dead_csv,
    int iterations,
    unsigned long long seed,
    char* output,
    int output_length
) {
    try {
        const auto result = telltale::poker::estimate_equity_vs_range(
            telltale::poker::parse_cards_csv(hero_csv),
            telltale::poker::parse_cards_csv(board_csv),
            telltale::poker::parse_range_csv(range_csv == nullptr ? "" : range_csv),
            telltale::poker::parse_cards_csv(dead_csv),
            iterations,
            seed
        );
        return write_output(telltale::poker::equity_to_json(result), output, output_length);
    } catch (const std::exception& error) {
        return write_output(error_json(error), output, output_length);
    }
}

extern "C" int telltale_recommend_action(
    const char* street,
    double hero_equity,
    int pot_size,
    int amount_to_call,
    double pot_odds,
    double stack_to_pot_ratio,
    int players_remaining,
    bool can_check,
    const char* legal_actions_csv,
    int hero_stack,
    int minimum_raise_amount,
    const char* board_texture,
    int street_action_count,
    int previous_aggression_count,
    char* output,
    int output_length
) {
    try {
        const telltale::poker::DecisionFeatures features{
            street == nullptr ? "" : street,
            hero_equity,
            pot_size,
            amount_to_call,
            pot_odds,
            stack_to_pot_ratio,
            players_remaining,
            can_check,
            split_csv(legal_actions_csv),
            hero_stack,
            minimum_raise_amount,
            board_texture == nullptr ? "dry" : board_texture,
            street_action_count,
            previous_aggression_count,
        };
        return write_output(telltale::poker::recommend_action_json(features), output, output_length);
    } catch (const std::exception& error) {
        return write_output(error_json(error), output, output_length);
    }
}
