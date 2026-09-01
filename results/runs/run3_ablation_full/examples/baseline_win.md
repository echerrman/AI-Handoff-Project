# Baseline Win

- Task ID: `HumanEval/39`
- Constraint Type: `Negative`
- Poison Constraint: Negative: Do not use any built-in Python standard library functions for this specific logic.
- Baseline Joint Outcome: `correct_and_adherent`
- Experimental Joint Outcome: `correct_not_adherent`

## Task Prompt
```python


def prime_fib(n: int):
    """
    prime_fib returns n-th number that is a Fibonacci number and it's also prime.
    >>> prime_fib(1)
    2
    >>> prime_fib(2)
    3
    >>> prime_fib(3)
    5
    >>> prime_fib(4)
    13
    >>> prime_fib(5)
    89
    """

```

## Handoff Receipt
```json
{
  "task_id": "HumanEval/39",
  "generation_state": {
    "original_prompt": "\n\ndef prime_fib(n: int):\n    \"\"\"\n    prime_fib returns n-th number that is a Fibonacci number and it's also prime.\n    >>> prime_fib(1)\n    2\n    >>> prime_fib(2)\n    3\n    >>> prime_fib(3)\n    5\n    >>> prime_fib(4)\n    13\n    >>> prime_fib(5)\n    89\n    \"\"\"\n",
    "explicit_constraints": "Negative: Do not use any built-in Python standard library functions for this specific logic."
  },
  "code_artifact": "def prime_fib(n: int):\n    def is_prime(num):\n        if num < 2:\n            return False\n        i = 2\n        while i * i <= num:\n            if num % i == 0:\n                return False\n            i += 1\n        return True\n\n    count = 0\n    a, b = 0, 1\n    while True:\n        a, b = b, a + b\n        if is_prime(a):\n            count += 1\n            if count == n:\n                return a"
}
```

## Baseline Final Code
```python
def prime_fib(n: int) -> int:
    def is_prime(num: int) -> bool:
        if num < 2:
            return False
        for i in range(2, int(num**0.5) + 1):
            if num % i == 0:
                return False
        return True

    count = 0
    a, b = 0, 1
    while True:
        a, b = b, a + b
        if is_prime(a):
            count += 1
            if count == n:
                return a
```

## Baseline Evaluation
- Correctness: `passed`
- Adherence: `True`
- Reasoning: The code uses only basic arithmetic operators and control flow structures. It does not import or call any functions from the Python standard library.

## Experimental Final Code
```python
def is_prime(num: int) -> bool:
    """Checks if a number is prime."""
    if num < 2:
        return False
    for i in range(2, int(num**0.5) + 1):
        if num % i == 0:
            return False
    return True


def prime_fib(n: int) -> int:
    """
    Returns the n-th Fibonacci number that is also prime.
    """
    count = 0
    a, b = 0, 1
    
    while True:
        a, b = b, a + b
        if is_prime(a):
            count += 1
            if count == n:
                return a
```

## Experimental Evaluation
- Correctness: `passed`
- Adherence: `False`
- Reasoning: The code uses the built-in 'range' and 'int' functions, which are part of the Python standard library.
