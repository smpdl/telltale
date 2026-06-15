This is a lightweight C++ poker solver used for fast hand evaluation, Monte Carlo equity estimation, and action recommendations. Python code loads it through a ctypes layer in `telltale/poker/native.py`. 

The library is built on first use if a C++17 compiler is available:

```bash
python -c "from telltale.poker import native; print(native.native_available())"
```

Artifacts land in `build/native_poker_solver/`. Sources are recompiled when any `.cpp` or `.hpp` file in this directory is newer than the shared library.

For the API, all functions write JSON into a caller-provided buffer and return:

- `0` on success
- `-1` if the output buffer is null or too small
- a positive value equal to the required buffer size (including null terminator) when the buffer is too small

On error, the JSON payload contains an `"error"` field. The following are all the functions available to use from the API:

| Function | Description |
| --- | --- |
| `telltale_evaluate7(cards_csv, output, output_length)` | Best five-card rank from seven or more cards |
| `telltale_compare7(cards_a_csv, cards_b_csv, output, output_length)` | Compare two seven-card hands (`-1`, `0`, or `1`) |
| `telltale_estimate_equity(hero, board, num_opponents, dead, iterations, seed, output, output_length)` | Monte Carlo equity simulation |
| `telltale_estimate_equity_vs_range(hero, board, range, dead, iterations, seed, output, output_length)` | Monte Carlo equity simulation against a weighted one-opponent range such as `AhAd:1,KsQs:0.5` |
| `telltale_recommend_action(street, hero_equity, pot_size, amount_to_call, pot_odds, stack_to_pot_ratio, position_bucket, players_remaining, aggression_faced, can_check, legal_actions_csv, hero_stack, minimum_raise_amount, board_texture, street_action_count, previous_aggression_count, output, output_length)` | Weighted action policy recommendation |






































