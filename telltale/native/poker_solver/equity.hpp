#pragma once

#include "evaluator.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace telltale::poker {

/**
 * Describes the result of a Monte Carlo equity estimation.
 */
struct EquityResult {
    int wins;
    int ties;
    int losses;
    int iterations;
    double win_probability;
    double tie_probability;
    double loss_probability;
};

/**
 * Describes a weighted two-card opponent range combo (e.g. "AhAd:1,KsQs:0.5").
 * This will be used to sample opponent hole cards from a weighted range. 
 */
struct RangeCombo {
    Card first;
    Card second;
    double weight;
};

/**
 * Estimates the equity of a hand using a Monte Carlo simulation.
 * The simulation will be run for the given number of iterations and the seed will be used to randomize the simulation.
 */
EquityResult estimate_equity(
    const std::vector<Card>& hero_cards,
    const std::vector<Card>& board_cards,
    int num_opponents,
    const std::vector<Card>& dead_cards,
    int iterations,
    std::uint64_t seed
);

/**
 * Estimates hero equity against a weighted one-opponent range.
 */
EquityResult estimate_equity_vs_range(
    const std::vector<Card>& hero_cards,
    const std::vector<Card>& board_cards,
    const std::vector<RangeCombo>& opponent_range,
    const std::vector<Card>& dead_cards,
    int iterations,
    std::uint64_t seed
);

/**
 * Parses range entries like "AhAd:1,KsQs:0.5".
 */
std::vector<RangeCombo> parse_range_csv(const std::string& range_csv);

/**
 * Converts an equity result to a JSON string.
 * The JSON string will be in the format of:
 * { "wins": <wins>, 
 *  "ties": <ties>, 
 *  "losses": <losses>, 
 *  "equity": <win_probability + (tie_probability * 0.5)>,
 * "iterations": <iterations>, 
 * "win_probability": <win_probability>, 
 * "tie_probability": <tie_probability>, 
 * "loss_probability": <loss_probability> 
 * }
 */
std::string equity_to_json(const EquityResult& result);

}
