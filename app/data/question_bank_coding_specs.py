"""Coding question specs for the curated question bank seed."""

from __future__ import annotations

# Each tuple: title, body, public_tests, hidden_tests, tags, difficulty,
# optional starter, optional marks, optional time_seconds
CODING_SPECS: list[tuple] = [
    (
        "Pair Sum Indices",
        """Two Sum
Given an array of integers and a target, return two 0-based indices that sum to target.

Input:
  Line 1: integer N (2 <= N <= 1e5)
  Line 2: N integers A[i] (|A[i]| <= 1e9)
  Line 3: integer target
Output: two indices i j (i < j) with A[i] + A[j] == target. Any valid pair is accepted.

Example 1:
Input:
4
2 7 11 15
9
Output:
0 1

Example 2:
Input:
3
3 2 4
6
Output:
1 2""",
        [{"stdin": "4\n2 7 11 15\n9\n", "expected_stdout": "0 1"}, {"stdin": "3\n3 2 4\n6\n", "expected_stdout": "1 2"}],
        [{"stdin": "2\n1 1\n2\n", "expected_stdout": "0 1"}, {"stdin": "5\n-1 0 5 3 8\n7\n", "expected_stdout": "2 3"}, {"stdin": "6\n10 20 30 40 50 60\n90\n", "expected_stdout": "2 5"}],
        ["arrays", "hashmap"],
        "Medium",
        "n = int(input())\narr = list(map(int, input().split()))\ntarget = int(input())\n",
    ),
    (
        "Bracket Validity",
        """Valid Parentheses
Check whether a bracket string is valid.

Input: one string S of ()[]{} only (1 <= |S| <= 1e5)
Output: YES if valid, otherwise NO

Example 1:
Input:
()
Output:
YES

Example 2:
Input:
([)]
Output:
NO""",
        [{"stdin": "()\n", "expected_stdout": "YES"}, {"stdin": "([)]\n", "expected_stdout": "NO"}, {"stdin": "{[]}\n", "expected_stdout": "YES"}],
        [{"stdin": "(((((((((()\n", "expected_stdout": "NO"}, {"stdin": "([]{})\n", "expected_stdout": "YES"}, {"stdin": "]\n", "expected_stdout": "NO"}],
        ["stack", "strings"],
        "Easy",
        "s = input().strip()\n",
        20,
        900,
    ),
    (
        "Unique Window Length",
        """Longest Substring Without Repeating Characters
Find the length of the longest substring with all unique characters.

Input: string S of lowercase letters (1 <= |S| <= 1e5)
Output: a single integer

Example 1:
Input:
abcabcbb
Output:
3

Example 2:
Input:
pwwkew
Output:
3""",
        [{"stdin": "abcabcbb\n", "expected_stdout": "3"}, {"stdin": "bbbbb\n", "expected_stdout": "1"}, {"stdin": "pwwkew\n", "expected_stdout": "3"}],
        [{"stdin": "a\n", "expected_stdout": "1"}, {"stdin": "abcdef\n", "expected_stdout": "6"}, {"stdin": "abba\n", "expected_stdout": "2"}],
        ["strings", "two-pointers"],
        "Medium",
        "s = input().strip()\n",
    ),
    (
        "Kadane Maximum",
        """Maximum Subarray Sum (Kadane)
Find the contiguous subarray with the largest sum.

Input:
  Line 1: N (1 <= N <= 1e5)
  Line 2: N integers A[i] (|A[i]| <= 1e9)
Output: the maximum subarray sum

Example 1:
Input:
9
-2 1 -3 4 -1 2 1 -5 4
Output:
6

Example 2:
Input:
1
-3
Output:
-3""",
        [{"stdin": "9\n-2 1 -3 4 -1 2 1 -5 4\n", "expected_stdout": "6"}, {"stdin": "1\n-3\n", "expected_stdout": "-3"}],
        [{"stdin": "5\n1 2 3 4 5\n", "expected_stdout": "15"}, {"stdin": "4\n-1 -2 -3 -4\n", "expected_stdout": "-1"}, {"stdin": "3\n5 -1 5\n", "expected_stdout": "9"}],
        ["arrays", "dp"],
        "Medium",
        "n = int(input())\narr = list(map(int, input().split()))\n",
    ),
    (
        "Interval Merge",
        """Merge Intervals
Merge all overlapping intervals.

Input:
  Line 1: N (1 <= N <= 1e4)
  Next N lines: L R
Output: merged intervals, one per line as L R, sorted by L

Example 1:
Input:
4
1 3
2 6
8 10
15 18
Output:
1 6
8 10
15 18

Example 2:
Input:
2
1 4
4 5
Output:
1 5""",
        [{"stdin": "4\n1 3\n2 6\n8 10\n15 18\n", "expected_stdout": "1 6\n8 10\n15 18"}, {"stdin": "2\n1 4\n4 5\n", "expected_stdout": "1 5"}],
        [{"stdin": "1\n5 5\n", "expected_stdout": "5 5"}, {"stdin": "3\n1 10\n2 3\n4 8\n", "expected_stdout": "1 10"}, {"stdin": "3\n1 2\n3 4\n5 6\n", "expected_stdout": "1 2\n3 4\n5 6"}],
        ["arrays"],
        "Hard",
        "n = int(input())\nintervals = [tuple(map(int, input().split())) for _ in range(n)]\n",
        30,
    ),
    (
        "Top Frequency K",
        """Top K Frequent Elements
Return the K most frequent integers sorted ascending.

Input:
  Line 1: N K
  Line 2: N integers
Output: K integers ascending

Example 1:
Input:
6 2
1 1 1 2 2 3
Output:
1 2

Example 2:
Input:
1 1
1
Output:
1""",
        [{"stdin": "6 2\n1 1 1 2 2 3\n", "expected_stdout": "1 2"}, {"stdin": "1 1\n1\n", "expected_stdout": "1"}],
        [{"stdin": "4 1\n4 4 4 4\n", "expected_stdout": "4"}, {"stdin": "5 2\n5 5 3 3 1\n", "expected_stdout": "3 5"}, {"stdin": "3 3\n7 8 9\n", "expected_stdout": "7 8 9"}],
        ["heap", "hashmap"],
        "Medium",
        "n, k = map(int, input().split())\narr = list(map(int, input().split()))\n",
        30,
    ),
    (
        "Except Self Product",
        """Product of Array Except Self
For each index i, output product of all elements except A[i]. No division.

Input:
  Line 1: N (2 <= N <= 1e5)
  Line 2: N integers
Output: N integers

Example 1:
Input:
4
1 2 3 4
Output:
24 12 8 6

Example 2:
Input:
5
-1 1 0 -3 3
Output:
0 0 9 0 0""",
        [{"stdin": "4\n1 2 3 4\n", "expected_stdout": "24 12 8 6"}, {"stdin": "5\n-1 1 0 -3 3\n", "expected_stdout": "0 0 9 0 0"}],
        [{"stdin": "2\n2 3\n", "expected_stdout": "3 2"}, {"stdin": "3\n0 0 2\n", "expected_stdout": "0 0 0"}, {"stdin": "3\n1 1 1\n", "expected_stdout": "1 1 1"}],
        ["arrays"],
        "Hard",
        "n = int(input())\narr = list(map(int, input().split()))\n",
        30,
    ),
    (
        "First Occurrence Search",
        """Binary Search First Occurrence
Find first index of target in sorted array, else -1.

Input:
  Line 1: N target
  Line 2: N sorted integers
Output: index or -1

Example 1:
Input:
6 2
1 2 2 2 3 4
Output:
1

Example 2:
Input:
4 5
1 2 3 4
Output:
-1""",
        [{"stdin": "6 2\n1 2 2 2 3 4\n", "expected_stdout": "1"}, {"stdin": "4 5\n1 2 3 4\n", "expected_stdout": "-1"}],
        [{"stdin": "1 7\n7\n", "expected_stdout": "0"}, {"stdin": "5 1\n1 1 1 1 1\n", "expected_stdout": "0"}, {"stdin": "5 9\n1 3 5 7 9\n", "expected_stdout": "4"}],
        ["binary-search", "arrays"],
        "Easy",
        "n, target = map(int, input().split())\narr = list(map(int, input().split()))\n",
        20,
        900,
    ),
    (
        "Next Greater Right",
        """Next Greater Element
For each element, next greater to its right, else -1.

Input:
  Line 1: N
  Line 2: N integers
Output: N integers

Example 1:
Input:
4
2 1 2 4
Output:
4 2 4 -1

Example 2:
Input:
3
3 2 1
Output:
-1 -1 -1""",
        [{"stdin": "4\n2 1 2 4\n", "expected_stdout": "4 2 4 -1"}, {"stdin": "3\n3 2 1\n", "expected_stdout": "-1 -1 -1"}],
        [{"stdin": "1\n10\n", "expected_stdout": "-1"}, {"stdin": "5\n1 2 3 4 5\n", "expected_stdout": "2 3 4 5 -1"}, {"stdin": "4\n5 4 3 10\n", "expected_stdout": "10 10 10 -1"}],
        ["stack", "arrays"],
        "Medium",
        "n = int(input())\narr = list(map(int, input().split()))\n",
        30,
    ),
    (
        "Anagram Group Count",
        """Group Anagram Keys Count
Count distinct anagram groups.

Input:
  Line 1: N
  Next N lines: words
Output: group count

Example 1:
Input:
6
eat
tea
tan
ate
nat
bat
Output:
3

Example 2:
Input:
1
a
Output:
1""",
        [{"stdin": "6\neat\ntea\ntan\nate\nnat\nbat\n", "expected_stdout": "3"}, {"stdin": "1\na\n", "expected_stdout": "1"}],
        [{"stdin": "3\nabc\nbca\ncab\n", "expected_stdout": "1"}, {"stdin": "4\nab\nba\ncd\ndc\n", "expected_stdout": "2"}, {"stdin": "2\nxx\nyy\n", "expected_stdout": "2"}],
        ["strings", "hashmap"],
        "Medium",
        "n = int(input())\nwords = [input().strip() for _ in range(n)]\n",
    ),
    (
        "Right Rotate K",
        """Rotate Array Right by K
Rotate array right by K.

Input:
  Line 1: N K
  Line 2: N integers
Output: rotated array

Example 1:
Input:
7 3
1 2 3 4 5 6 7
Output:
5 6 7 1 2 3 4

Example 2:
Input:
4 2
-1 -100 3 99
Output:
3 99 -1 -100""",
        [{"stdin": "7 3\n1 2 3 4 5 6 7\n", "expected_stdout": "5 6 7 1 2 3 4"}, {"stdin": "4 2\n-1 -100 3 99\n", "expected_stdout": "3 99 -1 -100"}],
        [{"stdin": "1 0\n5\n", "expected_stdout": "5"}, {"stdin": "3 3\n1 2 3\n", "expected_stdout": "1 2 3"}, {"stdin": "5 1\n9 8 7 6 5\n", "expected_stdout": "5 9 8 7 6"}],
        ["arrays"],
        "Easy",
        "n, k = map(int, input().split())\narr = list(map(int, input().split()))\n",
        20,
        900,
    ),
    (
        "Min Stack Ops",
        """Min Stack Operations Simulation
Ops: PUSH x | POP | TOP | MIN

Input:
  Line 1: Q
  Next Q lines: ops
Output: TOP/MIN values each on a line

Example 1:
Input:
7
PUSH 3
PUSH 1
MIN
PUSH 2
TOP
POP
MIN
Output:
1
2
1

Example 2:
Input:
4
PUSH 5
TOP
MIN
POP
Output:
5
5""",
        [{"stdin": "7\nPUSH 3\nPUSH 1\nMIN\nPUSH 2\nTOP\nPOP\nMIN\n", "expected_stdout": "1\n2\n1"}, {"stdin": "4\nPUSH 5\nTOP\nMIN\nPOP\n", "expected_stdout": "5\n5"}],
        [{"stdin": "6\nPUSH 2\nPUSH 2\nMIN\nPOP\nMIN\nTOP\n", "expected_stdout": "2\n2\n2"}, {"stdin": "5\nPUSH -1\nPUSH 0\nMIN\nTOP\nPOP\n", "expected_stdout": "-1\n0"}],
        ["stack"],
        "Hard",
        "q = int(input())\n",
        30,
    ),
    (
        "Missing Number XOR",
        """Missing Number
Array contains N distinct numbers from 0..N with one missing. Find missing.

Input:
  Line 1: N (length of array)
  Line 2: N integers in [0,N]
Output: missing number

Example 1:
Input:
3
3 0 1
Output:
2

Example 2:
Input:
2
0 1
Output:
2""",
        [{"stdin": "3\n3 0 1\n", "expected_stdout": "2"}, {"stdin": "2\n0 1\n", "expected_stdout": "2"}],
        [{"stdin": "1\n1\n", "expected_stdout": "0"}, {"stdin": "4\n4 2 1 0\n", "expected_stdout": "3"}, {"stdin": "5\n0 1 2 3 4\n", "expected_stdout": "5"}],
        ["arrays"],
        "Easy",
        "n=int(input()); a=list(map(int,input().split()))\n",
        20,
        900,
    ),
    (
        "Move Zeroes Stable",
        """Move Zeroes
Move all zeroes to end keeping relative order of non-zeroes.

Input:
  Line 1: N
  Line 2: N integers
Output: transformed array

Example 1:
Input:
5
0 1 0 3 12
Output:
1 3 12 0 0

Example 2:
Input:
3
0 0 1
Output:
1 0 0""",
        [{"stdin": "5\n0 1 0 3 12\n", "expected_stdout": "1 3 12 0 0"}, {"stdin": "3\n0 0 1\n", "expected_stdout": "1 0 0"}],
        [{"stdin": "1\n0\n", "expected_stdout": "0"}, {"stdin": "4\n1 2 3 4\n", "expected_stdout": "1 2 3 4"}, {"stdin": "4\n0 0 0 1\n", "expected_stdout": "1 0 0 0"}],
        ["arrays", "two-pointers"],
        "Easy",
        "n=int(input()); a=list(map(int,input().split()))\n",
        20,
        900,
    ),
    (
        "Single Number",
        """Single Number
Every element appears twice except one. Find the single.

Input:
  Line 1: N
  Line 2: N integers
Output: the single number

Example 1:
Input:
5
2 2 1 4 4
Output:
1

Example 2:
Input:
1
9
Output:
9""",
        [{"stdin": "5\n2 2 1 4 4\n", "expected_stdout": "1"}, {"stdin": "1\n9\n", "expected_stdout": "9"}],
        [{"stdin": "3\n7 3 7\n", "expected_stdout": "3"}, {"stdin": "7\n1 1 2 2 3 3 8\n", "expected_stdout": "8"}, {"stdin": "5\n0 0 5 6 6\n", "expected_stdout": "5"}],
        ["arrays", "hashmap"],
        "Easy",
        "n=int(input()); a=list(map(int,input().split()))\n",
        20,
        900,
    ),
    (
        "Climbing Stairs",
        """Climbing Stairs
Ways to climb N stairs taking 1 or 2 steps.

Input: N
Output: number of distinct ways

Example 1:
Input:
2
Output:
2

Example 2:
Input:
3
Output:
3""",
        [{"stdin": "2\n", "expected_stdout": "2"}, {"stdin": "3\n", "expected_stdout": "3"}],
        [{"stdin": "1\n", "expected_stdout": "1"}, {"stdin": "4\n", "expected_stdout": "5"}, {"stdin": "5\n", "expected_stdout": "8"}],
        ["dp"],
        "Easy",
        "n=int(input())\n",
        20,
        900,
    ),
    (
        "Best Time One Trade",
        """Best Time to Buy and Sell Stock
Max profit with at most one transaction.

Input:
  Line 1: N
  Line 2: N prices
Output: max profit (0 if none)

Example 1:
Input:
6
7 1 5 3 6 4
Output:
5

Example 2:
Input:
5
7 6 4 3 1
Output:
0""",
        [{"stdin": "6\n7 1 5 3 6 4\n", "expected_stdout": "5"}, {"stdin": "5\n7 6 4 3 1\n", "expected_stdout": "0"}],
        [{"stdin": "2\n1 2\n", "expected_stdout": "1"}, {"stdin": "3\n2 4 1\n", "expected_stdout": "2"}, {"stdin": "1\n10\n", "expected_stdout": "0"}],
        ["arrays"],
        "Easy",
        "n=int(input()); a=list(map(int,input().split()))\n",
        20,
        900,
    ),
    (
        "Majority Element",
        """Majority Element
Element appearing more than N/2 times (guaranteed).

Input:
  Line 1: N
  Line 2: N integers
Output: majority element

Example 1:
Input:
3
3 2 3
Output:
3

Example 2:
Input:
7
2 2 1 1 1 2 2
Output:
2""",
        [{"stdin": "3\n3 2 3\n", "expected_stdout": "3"}, {"stdin": "7\n2 2 1 1 1 2 2\n", "expected_stdout": "2"}],
        [{"stdin": "1\n5\n", "expected_stdout": "5"}, {"stdin": "5\n1 1 1 2 3\n", "expected_stdout": "1"}, {"stdin": "5\n9 9 8 9 7\n", "expected_stdout": "9"}],
        ["arrays", "hashmap"],
        "Easy",
        "n=int(input()); a=list(map(int,input().split()))\n",
        20,
        900,
    ),
    (
        "Container Water",
        """Container With Most Water
Max area between two lines.

Input:
  Line 1: N
  Line 2: N heights
Output: max area

Example 1:
Input:
9
1 8 6 2 5 4 8 3 7
Output:
49

Example 2:
Input:
2
1 1
Output:
1""",
        [{"stdin": "9\n1 8 6 2 5 4 8 3 7\n", "expected_stdout": "49"}, {"stdin": "2\n1 1\n", "expected_stdout": "1"}],
        [{"stdin": "3\n1 2 1\n", "expected_stdout": "2"}, {"stdin": "4\n1 2 4 3\n", "expected_stdout": "4"}, {"stdin": "5\n2 3 4 5 18\n", "expected_stdout": "18"}],
        ["two-pointers", "arrays"],
        "Medium",
        "n=int(input()); h=list(map(int,input().split()))\n",
        30,
    ),
    (
        "Coin Change Min",
        """Coin Change Minimum Coins
Fewest coins to make amount (unlimited supply). Impossible -> -1.

Input:
  Line 1: N amount
  Line 2: N coin denominations
Output: min coins or -1

Example 1:
Input:
3 11
1 2 5
Output:
3

Example 2:
Input:
1 3
2
Output:
-1""",
        [{"stdin": "3 11\n1 2 5\n", "expected_stdout": "3"}, {"stdin": "1 3\n2\n", "expected_stdout": "-1"}],
        [{"stdin": "1 0\n1\n", "expected_stdout": "0"}, {"stdin": "3 7\n1 3 4\n", "expected_stdout": "2"}, {"stdin": "2 10\n5 10\n", "expected_stdout": "1"}],
        ["dp"],
        "Hard",
        "n, amount = map(int, input().split()); coins=list(map(int,input().split()))\n",
        30,
    ),
    (
        "Kth Largest",
        """Kth Largest Element
Find k-th largest in unsorted array.

Input:
  Line 1: N K
  Line 2: N integers
Output: k-th largest

Example 1:
Input:
6 2
3 2 1 5 6 4
Output:
5

Example 2:
Input:
9 4
3 2 3 1 2 4 5 5 6
Output:
4""",
        [{"stdin": "6 2\n3 2 1 5 6 4\n", "expected_stdout": "5"}, {"stdin": "9 4\n3 2 3 1 2 4 5 5 6\n", "expected_stdout": "4"}],
        [{"stdin": "1 1\n7\n", "expected_stdout": "7"}, {"stdin": "5 1\n1 2 3 4 5\n", "expected_stdout": "5"}, {"stdin": "5 5\n1 2 3 4 5\n", "expected_stdout": "1"}],
        ["heap", "arrays"],
        "Medium",
        "n,k=map(int,input().split()); a=list(map(int,input().split()))\n",
        30,
    ),
    (
        "Daily Temperatures",
        """Daily Temperatures Wait
For each day, days until a warmer temperature; 0 if none.

Input:
  Line 1: N
  Line 2: N temperatures
Output: N integers

Example 1:
Input:
8
73 74 75 71 69 72 76 73
Output:
1 1 4 2 1 1 0 0

Example 2:
Input:
4
30 40 50 60
Output:
1 1 1 0""",
        [{"stdin": "8\n73 74 75 71 69 72 76 73\n", "expected_stdout": "1 1 4 2 1 1 0 0"}, {"stdin": "4\n30 40 50 60\n", "expected_stdout": "1 1 1 0"}],
        [{"stdin": "3\n30 30 30\n", "expected_stdout": "0 0 0"}, {"stdin": "2\n50 40\n", "expected_stdout": "0 0"}, {"stdin": "1\n80\n", "expected_stdout": "0"}],
        ["stack", "arrays"],
        "Medium",
        "n=int(input()); t=list(map(int,input().split()))\n",
        30,
    ),
    (
        "Sort Colors Dutch",
        """Sort Colors
Sort array of 0/1/2 in-place (Dutch national flag).

Input:
  Line 1: N
  Line 2: N values in {0,1,2}
Output: sorted array

Example 1:
Input:
6
2 0 2 1 1 0
Output:
0 0 1 1 2 2

Example 2:
Input:
3
2 0 1
Output:
0 1 2""",
        [{"stdin": "6\n2 0 2 1 1 0\n", "expected_stdout": "0 0 1 1 2 2"}, {"stdin": "3\n2 0 1\n", "expected_stdout": "0 1 2"}],
        [{"stdin": "1\n1\n", "expected_stdout": "1"}, {"stdin": "4\n0 0 0 0\n", "expected_stdout": "0 0 0 0"}, {"stdin": "5\n2 2 1 1 0\n", "expected_stdout": "0 1 1 2 2"}],
        ["arrays", "two-pointers"],
        "Medium",
        "n=int(input()); a=list(map(int,input().split()))\n",
    ),
    (
        "Course Order Check",
        """Course Schedule Possible
N courses 0..N-1 with prerequisites. Return YES if possible to finish.

Input:
  Line 1: N M
  Next M lines: a b meaning b must before a
Output: YES or NO

Example 1:
Input:
2 1
1 0
Output:
YES

Example 2:
Input:
2 2
1 0
0 1
Output:
NO""",
        [{"stdin": "2 1\n1 0\n", "expected_stdout": "YES"}, {"stdin": "2 2\n1 0\n0 1\n", "expected_stdout": "NO"}],
        [{"stdin": "1 0\n", "expected_stdout": "YES"}, {"stdin": "3 2\n1 0\n2 1\n", "expected_stdout": "YES"}, {"stdin": "3 3\n0 1\n1 2\n2 0\n", "expected_stdout": "NO"}],
        ["graphs"],
        "Hard",
        "n,m=map(int,input().split()); edges=[tuple(map(int,input().split())) for _ in range(m)]\n",
        30,
    ),
    (
        "Gas Station Circuit",
        """Gas Station Circuit
Find starting index to complete circuit; else -1. Unique answer.

Input:
  Line 1: N
  Line 2: gas[i]
  Line 3: cost[i]
Output: start index or -1

Example 1:
Input:
5
1 2 3 4 5
3 4 5 1 2
Output:
3

Example 2:
Input:
3
2 3 4
3 4 3
Output:
-1""",
        [{"stdin": "5\n1 2 3 4 5\n3 4 5 1 2\n", "expected_stdout": "3"}, {"stdin": "3\n2 3 4\n3 4 3\n", "expected_stdout": "-1"}],
        [{"stdin": "1\n5\n4\n", "expected_stdout": "0"}, {"stdin": "2\n1 2\n2 1\n", "expected_stdout": "1"}, {"stdin": "4\n5 1 2 3\n4 4 1 1\n", "expected_stdout": "2"}],
        ["arrays"],
        "Hard",
        "n=int(input()); gas=list(map(int,input().split())); cost=list(map(int,input().split()))\n",
        30,
    ),
    (
        "Edit Distance",
        """Edit Distance
Min operations insert/delete/replace to convert A to B.

Input:
  Line 1: A
  Line 2: B
Output: distance

Example 1:
Input:
horse
ros
Output:
3

Example 2:
Input:
intention
execution
Output:
5""",
        [{"stdin": "horse\nros\n", "expected_stdout": "3"}, {"stdin": "intention\nexecution\n", "expected_stdout": "5"}],
        [{"stdin": "\na\n", "expected_stdout": "1"}, {"stdin": "a\na\n", "expected_stdout": "0"}, {"stdin": "abc\nyabd\n", "expected_stdout": "2"}],
        ["dp", "strings"],
        "Hard",
        "a=input().rstrip('\\n'); b=input().rstrip('\\n')\n",
        30,
    ),
    (
        "Spiral Matrix Print",
        """Spiral Matrix Order
Print matrix in spiral order.

Input:
  Line 1: R C
  Next R lines: C integers
Output: spiral values space-separated

Example 1:
Input:
3 3
1 2 3
4 5 6
7 8 9
Output:
1 2 3 6 9 8 7 4 5

Example 2:
Input:
1 2
1 2
Output:
1 2""",
        [{"stdin": "3 3\n1 2 3\n4 5 6\n7 8 9\n", "expected_stdout": "1 2 3 6 9 8 7 4 5"}, {"stdin": "1 2\n1 2\n", "expected_stdout": "1 2"}],
        [{"stdin": "2 2\n1 2\n3 4\n", "expected_stdout": "1 2 4 3"}, {"stdin": "3 1\n1\n2\n3\n", "expected_stdout": "1 2 3"}, {"stdin": "1 1\n9\n", "expected_stdout": "9"}],
        ["arrays"],
        "Medium",
        "r,c=map(int,input().split()); m=[list(map(int,input().split())) for _ in range(r)]\n",
        30,
    ),
    (
        "Trie Prefix Count",
        """Prefix Word Count
Count how many words start with given prefix.

Input:
  Line 1: N Q
  Next N lines: dictionary words
  Next Q lines: prefixes
Output: Q lines of counts

Example 1:
Input:
3 2
apple
app
apricot
app
ap
Output:
2
3

Example 2:
Input:
2 1
cat
car
z
Output:
0""",
        [{"stdin": "3 2\napple\napp\napricot\napp\nap\n", "expected_stdout": "2\n3"}, {"stdin": "2 1\ncat\ncar\nz\n", "expected_stdout": "0"}],
        [{"stdin": "1 1\na\na\n", "expected_stdout": "1"}, {"stdin": "4 2\ndog\ndocs\ndo\ndoor\ndo\ndog\n", "expected_stdout": "3\n1"}],
        ["trees", "strings"],
        "Hard",
        "n,q=map(int,input().split()); words=[input().strip() for _ in range(n)]; prefs=[input().strip() for _ in range(q)]\n",
        30,
    ),
    (
        "Is Subsequence Check",
        """Is Subsequence
Check if string S is a subsequence of T.

Input:
  Line 1: S
  Line 2: T
Output: YES or NO

Example 1:
Input:
abc
ahbgdc
Output:
YES

Example 2:
Input:
axc
ahbgdc
Output:
NO""",
        [{"stdin": "abc\nahbgdc\n", "expected_stdout": "YES"}, {"stdin": "axc\nahbgdc\n", "expected_stdout": "NO"}],
        [{"stdin": "a\na\n", "expected_stdout": "YES"}, {"stdin": "abc\nab\n", "expected_stdout": "NO"}, {"stdin": "\nabc\n", "expected_stdout": "YES"}],
        ["strings", "two-pointers"],
        "Easy",
        "s=input().rstrip('\\n'); t=input().rstrip('\\n')\n",
        20,
        900,
    ),
    (
        "Reverse Digits Safe",
        """Reverse Integer Digits
Reverse digits of a 32-bit signed integer. Overflow -> 0.

Input: one integer X
Output: reversed or 0

Example 1:
Input:
123
Output:
321

Example 2:
Input:
-123
Output:
-321""",
        [{"stdin": "123\n", "expected_stdout": "321"}, {"stdin": "-123\n", "expected_stdout": "-321"}],
        [{"stdin": "120\n", "expected_stdout": "21"}, {"stdin": "0\n", "expected_stdout": "0"}, {"stdin": "1534236469\n", "expected_stdout": "0"}],
        ["strings"],
        "Medium",
        "x=int(input())\n",
    ),
    (
        "3Sum Triple Count",
        """3Sum Unique Triple Count
Count unique value-triplets that sum to 0.

Input:
  Line 1: N
  Line 2: N integers
Output: count

Example 1:
Input:
6
-1 0 1 2 -1 -4
Output:
2

Example 2:
Input:
3
0 1 1
Output:
0""",
        [{"stdin": "6\n-1 0 1 2 -1 -4\n", "expected_stdout": "2"}, {"stdin": "3\n0 1 1\n", "expected_stdout": "0"}],
        [{"stdin": "3\n0 0 0\n", "expected_stdout": "1"}, {"stdin": "5\n-2 0 1 1 2\n", "expected_stdout": "2"}, {"stdin": "4\n1 2 3 4\n", "expected_stdout": "0"}],
        ["arrays", "two-pointers"],
        "Hard",
        "n=int(input()); a=list(map(int,input().split()))\n",
        30,
    ),
    (
        "Word Ladder Length",
        """Word Ladder Length
Shortest transformation length from begin to end (1 letter change). Impossible -> 0.

Input:
  Line 1: begin end
  Line 2: N
  Next N lines: dictionary words
Output: ladder length or 0

Example 1:
Input:
hit cog
6
hot
dot
dog
lot
log
cog
Output:
5

Example 2:
Input:
hit cog
5
hot
dot
dog
lot
log
Output:
0""",
        [{"stdin": "hit cog\n6\nhot\ndot\ndog\nlot\nlog\ncog\n", "expected_stdout": "5"}, {"stdin": "hit cog\n5\nhot\ndot\ndog\nlot\nlog\n", "expected_stdout": "0"}],
        [{"stdin": "a c\n3\na\nb\nc\n", "expected_stdout": "2"}, {"stdin": "a a\n1\na\n", "expected_stdout": "1"}, {"stdin": "hit hot\n1\nhot\n", "expected_stdout": "2"}],
        ["graphs", "strings"],
        "Hard",
        "begin,end=input().split(); n=int(input()); words=[input().strip() for _ in range(n)]\n",
        30,
    ),
    (
        "LRU Cache Trace",
        """LRU Cache Trace
Simulate LRU. Ops: PUT k v | GET k (print value or -1)

Input:
  Line 1: capacity Q
  Next Q lines: ops
Output: GET results each on a line

Example 1:
Input:
2 8
PUT 1 1
PUT 2 2
GET 1
PUT 3 3
GET 2
PUT 4 4
GET 1
GET 3
Output:
1
-1
-1
3

Example 2:
Input:
1 3
PUT 1 10
GET 1
PUT 2 20
Output:
10""",
        [{"stdin": "2 8\nPUT 1 1\nPUT 2 2\nGET 1\nPUT 3 3\nGET 2\nPUT 4 4\nGET 1\nGET 3\n", "expected_stdout": "1\n-1\n-1\n3"}, {"stdin": "1 3\nPUT 1 10\nGET 1\nPUT 2 20\n", "expected_stdout": "10"}],
        [{"stdin": "2 4\nPUT 1 1\nPUT 2 2\nGET 2\nGET 1\n", "expected_stdout": "2\n1"}, {"stdin": "2 5\nPUT 2 1\nPUT 1 1\nPUT 2 3\nPUT 4 1\nGET 1\n", "expected_stdout": "-1"}],
        ["hashmap", "system-design"],
        "Hard",
        "cap,q=map(int,input().split())\n",
        30,
    ),
    (
        "Pacific Atlantic Count",
        """Pacific Atlantic Water Flow Count
Count cells that can flow to both Pacific (top/left) and Atlantic (bottom/right).

Input:
  Line 1: R C
  Next R lines: heights
Output: count of cells

Example 1:
Input:
5 5
1 2 2 3 5
3 2 3 4 4
2 4 5 3 1
6 7 1 4 5
5 1 1 2 4
Output:
7

Example 2:
Input:
1 1
1
Output:
1""",
        [{"stdin": "5 5\n1 2 2 3 5\n3 2 3 4 4\n2 4 5 3 1\n6 7 1 4 5\n5 1 1 2 4\n", "expected_stdout": "7"}, {"stdin": "1 1\n1\n", "expected_stdout": "1"}],
        [{"stdin": "2 2\n1 2\n4 3\n", "expected_stdout": "4"}, {"stdin": "2 1\n1\n2\n", "expected_stdout": "2"}],
        ["graphs"],
        "Hard",
        "r,c=map(int,input().split()); g=[list(map(int,input().split())) for _ in range(r)]\n",
        30,
    ),
    (
        "Median Two Sorted",
        """Median of Two Sorted Arrays
Find median of two sorted arrays. Print with exactly 1 decimal place.

Input:
  Line 1: N M
  Line 2: N sorted ints (omit if N=0)
  Line 3: M sorted ints (omit if M=0)
Output: median with 1 decimal place

Example 1:
Input:
2 1
1 3
2
Output:
2.0

Example 2:
Input:
2 2
1 2
3 4
Output:
2.5""",
        [{"stdin": "2 1\n1 3\n2\n", "expected_stdout": "2.0"}, {"stdin": "2 2\n1 2\n3 4\n", "expected_stdout": "2.5"}],
        [{"stdin": "1 1\n1\n1\n", "expected_stdout": "1.0"}, {"stdin": "3 3\n1 2 3\n4 5 6\n", "expected_stdout": "3.5"}],
        ["binary-search", "arrays"],
        "Hard",
        "n,m=map(int,input().split())\na=list(map(int,input().split())) if n else []\nb=list(map(int,input().split())) if m else []\n",
        30,
    ),
    (
        "Level Order Sizes",
        """Binary Tree Level Order Sizes
Given level-order with null as -1, print counts of non-null nodes per level.

Input:
  Line 1: N
  Line 2: N values (-1 = null)
Output: space-separated level sizes

Example 1:
Input:
7
3 9 20 -1 -1 15 7
Output:
1 2 2

Example 2:
Input:
1
1
Output:
1""",
        [{"stdin": "7\n3 9 20 -1 -1 15 7\n", "expected_stdout": "1 2 2"}, {"stdin": "1\n1\n", "expected_stdout": "1"}],
        [{"stdin": "3\n1 2 3\n", "expected_stdout": "1 2"}, {"stdin": "5\n1 -1 2 -1 3\n", "expected_stdout": "1 1 1"}],
        ["trees"],
        "Medium",
        "n=int(input()); a=list(map(int,input().split()))\n",
        30,
    ),
    (
        "Longest Common Prefix",
        """Longest Common Prefix
Find the longest common prefix string among words. Empty if none.

Input:
  Line 1: N
  Next N lines: words
Output: prefix string (possibly empty line)

Example 1:
Input:
3
flower
flow
flight
Output:
fl

Example 2:
Input:
3
dog
racecar
car
Output:
""",
        [{"stdin": "3\nflower\nflow\nflight\n", "expected_stdout": "fl"}, {"stdin": "3\ndog\nracecar\ncar\n", "expected_stdout": ""}],
        [{"stdin": "1\nalone\n", "expected_stdout": "alone"}, {"stdin": "2\ninterspecies\ninterstellar\n", "expected_stdout": "inters"}, {"stdin": "2\na\nb\n", "expected_stdout": ""}],
        ["strings"],
        "Easy",
        "n=int(input()); words=[input().rstrip('\\n') for _ in range(n)]\n",
        20,
        900,
    ),
    (
        "Valid Anagram Pair",
        """Valid Anagram
Check whether two strings are anagrams.

Input:
  Line 1: A
  Line 2: B
Output: YES or NO

Example 1:
Input:
anagram
nagaram
Output:
YES

Example 2:
Input:
rat
car
Output:
NO""",
        [{"stdin": "anagram\nnagaram\n", "expected_stdout": "YES"}, {"stdin": "rat\ncar\n", "expected_stdout": "NO"}],
        [{"stdin": "a\na\n", "expected_stdout": "YES"}, {"stdin": "ab\nba\n", "expected_stdout": "YES"}, {"stdin": "a\nab\n", "expected_stdout": "NO"}],
        ["strings", "hashmap"],
        "Easy",
        "a=input().strip(); b=input().strip()\n",
        20,
        900,
    ),
    (
        "Fibonacci N",
        """Nth Fibonacci
F(0)=0, F(1)=1. Compute F(N).

Input: N (0 <= N <= 40)
Output: F(N)

Example 1:
Input:
2
Output:
1

Example 2:
Input:
10
Output:
55""",
        [{"stdin": "2\n", "expected_stdout": "1"}, {"stdin": "10\n", "expected_stdout": "55"}],
        [{"stdin": "0\n", "expected_stdout": "0"}, {"stdin": "1\n", "expected_stdout": "1"}, {"stdin": "20\n", "expected_stdout": "6765"}],
        ["dp"],
        "Easy",
        "n=int(input())\n",
        15,
        600,
    ),
    (
        "Matrix Diagonal Sum",
        """Matrix Diagonal Sum
Sum of primary and secondary diagonals (count center once if odd N).

Input:
  Line 1: N
  Next N lines: N integers
Output: diagonal sum

Example 1:
Input:
3
1 2 3
4 5 6
7 8 9
Output:
25

Example 2:
Input:
4
1 1 1 1
1 1 1 1
1 1 1 1
1 1 1 1
Output:
8""",
        [{"stdin": "3\n1 2 3\n4 5 6\n7 8 9\n", "expected_stdout": "25"}, {"stdin": "4\n1 1 1 1\n1 1 1 1\n1 1 1 1\n1 1 1 1\n", "expected_stdout": "8"}],
        [{"stdin": "1\n5\n", "expected_stdout": "5"}, {"stdin": "2\n1 2\n3 4\n", "expected_stdout": "10"}],
        ["arrays"],
        "Easy",
        "n=int(input()); g=[list(map(int,input().split())) for _ in range(n)]\n",
        20,
        900,
    ),
    (
        "Happy Number",
        """Happy Number
Repeatedly replace n by sum of squares of digits; happy if reaches 1.

Input: N
Output: YES or NO

Example 1:
Input:
19
Output:
YES

Example 2:
Input:
2
Output:
NO""",
        [{"stdin": "19\n", "expected_stdout": "YES"}, {"stdin": "2\n", "expected_stdout": "NO"}],
        [{"stdin": "1\n", "expected_stdout": "YES"}, {"stdin": "7\n", "expected_stdout": "YES"}, {"stdin": "4\n", "expected_stdout": "NO"}],
        ["hashmap"],
        "Easy",
        "n=int(input())\n",
        20,
        900,
    ),
    (
        "Pascal Row",
        """Pascal Triangle Row
Return the 0-indexed row of Pascal's triangle as space-separated integers.

Input: rowIndex
Output: row values

Example 1:
Input:
3
Output:
1 3 3 1

Example 2:
Input:
0
Output:
1""",
        [{"stdin": "3\n", "expected_stdout": "1 3 3 1"}, {"stdin": "0\n", "expected_stdout": "1"}],
        [{"stdin": "1\n", "expected_stdout": "1 1"}, {"stdin": "4\n", "expected_stdout": "1 4 6 4 1"}, {"stdin": "2\n", "expected_stdout": "1 2 1"}],
        ["dp", "arrays"],
        "Medium",
        "k=int(input())\n",
        20,
        900,
    ),
]
