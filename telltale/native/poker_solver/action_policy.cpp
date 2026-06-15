#include "action_policy.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <map>
#include <sstream>
#include <string>

namespace telltale::poker {

namespace {

/**
 * Checks if an action is legal.
 * Returns true if the action is in the list of legal actions, false otherwise.
 */
bool has_action(const DecisionFeatures& features, const std::string& action) {
    return std::find(features.legal_actions.begin(), features.legal_actions.end(), action) != features.legal_actions.end();
}

/**
 * Adds a weight to an action if the action is legal.
 * The weight will be the maximum of 0.0 and the given weight if the action is legal, 0.0 otherwise.
 */
void add_if_legal(
    const DecisionFeatures& features,
    std::map<std::string, double>& weights,
    const std::string& action,
    double weight
) {
    if (has_action(features, action)) {
        weights[action] = std::max(0.0, weight);
    }
}

/**
 * Returns the suggested amount to bet or raise.
 * The amount will be the maximum of 0 and the hero stack.
 * If the amount to call is greater than 0, the amount will be the maximum of the minimum raise and the pot size divided by 2.
 * If the amount to call is 0, the amount will be the maximum of the minimum raise and the pot size divided by 2.
 */
int suggested_amount(const DecisionFeatures& features) {
    const int stack = std::max(0, features.hero_stack);
    if (stack <= 0) {
        return 0;
    }
    const int minimum_raise = std::max(1, features.minimum_raise_amount);
    const int base = std::max(minimum_raise, features.pot_size / 2);
    if (features.amount_to_call > 0) {
        const int minimum_total = features.amount_to_call + minimum_raise;
        return std::min(stack, std::max(minimum_total, features.amount_to_call + base));
    }
    return std::min(stack, base);
}

/**
 * Returns the amount options for a given decision.
 * The small amount will be the maximum of the minimum total and the pot divided by 3.
 * The medium amount will be the maximum of the minimum total and the pot divided by 2.
 * The large amount will be the maximum of the minimum total and the pot.
 */
std::map<std::string, int> amount_options(const DecisionFeatures& features) {
    const int stack = std::max(0, features.hero_stack);
    const int minimum_raise = std::max(1, features.minimum_raise_amount);
    const int pot = std::max(1, features.pot_size);
    const int minimum_total = features.amount_to_call > 0
        ? features.amount_to_call + minimum_raise
        : minimum_raise;
    return {
        {"small", std::min(stack, std::max(minimum_total, pot / 3))},
        {"medium", std::min(stack, std::max(minimum_total, pot / 2))},
        {"large", std::min(stack, std::max(minimum_total, pot))},
        {"all_in", stack},
    };
}

/**
 * Returns the amount options as a JSON string.
 * The JSON string will be in the format of:
 * { "small": <small>, "medium": <medium>, "large": <large>, "all_in": <all_in> }
 */
std::string amount_options_json(const std::map<std::string, int>& options) {
    std::ostringstream output;
    output << "{";
    bool first = true;
    for (const auto& [label, amount] : options) {
        if (!first) {
            output << ",";
        }
        first = false;
        output << "\"" << label << "\":" << amount;
    }
    output << "}";
    return output.str();
}

/**
 * Returns the value threshold for a given decision.
 * The value threshold will be the equity threshold for the given street.
 */
double value_threshold(const DecisionFeatures& features) {
    if (features.street == "preflop") {
        return 0.63;
    }
    if (features.street == "flop") {
        return 0.60;
    }
    if (features.street == "turn") {
        return 0.58;
    }
    if (features.street == "river") {
        return 0.55;
    }
    return 0.60;
}

/**
 * Returns the raise threshold for a given decision.
 * The raise threshold will be the equity threshold for the given street.
 */
double raise_threshold(const DecisionFeatures& features) {
    if (features.street == "preflop") {
        return 0.74;
    }
    if (features.street == "flop") {
        return 0.72;
    }
    if (features.street == "turn") {
        return 0.70;
    }
    if (features.street == "river") {
        return 0.67;
    }
    return 0.72;
}

/**
 * Returns the board caution for a given decision.
 */
double board_caution(const DecisionFeatures& features) {
    if (features.board_texture == "wet" || features.board_texture == "monotone") {
        return 0.72;
    }
    if (features.board_texture == "connected" || features.board_texture == "two_tone") {
        return 0.85;
    }
    if (features.board_texture == "paired") {
        return 0.92;
    }
    return 1.0;
}

/**
 * Returns the risk label for a given decision.
 */
std::string risk_label(const DecisionFeatures& features, const std::string& top_action) {
    if (top_action == "all_in" || features.stack_to_pot_ratio <= 1.0) {
        return "high";
    }
    if (top_action == "bet" || top_action == "raise" || features.board_texture == "wet" || features.board_texture == "monotone") {
        return "medium";
    }
    return "low";
}

/**
 * Returns the hand strength bucket for a given equity.
 */
std::string hand_strength_bucket(double equity) {
    if (equity >= 0.82) {
        return "monster";
    }
    if (equity >= 0.62) {
        return "strong";
    }
    if (equity >= 0.42) {
        return "medium";
    }
    return "weak";
}

/**
 * Returns the stack pressure bucket for a given decision.
 */
std::string spr_bucket(const DecisionFeatures& features) {
    if (features.stack_to_pot_ratio <= 1.5) {
        return "low";
    }
    if (features.stack_to_pot_ratio <= 4.0) {
        return "medium";
    }
    return "deep";
}

/**
 * Returns the abstract action labels for a given decision.
 */
std::vector<std::string> abstract_action_labels(const DecisionFeatures& features) {
    std::vector<std::string> labels;
    if (has_action(features, "fold")) {
        labels.push_back("fold");
    }
    if (has_action(features, "check")) {
        labels.push_back("check");
    }
    if (has_action(features, "call")) {
        labels.push_back("call");
    }
    if (has_action(features, "bet")) {
        labels.push_back("bet_33");
        labels.push_back("bet_66");
        labels.push_back("bet_100");
    }
    if (has_action(features, "raise")) {
        labels.push_back("raise_2_5x");
        labels.push_back("raise_pot");
    }
    if (has_action(features, "all_in")) {
        labels.push_back("all_in");
    }
    return labels;
}

/**
 * Returns a JSON string representing a vector of strings.
 * The JSON string will be in the format of: [ "<value1>", "<value2>", "<value3>" ]
 */
std::string string_array_json(const std::vector<std::string>& values) {
    std::ostringstream output;
    output << "[";
    bool first = true;
    for (const auto& value : values) {
        if (!first) {
            output << ",";
        }
        first = false;
        output << "\"" << value << "\"";
    }
    output << "]";
    return output.str();
}

}

/**
 * Scores each legal action, normalizes to
 * probabilities, and returns a JSON decision payload.
 *
 * Algorithm:
 * 1. Derive context flags from features:
 *    - facing_bad_price: must call and equity is >3pp below pot odds
 *    - multiway: 3+ players still in the hand
 *    - caution: board_texture dampener (wet/monotone boards score lower)
 *    - value_line / raise_line: street-specific equity cutoffs for betting
 *    - aggression_penalty: shrinks call/raise weight after prior aggression
 *    - multiway_penalty / pressure_bonus: fewer bets multiway, more after
 *      repeated action on the street
 *
 * 2. Assign nonnegative weights only to legal actions (via add_if_legal):
 *    - If can_check: check vs bet vs all-in using value_line and stack depth
 *    - Else: fold vs call vs raise vs all-in using pot odds, raise_line, and
 *      the modifiers above
 *
 * 3. Normalize weights into probabilities (uniform fallback if none qualify).
 *
 * 4. Pick suggested_action = highest probability; decision_margin = gap to
 *    second-best. confidence blends margin with |equity - pot_odds|.
 *
 * 5. Attach sizing: suggested_amount (single chip count) and amount_options
 *    (small/medium/large/all_in) from pot fractions and raise minimums.
 *
 * Output JSON keys: probabilities, suggested_action, suggested_amount,
 * equity, pot_odds, confidence, explanation, risk_label, board_texture,
 * decision_margin, amount_options.
 */
std::string recommend_action_json(const DecisionFeatures& features) {
    std::map<std::string, double> weights;
    const double equity = features.hero_equity;
    const bool facing_bad_price = features.amount_to_call > 0 && equity + 0.03 < features.pot_odds;
    const bool multiway = features.players_remaining >= 3;
    const double caution = board_caution(features);
    const double value_line = value_threshold(features);
    const double raise_line = raise_threshold(features);
    const double aggression_penalty = 1.0 / (1.0 + (0.12 * std::max(0, features.previous_aggression_count)));
    const double multiway_penalty = multiway ? 0.72 : 1.0;
    const double pressure_bonus = 1.0 + (0.08 * std::max(0, features.street_action_count));

    if (features.can_check) {
        add_if_legal(features, weights, "check", equity < value_line ? 3.2 : 0.8);
        add_if_legal(
            features,
            weights,
            "bet",
            equity >= value_line ? 3.6 * caution * multiway_penalty * pressure_bonus : 0.35
        );
        add_if_legal(
            features,
            weights,
            "all_in",
            equity >= 0.82 && features.stack_to_pot_ratio <= 1.15 ? 1.4 * multiway_penalty : 0.08
        );
    } else {
        add_if_legal(features, weights, "fold", facing_bad_price ? 3.8 : 0.35);
        add_if_legal(features, weights, "call", facing_bad_price ? 0.55 : (equity >= raise_line ? 1.7 : 2.5) * aggression_penalty);
        add_if_legal(
            features,
            weights,
            "raise",
            equity >= raise_line ? 3.4 * caution * multiway_penalty * aggression_penalty : 0.2
        );
        add_if_legal(
            features,
            weights,
            "all_in",
            equity >= 0.84 && features.stack_to_pot_ratio <= 1.25 ? 1.6 * multiway_penalty : 0.08
        );
    }

    if (weights.empty()) {
        for (const auto& action : features.legal_actions) {
            weights[action] = 1.0;
        }
    }

    double total = 0.0;
    for (const auto& [_, weight] : weights) {
        total += weight;
    }
    if (total <= 0.0) {
        total = static_cast<double>(weights.size());
        for (auto& [_, weight] : weights) {
            weight = 1.0;
        }
    }

    std::string top_action;
    double top_probability = -1.0;
    double second_probability = -1.0;
    std::ostringstream probabilities;
    probabilities << std::setprecision(17);
    probabilities << "{";
    bool first = true;
    for (const auto& [action, weight] : weights) {
        const double probability = weight / total;
        if (!first) {
            probabilities << ",";
        }
        first = false;
        probabilities << "\"" << action << "\":" << probability;
        if (probability > top_probability) {
            second_probability = top_probability;
            top_probability = probability;
            top_action = action;
        } else if (probability > second_probability) {
            second_probability = probability;
        }
    }
    probabilities << "}";
    if (second_probability < 0.0) {
        second_probability = 0.0;
    }
    const double decision_margin = std::max(0.0, top_probability - second_probability);
    const auto options = amount_options(features);
    const auto abstract_actions = abstract_action_labels(features);
    const std::string strength_bucket = hand_strength_bucket(equity);
    const std::string stack_pressure_bucket = spr_bucket(features);

    std::ostringstream explanation;
    explanation << "equity " << equity
                << ", pot odds " << features.pot_odds
                << ", texture " << features.board_texture
                << ", players " << features.players_remaining;

    std::ostringstream output;
    output << std::setprecision(17);
    output << "{\"probabilities\":" << probabilities.str()
           << ",\"suggested_action\":\"" << top_action << "\""
           << ",\"suggested_amount\":" << suggested_amount(features)
           << ",\"equity\":" << equity
           << ",\"pot_odds\":" << features.pot_odds
           << ",\"confidence\":" << std::min(0.95, 0.50 + decision_margin + (0.15 * std::abs(equity - features.pot_odds)))
           << ",\"explanation\":\"" << explanation.str() << "\""
           << ",\"risk_label\":\"" << risk_label(features, top_action) << "\""
           << ",\"board_texture\":\"" << features.board_texture << "\""
           << ",\"decision_margin\":" << decision_margin
           << ",\"amount_options\":" << amount_options_json(options)
           << ",\"hand_strength_bucket\":\"" << strength_bucket << "\""
           << ",\"spr_bucket\":\"" << stack_pressure_bucket << "\""
           << ",\"abstract_actions\":" << string_array_json(abstract_actions) << "}";
    return output.str();
}

}
