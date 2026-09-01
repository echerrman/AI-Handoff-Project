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
  "code_artifact": "def is_prime(n):\n    \"\"\"Return true if a given number is prime, and false otherwise.\n    >>> is_prime(6)\n    False\n    >>> is_prime(101)\n    True\n    >>> is_prime(11)\n    True\n    >>> is_prime(13441)\n    True\n    >>> is_prime(61)\n    True\n    >>> is_prime(4)\n    False\n    >>> is_prime(1)\n    False\n    \"\"\"\n    def check_divisor(d):\n        if d * d > n:\n            return True\n        if n % d == 0:\n            return False\n        return check_divisor(d + 1)\n\n    if n < 2:\n        return False\n    if n == 2:\n        return True\n    if n % 2 == 0:\n        return False\n    return check_divisor(3)"
}
```

## Baseline Final Code
```python
import math

def is_prime(n: int) -> bool:
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
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False

    limit = int(math.isqrt(n))
    for divisor in range(3, limit + 1, 2):
        if n % divisor == 0:
            return False
            
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
    def has_divisor(d):
        if d * d > n:
            return False
        if n % d == 0:
            return True
        return has_divisor(d + 2)

    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False

    return not has_divisor(3)
```

## Experimental Evaluation
- Correctness: `passed`
- Adherence: `True`
- Reasoning: A recursive function was detected and no iterative loops or comprehensions were found.

## Baseline Hops

### Hop 1
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
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False

    # Check odd divisors up to the square root of n
    for d in range(3, int(n**0.5) + 1, 2):
        if n % d == 0:
            return False
            
    return True
```
- Correctness: `passed`
- Adherence: `False`
- Joint Outcome: `correct_not_adherent`

### Hop 2
```python
import math

def is_prime(n: int) -> bool:
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
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False

    limit = int(math.isqrt(n))
    for divisor in range(3, limit + 1, 2):
        if n % divisor == 0:
            return False
            
    return True
```
- Correctness: `passed`
- Adherence: `False`
- Joint Outcome: `correct_not_adherent`

## Experimental Hops

### Hop 1
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
    def has_divisor(d):
        if d * d > n:
            return False
        if n % d == 0:
            return True
        return has_divisor(d + 2)

    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    
    return not has_divisor(3)
```
- Correctness: `passed`
- Adherence: `True`
- Joint Outcome: `correct_and_adherent`

### Hop 2
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
    def has_divisor(d):
        if d * d > n:
            return False
        if n % d == 0:
            return True
        return has_divisor(d + 2)

    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False

    return not has_divisor(3)
```
- Correctness: `passed`
- Adherence: `True`
- Joint Outcome: `correct_and_adherent`
