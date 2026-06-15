#include "evaluator.hpp"

#include <algorithm>
#include <array>
#include <map>
#include <sstream>
#include <stdexcept>

namespace telltale::poker {

namespace {

/**
 * Converts a card rank character to its corresponding integer value. 
 * For example, 'A' returns 14, 'K' returns 13, 'Q' returns 12, etc. 
 */
int rank_value(char rank) {
    const std::string ranks = "23456789TJQKA";
    const auto index = ranks.find(rank);
    if (index == std::string::npos) {
        throw std::invalid_argument("invalid card rank");
    }
    return static_cast<int>(index) + 2;
}

/**
 * Returns the label for a hand rank category. 
 * For example, 8 returns "straight flush", 7 returns "four of a kind", etc. 
 */
std::string label_for_category(int category) {
    static const std::array<std::string, 9> labels = {
        "high card",
        "one pair",
        "two pair",
        "three of a kind",
        "straight",
        "flush",
        "full house",
        "four of a kind",
        "straight flush",
    };
    return labels.at(category);
}

/**
 * Returns the ranks with a count other than the excluded count. 
 * For example, if the counts are {2: 2, 3: 2, 4: 1}, then the ranks with count other than 2 are {3, 4}. 
 * This will be used to get the kickers for a hand rank. 
 */
std::vector<int> ranks_with_count_other_than(const std::map<int, int>& counts, int excluded_count) {
    std::vector<int> ranks;
    for (const auto& [rank, count] : counts) {
        if (count != excluded_count) {
            ranks.push_back(rank);
        }
    }
    std::sort(ranks.begin(), ranks.end(), std::greater<int>());
    return ranks;
}

/**
 * Appends a vector of integers to a string stream as a JSON array. 
 * For example, [1, 2, 3] will be appended as "[1,2,3]". 
 */
void append_int_array(std::ostringstream& output, const std::vector<int>& values) {
    output << "[";
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index > 0) {
            output << ",";
        }
        output << values[index];
    }
    output << "]";
}

}

/**
 * Parses a card from a string. 
 * The string should be two characters, the first being the rank and the second being the suit. 
 * For example, "Ah" is the ace of hearts, "Ks" is the king of spades, "2c" is the 2 of clubs, etc. 
 */
Card parse_card(const std::string& value) {
    if (value.size() != 2) {
        throw std::invalid_argument("card must be two characters");
    }
    const char suit = value[1];
    if (suit != 'c' && suit != 'd' && suit != 'h' && suit != 's') {
        throw std::invalid_argument("invalid card suit");
    }
    return Card{rank_value(value[0]), suit};
}


/**
 * Parses a list of cards from a CSV string. 
 * For example, "Ah,Ks,2c" is the ace of hearts, the king of spades, and the 2 of clubs. 
 * The cards are returned in the order they appear in the string. 
 */
std::vector<Card> parse_cards_csv(const char* values) {
    std::vector<Card> cards;
    if (values == nullptr || values[0] == '\0') {
        return cards;
    }
    std::stringstream stream(values);
    std::string item;
    while (std::getline(stream, item, ',')) {
        if (!item.empty()) {
            cards.push_back(parse_card(item));
        }
    }
    return cards;
}

/**
 * Evaluates a 5-card hand and returns a HandRank object.
 * You can read the note.md file for more detail and explanation on how this implementation works. 
 */
