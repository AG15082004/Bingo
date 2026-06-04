import random
from typing import Dict, List, Tuple, Union, Optional

# Card column configuration ranges (B, I, N, G, O)
# Customizable if rules change, but default conforms to user specification.
CARD_RANGES = {
    "B": (1, 10),
    "I": (11, 20),
    "N": (21, 30),
    "G": (31, 40),
    "O": (41, 50)
}

def generate_card() -> Tuple[List[List[Union[int, str]]], List[List[bool]]]:
    """
    Generates a randomized Bingo card conforming to B-I-N-G-O column ranges.
    Returns:
        matrix: 5x5 list of numbers (with "FREE" in center)
        marked: 5x5 list of booleans (with True for the FREE space, False elsewhere)
    """
    B_nums = random.sample(range(CARD_RANGES["B"][0], CARD_RANGES["B"][1] + 1), 5)
    I_nums = random.sample(range(CARD_RANGES["I"][0], CARD_RANGES["I"][1] + 1), 5)
    N_nums = random.sample(range(CARD_RANGES["N"][0], CARD_RANGES["N"][1] + 1), 4) # 4 numbers for N (excluding FREE)
    G_nums = random.sample(range(CARD_RANGES["G"][0], CARD_RANGES["G"][1] + 1), 5)
    O_nums = random.sample(range(CARD_RANGES["O"][0], CARD_RANGES["O"][1] + 1), 5)

    matrix: List[List[Union[int, str]]] = []
    marked: List[List[bool]] = []

    for r in range(5):
        row_vals: List[Union[int, str]] = []
        row_marks: List[bool] = []

        # Column 0: B
        row_vals.append(B_nums[r])
        row_marks.append(False)

        # Column 1: I
        row_vals.append(I_nums[r])
        row_marks.append(False)

        # Column 2: N
        if r == 2:
            row_vals.append("FREE")
            row_marks.append(True) # FREE space is automatically marked
        else:
            idx = r if r < 2 else r - 1
            row_vals.append(N_nums[idx])
            row_marks.append(False)

        # Column 3: G
        row_vals.append(G_nums[r])
        row_marks.append(False)

        # Column 4: O
        row_vals.append(O_nums[r])
        row_marks.append(False)

        matrix.append(row_vals)
        marked.append(row_marks)

    return matrix, marked

def check_win(marked: List[List[bool]]) -> Optional[Dict]:
    """
    Checks if a 5x5 marked grid contains any winning pattern (row, column, or diagonal).
    Returns a dict with winning details if found, otherwise None.
    """
    # 1. Check rows
    for r in range(5):
        if all(marked[r][c] for c in range(5)):
            return {
                "won": True,
                "type": "row",
                "index": r,
                "cells": [[r, c] for c in range(5)]
            }

    # 2. Check columns
    for c in range(5):
        if all(marked[r][c] for r in range(5)):
            return {
                "won": True,
                "type": "column",
                "index": c,
                "cells": [[r, c] for r in range(5)]
            }

    # 3. Check Left Diagonal (Top-Left to Bottom-Right)
    if all(marked[i][i] for i in range(5)):
        return {
            "won": True,
            "type": "diagonal",
            "index": 0,  # Left diagonal
            "cells": [[i, i] for i in range(5)]
        }

    # 4. Check Right Diagonal (Top-Right to Bottom-Left)
    if all(marked[i][4 - i] for i in range(5)):
        return {
            "won": True,
            "type": "diagonal",
            "index": 1,  # Right diagonal
            "cells": [[i, 4 - i] for i in range(5)]
        }

    return None
