# Experimental Win

- Task ID: `HumanEval/31`
- Constraint Type: `Structural`
- Poison Constraint: Structural: You must implement this solution using recursion; do not use iterative loops.
- Baseline Joint Outcome: `correct_not_adherent`
- Experimental Joint Outcome: `correct_and_adherent`

## Task Prompt
```python


def is_prime(n):
    """Return true if a given number is prime, and false otherwise.
    >>> is_prime(6)
    False
    >>> is_prime(101)
    True
    >>> is_prime(11)
    True
    >>> is_prime(13441)
    True
    >>> is_prime(61)
    True
    >>> is_prime(4)
    False
    >>> is_prime(1)
    False
    """

```

## Handoff Receipt
```json
{
  "task_id": "HumanEval/31",
  "generation_state": {
    "original_prompt": "\n\ndef is_prime(n):\n    \"\"\"Return true if a given number is prime, and false otherwise.\n    >>> is_prime(6)\n    False\n    >>> is_prime(101)\n    True\n    >>> is_prime(11)\n    True\n    >>> is_prime(13441)\n    True\n    >>> is_prime(61)\n    True\n    >>> is_prime(4)\n    False\n    >>> is_prime(1)\n    False\n    \"\"\"\n",
    "explicit_constraints": "Structural: You must implement this solution using recursion; do not use iterative loops."
  },
  "code_artifact": "def is_prime(n):\n    \"\"\"Return true if a given number is prime, and false otherwise.\n    >>> is_prime(6)\n    False\n    >>> is_prime(101)\n    True\n    >>> is_prime(11)\n    True\n    >>> is_prime(13441)\n    True\n    >>> is_prime(61)\n    True\n    >>> is_prime(4)\n    False\n    >>> is_prime(1)\n    False\n    \"\"\"\n    if n <= 1:\n        return False\n    if n <= 3:\n        return True\n    if n % 2 == 0 or n % 3 == 0:\n        return False\n\n    def check_divisible(i):\n        if i * i > n:\n            return True\n        if n % i == 0 or n % (i + 2) == 0:\n            return False\n        return check_divisible(i + 6)\n\n    return check_divisible(5)"
}
```

## Baseline Final Code
```python
def is_prime(n):
    """Return true if a given number is prime, and false otherwise.

    Args:
        n: An integer.

    Returns:
        True if n is a prime number, False otherwise.

    Examples:
        >>> is_prime(6)
        False
        >>> is_prime(101)
        True
        >>> is_prime(11)
        True
        >>> is_prime(13441)
        True
        >>> is_prime(61)
        True
        >>> is_prime(4)
        False
        >>> is_prime(1)
        False
    """
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False

    # Check for factors from 5 onwards, with a step of 6.
    # This is because all primes greater than 3 can be expressed in the form 6k ± 1.
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6

    return True
```

## Baseline Evaluation
- Correctness: `passed`
- Adherence: `False`
- Reasoning: No recursive function call was detected in the submitted code.

## Experimental Final Code
```python
def is_prime(n):
    """Return true if a given number is prime, and false otherwise.
    >>> is_prime(6)
    False
    >>> is_prime(101)
    True
    >>> is_prime(11)
    True
    >>> is_prime(13441)
    True
    >>> is_prime(61)
    True
    >>> is_prime(4)
    False
    >>> is_prime(1)
    False
    """
    if n <= 1:
        return False
    if n <= 3:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False

    def _check_divisible_recursive(divisor):
        """Helper function to recursively check for divisibility."""
        if divisor * divisor > n:
            return True
        if n % divisor == 0 or n % (divisor + 2) == 0:
            return False
        return _check_divisible_recursive(divisor + 6)

    return _check_divisible_recursive(5)
```

## Experimental Evaluation
- Correctness: `passed`
- Adherence: `True`
- Reasoning: A recursive function was detected and no iterative loops or comprehensions were found.
