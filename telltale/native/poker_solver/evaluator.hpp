#pragma once

#include <array>
#include <string>
#include <vector>

namespace telltale::poker {

/**
 * Describes a card in a poker hand. 
 */
struct Card {
    int rank;
    char suit;
};

/**
 * Describes a hand rank in a poker hand. 
 * There are 9 categories of hand ranks in poker, and they are ordered from highest (straight flush) to lowest (high card). 
 */
struct HandRank {
    int category; // the category of the hand rank. 
    std::vector<int> tiebreakers; // tiebreakers are used to break ties within a same category. 
    std::string label; // the label of the hand rank. 
};

/**
 * Parses a card from a string. 
 * The string should be two characters, the first being the rank and the second being the suit. 
 * For example, "Ah" is the ace of hearts, "Ks" is the king of spades, "2c" is the 2 of clubs, etc. 
 */
Card parse_card(const std::string& value);

/**
 * Parses a list of cards from a CSV string. 
 * For example, "Ah,Ks,2c" is the ace of hearts, the king of spades, and the 2 of clubs. 
 * The cards are returned in the order they appear in the string. 
 */
std::vector<Card> parse_cards_csv(const char* values);


/**
 * Evaluates a 5-card hand. This follws the same logic as the Python implementation. 
 */
HandRank evaluate_5(const std::array<Card, 5>& cards);

/**
 * Evaluates a 7-card hand. 
 */
HandRank evaluate_7(const std::vector<Card>& cards);

/**
 * Compares two hand ranks.
 * Returns -1 if the left hand rank is lower than the right hand rank, 
 * 0 if they are equal, and 1 if the left hand rank is higher than the right hand rank. 
 */
int compare_ranks(const HandRank& left, const HandRank& right);

/**
 * Converts a hand rank to a JSON string. 
 */ 
std::string rank_to_json(const HandRank& rank);

}
