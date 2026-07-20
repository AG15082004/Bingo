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
    Generates a randomized Bingo card containing exactly 25 unique numbers ranging from 1 to 25.
    Returns:
        matrix: 5x5 list of numbers
        marked: 5x5 list of booleans (False everywhere initially)
    """
    nums = list(range(1, 26))
    random.shuffle(nums)

    matrix: List[List[Union[int, str]]] = []
    marked: List[List[bool]] = []

    for r in range(5):
        row_vals: List[Union[int, str]] = [nums[r * 5 + c] for c in range(5)]
        row_marks: List[bool] = [False] * 5
        matrix.append(row_vals)
        marked.append(row_marks)

    return matrix, marked

def count_completed_lines(marked: List[List[bool]]) -> int:
    """
    Counts the number of completed lines (rows, columns, diagonals).
    """
    lines = 0
    # Rows
    for r in range(5):
        if all(marked[r][c] for c in range(5)):
            lines += 1
    # Columns
    for c in range(5):
        if all(marked[r][c] for r in range(5)):
            lines += 1
    # Diagonals
    if all(marked[i][i] for i in range(5)):
        lines += 1
    if all(marked[i][4 - i] for i in range(5)):
        lines += 1
    return lines

def get_completed_lines_info(marked: List[List[bool]]) -> dict:
    """
    Finds all completed lines and their cell coordinates.
    Returns a dictionary with count of lines and list of cells belonging to completed lines.
    """
    completed_rows = []
    completed_cols = []
    diag1 = False
    diag2 = False

    for r in range(5):
        if all(marked[r][c] for c in range(5)):
            completed_rows.append(r)

    for c in range(5):
        if all(marked[r][c] for r in range(5)):
            completed_cols.append(c)

    if all(marked[i][i] for i in range(5)):
        diag1 = True

    if all(marked[i][4 - i] for i in range(5)):
        diag2 = True

    # Count
    completed_count = len(completed_rows) + len(completed_cols) + (1 if diag1 else 0) + (1 if diag2 else 0)

    # Collect cells to highlight
    cells = []
    for r in completed_rows:
        for c in range(5):
            if [r, c] not in cells:
                cells.append([r, c])
    for c in completed_cols:
        for r in range(5):
            if [r, c] not in cells:
                cells.append([r, c])
    if diag1:
        for i in range(5):
            if [i, i] not in cells:
                cells.append([i, i])
    if diag2:
        for i in range(5):
            if [i, 4 - i] not in cells:
                cells.append([i, 4 - i])

    return {
        "count": completed_count,
        "cells": cells
    }

def check_win(marked: List[List[bool]]) -> Optional[Dict]:
    """
    Checks if a 5x5 marked grid contains 5 or more completed lines.
    Returns a dict with winning details if found, otherwise None.
    """
    info = get_completed_lines_info(marked)
    if info["count"] >= 5:
        return {
            "won": True,
            "type": "multiple",
            "index": 0,
            "cells": info["cells"]
        }
    return None

