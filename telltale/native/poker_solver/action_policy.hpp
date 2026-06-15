#pragma once

#include <string>
#include <vector>

namespace telltale::poker {

/**
 * Describes the features of a decision.
 * This is the input to the action policy.
 */
struct DecisionFeatures {
    std::string street; 
    double hero_equity; 
    int pot_size;
    int amount_to_call;
    double pot_odds;
    double stack_to_pot_ratio;
    int players_remaining;
    bool can_check;
    std::vector<std::string> legal_actions;
    int hero_stack;
    int minimum_raise_amount;
    std::string board_texture;
    int street_action_count;
    int previous_aggression_count;
};

std::string recommend_action_json(const DecisionFeatures& features);

}