HandRank evaluate_5(const std::array<Card, 5>& cards) {
    std::vector<int> values;
    values.reserve(5);
    std::map<int, int> counts;
    bool is_flush = true;
    const char suit = cards[0].suit;
    for (const auto& card : cards) {
        values.push_back(card.rank);
        counts[card.rank] += 1;
        if (card.suit != suit) {
            is_flush = false;
        }
    }
    std::sort(values.begin(), values.end(), std::greater<int>());

    std::vector<int> unique_values = values;
    unique_values.erase(std::unique(unique_values.begin(), unique_values.end()), unique_values.end());

    bool is_straight = false;
    int straight_high = 0;
    if (unique_values.size() == 5) {
        if (unique_values[0] - unique_values[4] == 4) {
            is_straight = true;
            straight_high = unique_values[0];
        } else if (unique_values == std::vector<int>{14, 5, 4, 3, 2}) {
            is_straight = true;
            straight_high = 5;
        }
    }

    std::vector<std::pair<int, int>> by_count;
    for (const auto& [rank, count] : counts) {
        by_count.emplace_back(rank, count);
    }
    std::sort(by_count.begin(), by_count.end(), [](const auto& left, const auto& right) {
        if (left.second != right.second) {
            return left.second > right.second;
        }
        return left.first > right.first;
    });

    if (is_straight && is_flush) {
        return HandRank{8, {straight_high}, label_for_category(8)};
    }
    if (by_count[0].second == 4) {
        return HandRank{7, {by_count[0].first, by_count[1].first}, label_for_category(7)};
    }
    if (by_count[0].second == 3 && by_count[1].second == 2) {
        return HandRank{6, {by_count[0].first, by_count[1].first}, label_for_category(6)};
    }
    if (is_flush) {
        return HandRank{5, values, label_for_category(5)};
    }
    if (is_straight) {
        return HandRank{4, {straight_high}, label_for_category(4)};
    }
    if (by_count[0].second == 3) {
        auto kickers = ranks_with_count_other_than(counts, 3);
        std::vector<int> tiebreakers = {by_count[0].first};
        tiebreakers.insert(tiebreakers.end(), kickers.begin(), kickers.end());
        return HandRank{3, tiebreakers, label_for_category(3)};
    }
    if (by_count[0].second == 2 && by_count[1].second == 2) {
        const int high_pair = std::max(by_count[0].first, by_count[1].first);
        const int low_pair = std::min(by_count[0].first, by_count[1].first);
        return HandRank{2, {high_pair, low_pair, by_count[2].first}, label_for_category(2)};
    }
    if (by_count[0].second == 2) {
        auto kickers = ranks_with_count_other_than(counts, 2);
        std::vector<int> tiebreakers = {by_count[0].first};
        tiebreakers.insert(tiebreakers.end(), kickers.begin(), kickers.end());
        return HandRank{1, tiebreakers, label_for_category(1)};
    }
    return HandRank{0, values, label_for_category(0)};
}

/**
 * Evaluates a 7-card hand and returns a HandRank object.
 * First, we will need to iterate over all possible combinations of 5 cards and evaluate the hand rank.
 * Then, we will compare the hand rank to the best possible hand rank and return the best hand rank.
 */
HandRank evaluate_7(const std::vector<Card>& cards) {
    if (cards.size() < 7) {
        throw std::invalid_argument("evaluate_7 requires at least seven cards");
    }
    bool has_best = false;
    HandRank best;
    for (std::size_t a = 0; a < cards.size() - 4; ++a) {
        for (std::size_t b = a + 1; b < cards.size() - 3; ++b) {
            for (std::size_t c = b + 1; c < cards.size() - 2; ++c) {
                for (std::size_t d = c + 1; d < cards.size() - 1; ++d) {
                    for (std::size_t e = d + 1; e < cards.size(); ++e) {
                        const std::array<Card, 5> hand = {cards[a], cards[b], cards[c], cards[d], cards[e]};
                        const HandRank rank = evaluate_5(hand);
                        if (!has_best || compare_ranks(rank, best) > 0) {
                            best = rank;
                            has_best = true;
                        }
                    }
                }
            }
        }
    }
    return best;
}

/**
 * Compares two hand ranks.
 * Returns -1 if the left hand rank is lower than the right hand rank, 
 * 0 if they are equal, and 1 if the left hand rank is higher than the right hand rank. 
 */
int compare_ranks(const HandRank& left, const HandRank& right) {
    if (left.category != right.category) {
        return left.category > right.category ? 1 : -1;
    }
    const std::size_t limit = std::min(left.tiebreakers.size(), right.tiebreakers.size());
    for (std::size_t index = 0; index < limit; ++index) {
        if (left.tiebreakers[index] != right.tiebreakers[index]) {
            return left.tiebreakers[index] > right.tiebreakers[index] ? 1 : -1;
        }
    }
    if (left.tiebreakers.size() == right.tiebreakers.size()) {
        return 0;
    }
    return left.tiebreakers.size() > right.tiebreakers.size() ? 1 : -1;
}

/**
 * Converts a hand rank to a JSON string.
 * The JSON string will be in the format of:
 * { "category": <category>, "tiebreakers": [<tiebreakers>], "label": "<label>" }
 */
std::string rank_to_json(const HandRank& rank) {
    std::ostringstream output;
    output << "{\"category\":" << rank.category << ",\"tiebreakers\":";
    append_int_array(output, rank.tiebreakers);
    output << ",\"label\":\"" << rank.label << "\"}";
    return output.str();
}

}
