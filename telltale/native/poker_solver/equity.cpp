#include "equity.hpp"

#include <algorithm>
#include <array>
#include <iomanip>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>

namespace telltale::poker {

namespace {

/**
 * Returns a standard deck of cards.
 */
std::vector<Card> standard_deck() {
    std::vector<Card> deck;
    const std::string ranks = "23456789TJQKA";
    const std::string suits = "cdhs";
    for (const char suit : suits) {
        for (const char rank : ranks) {
            deck.push_back(parse_card(std::string{rank, suit}));
        }
    }
    return deck;
}

/**
 * Returns a string representation of a card.
 * The string will be in the format of: <rank><suit>
 * For example, "Ah" is the ace of hearts, "Ks" is the king of spades, "2c" is the 2 of clubs, etc.
 */
std::string card_key(const Card& card) {
    return std::to_string(card.rank) + card.suit;
}

/**
 * Ensures that a list of cards are unique.
 * If the list contains duplicate cards, an exception will be thrown.
 */
void ensure_unique(const std::vector<Card>& cards) {
    std::set<std::string> seen;
    for (const auto& card : cards) {
        const auto [_, inserted] = seen.insert(card_key(card));
        if (!inserted) {
            throw std::invalid_argument("known cards must be unique");
        }
    }
}

/**
 * Returns a list of cards that are not in the known cards.
 * The list will be in the order they appear in the standard deck.
 */
std::vector<Card> remaining_deck(const std::vector<Card>& known_cards) {
    std::set<std::string> known;
    for (const auto& card : known_cards) {
        known.insert(card_key(card));
    }
    std::vector<Card> remaining;
    for (const auto& card : standard_deck()) {
        if (known.count(card_key(card)) == 0) {
            remaining.push_back(card);
        }
    }
    return remaining;
}

/**
 * Returns true if a range combo conflicts with the known cards.
 */
bool conflicts_with_known(const RangeCombo& combo, const std::set<std::string>& known) {
    return known.count(card_key(combo.first)) > 0 || known.count(card_key(combo.second)) > 0;
}

/**
 * Returns a list of range combos that do not conflict with the known cards.
 * The list will be in the order they appear in the opponent range.
 */
std::vector<RangeCombo> filter_range(
    const std::vector<RangeCombo>& opponent_range,
    const std::vector<Card>& known_cards
) {
    std::set<std::string> known;
    for (const auto& card : known_cards) {
        known.insert(card_key(card));
    }

    std::vector<RangeCombo> filtered;
    for (const auto& combo : opponent_range) {
        if (!conflicts_with_known(combo, known)) {
            filtered.push_back(combo);
        }
    }
    if (filtered.empty()) {
        throw std::invalid_argument("opponent range has no live combos");
    }
    return filtered;
}

/**
 * Samples a range combo from a weighted range.
 * The range combo will be sampled with a probability proportional to its weight.
 */
RangeCombo sample_combo(const std::vector<RangeCombo>& range, std::mt19937_64& rng) {
    double total_weight = 0.0;
    for (const auto& combo : range) {
        total_weight += combo.weight;
    }

    std::uniform_real_distribution<double> distribution(0.0, total_weight);
    double point = distribution(rng);
    for (const auto& combo : range) {
        point -= combo.weight;
        if (point <= 0.0) {
            return combo;
        }
    }
    return range.back();
}

/**
 * Returns a list of cards that are not in the given combo.
 * The list will be in the order they appear in the deck.
 */
std::vector<Card> deck_without_combo(const std::vector<Card>& deck, const RangeCombo& combo) {
    const std::string first = card_key(combo.first);
    const std::string second = card_key(combo.second);
    std::vector<Card> filtered;
    for (const auto& card : deck) {
        const std::string key = card_key(card);
        if (key != first && key != second) {
            filtered.push_back(card);
        }
    }
    return filtered;
}

}

/**
 * Estimates the equity of a hand using a Monte Carlo simulation.
 */
EquityResult estimate_equity(
    const std::vector<Card>& hero_cards,
    const std::vector<Card>& board_cards,
    int num_opponents,
    const std::vector<Card>& dead_cards,
    int iterations,
    std::uint64_t seed
) {
    if (hero_cards.size() != 2) {
        throw std::invalid_argument("exactly two hero cards are required");
    }
    if (board_cards.size() > 5) {
        throw std::invalid_argument("board cannot contain more than five cards");
    }
    if (num_opponents < 1) {
        throw std::invalid_argument("at least one opponent is required");
    }
    if (iterations < 1) {
        throw std::invalid_argument("iterations must be positive");
    }

    std::vector<Card> known = hero_cards;
    known.insert(known.end(), board_cards.begin(), board_cards.end());
    known.insert(known.end(), dead_cards.begin(), dead_cards.end());
    ensure_unique(known);

    const int board_needed = static_cast<int>(5 - board_cards.size()); // We need to fill the board with 5 cards.
    const int cards_needed = board_needed + (num_opponents * 2); 
    std::vector<Card> deck = remaining_deck(known);
    if (cards_needed > static_cast<int>(deck.size())) {
        throw std::invalid_argument("not enough unknown cards remain");
    }

    std::mt19937_64 rng(seed); // We will use a random number generator to shuffle the deck.
    int wins = 0;
    int ties = 0;
    int losses = 0;

    for (int iteration = 0; iteration < iterations; ++iteration) {
        // Shuffle the deck.
        std::shuffle(deck.begin(), deck.end(), rng);

        std::vector<Card> board = board_cards;
        int offset = 0;
        // Fill the board with the remaining cards.
        for (int index = 0; index < board_needed; ++index) {
            board.push_back(deck[offset++]);
        }

        std::vector<Card> hero_hand = hero_cards; // Add the hero cards to the board.
        hero_hand.insert(hero_hand.end(), board.begin(), board.end());
        const HandRank hero_rank = evaluate_7(hero_hand); // Evaluate the hero hand.

        bool any_better = false; 
        bool any_tied = false;
        // Evaluate the hands of the opponents.
        for (int opponent = 0; opponent < num_opponents; ++opponent) {
            std::vector<Card> opponent_hand = {deck[offset++], deck[offset++]}; // Add the opponent cards to the board.
            opponent_hand.insert(opponent_hand.end(), board.begin(), board.end());
            const int comparison = compare_ranks(hero_rank, evaluate_7(opponent_hand)); // Compare the hero hand to the opponent hand.
            if (comparison < 0) {
                any_better = true;
                break;
            }
            if (comparison == 0) {
                any_tied = true;
            }
        }

        if (any_better) {
            losses += 1;
        } else if (any_tied) {
            ties += 1;
        } else {
            wins += 1;
        }
    }

    const double total = static_cast<double>(iterations);
    return EquityResult{
        wins,
        ties,
        losses,
        iterations,
        wins / total,
        ties / total,
        losses / total,
    };
}

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
) {
    if (hero_cards.size() != 2) {
        throw std::invalid_argument("exactly two hero cards are required");
    }
    if (board_cards.size() > 5) {
        throw std::invalid_argument("board cannot contain more than five cards");
    }
    if (opponent_range.empty()) {
        throw std::invalid_argument("opponent range cannot be empty");
    }
    if (iterations < 1) {
        throw std::invalid_argument("iterations must be positive");
    }

    std::vector<Card> known = hero_cards;
    known.insert(known.end(), board_cards.begin(), board_cards.end());
    known.insert(known.end(), dead_cards.begin(), dead_cards.end());
    ensure_unique(known);

    const int board_needed = static_cast<int>(5 - board_cards.size());
    std::vector<Card> base_deck = remaining_deck(known);
    if (board_needed + 2 > static_cast<int>(base_deck.size())) {
        throw std::invalid_argument("not enough unknown cards remain");
    }

    const std::vector<RangeCombo> live_range = filter_range(opponent_range, known);
    std::mt19937_64 rng(seed);
    int wins = 0;
    int ties = 0;
    int losses = 0;

    for (int iteration = 0; iteration < iterations; ++iteration) {
        const RangeCombo opponent_combo = sample_combo(live_range, rng);
        std::vector<Card> deck = deck_without_combo(base_deck, opponent_combo);
        std::shuffle(deck.begin(), deck.end(), rng);

        std::vector<Card> board = board_cards;
        int offset = 0;
        for (int index = 0; index < board_needed; ++index) {
            board.push_back(deck[offset++]);
        }

        std::vector<Card> hero_hand = hero_cards;
        hero_hand.insert(hero_hand.end(), board.begin(), board.end());
        std::vector<Card> opponent_hand = {opponent_combo.first, opponent_combo.second};
        opponent_hand.insert(opponent_hand.end(), board.begin(), board.end());

        const int comparison = compare_ranks(evaluate_7(hero_hand), evaluate_7(opponent_hand));
        if (comparison > 0) {
            wins += 1;
        } else if (comparison == 0) {
            ties += 1;
        } else {
            losses += 1;
        }
    }

    const double total = static_cast<double>(iterations);
    return EquityResult{
        wins,
        ties,
        losses,
        iterations,
        wins / total,
        ties / total,
        losses / total,
    };
}

/**
 * Parses range entries like "AhAd:1,KsQs:0.5".
 * The range will be in the order they appear in the range CSV string.
 */
std::vector<RangeCombo> parse_range_csv(const std::string& range_csv) {
    std::vector<RangeCombo> range;
    std::stringstream stream(range_csv);
    std::string item;
    while (std::getline(stream, item, ',')) {
        if (item.empty()) {
            continue;
        }
        const std::size_t separator = item.find(':');
        const std::string combo_text = separator == std::string::npos ? item : item.substr(0, separator);
        const std::string weight_text = separator == std::string::npos ? "1" : item.substr(separator + 1);
        if (combo_text.size() != 4) {
            throw std::invalid_argument("range combos must be four card characters like AhAd");
        }

        RangeCombo combo{
            parse_card(combo_text.substr(0, 2)),
            parse_card(combo_text.substr(2, 2)),
            std::stod(weight_text),
        };
        if (card_key(combo.first) == card_key(combo.second)) {
            throw std::invalid_argument("range combo cards must be unique");
        }
        if (combo.weight <= 0.0) {
            throw std::invalid_argument("range combo weights must be positive");
        }
        range.push_back(combo);
    }

    if (range.empty()) {
        throw std::invalid_argument("opponent range cannot be empty");
    }
    return range;
}

/**
 * Converts an equity result to a JSON string.
 * The JSON string will be in the format of:
 * { "wins": <wins>, 
 *  "ties": <ties>, 
 *  "losses": <losses>, 
 *  "iterations": <iterations>, 
 *  "win_probability": <win_probability>, 
 *  "tie_probability": <tie_probability>, 
 *  "loss_probability": <loss_probability> 
 * }
 */
std::string equity_to_json(const EquityResult& result) {
    std::ostringstream output;
    output << std::setprecision(17);
    output << "{\"wins\":" << result.wins
           << ",\"ties\":" << result.ties
           << ",\"losses\":" << result.losses
           << ",\"iterations\":" << result.iterations
           << ",\"win_probability\":" << result.win_probability
           << ",\"tie_probability\":" << result.tie_probability
           << ",\"loss_probability\":" << result.loss_probability
           << "}";
    return output.str();
}

}
