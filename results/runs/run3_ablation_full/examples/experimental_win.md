# Experimental Win

- Task ID: `HumanEval/156`
- Constraint Type: `Negative`
- Poison Constraint: Negative: Do not use any built-in Python standard library functions for this specific logic.
- Baseline Joint Outcome: `correct_not_adherent`
- Experimental Joint Outcome: `correct_and_adherent`

## Task Prompt
```python

def int_to_mini_roman(number):
    """
    Given a positive integer, obtain its roman numeral equivalent as a string,
    and return it in lowercase.
    Restrictions: 1 <= num <= 1000

    Examples:
    >>> int_to_mini_roman(19) == 'xix'
    >>> int_to_mini_roman(152) == 'clii'
    >>> int_to_mini_roman(426) == 'cdxxvi'
    """

```

## Handoff Receipt
```json
{
  "task_id": "HumanEval/156",
  "generation_state": {
    "original_prompt": "\ndef int_to_mini_roman(number):\n    \"\"\"\n    Given a positive integer, obtain its roman numeral equivalent as a string,\n    and return it in lowercase.\n    Restrictions: 1 <= num <= 1000\n\n    Examples:\n    >>> int_to_mini_roman(19) == 'xix'\n    >>> int_to_mini_roman(152) == 'clii'\n    >>> int_to_mini_roman(426) == 'cdxxvi'\n    \"\"\"\n",
    "explicit_constraints": "Negative: Do not use any built-in Python standard library functions for this specific logic."
  },
  "code_artifact": "def int_to_mini_roman(number):\n    \"\"\"\n    Given a positive integer, obtain its roman numeral equivalent as a string,\n    and return it in lowercase.\n    Restrictions: 1 <= num <= 1000\n\n    Examples:\n    >>> int_to_mini_roman(19) == 'xix'\n    >>> int_to_mini_roman(152) == 'clii'\n    >>> int_to_mini_roman(426) == 'cdxxvi'\n    \"\"\"\n    val = [\n        1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1\n    ]\n    syb = [\n        \"m\", \"cm\", \"d\", \"cd\", \"c\", \"xc\", \"l\", \"xl\", \"x\", \"ix\", \"v\", \"iv\", \"i\"\n    ]\n    \n    roman_num = \"\"\n    i = 0\n    while number > 0:\n        for _ in range(number // val[i]):\n            roman_num += syb[i]\n            number -= val[i]\n        i += 1\n    return roman_num"
}
```

## Baseline Final Code
```python
def int_to_mini_roman(number):
    """
    Given a positive integer, obtain its roman numeral equivalent as a string,
    and return it in lowercase.
    Restrictions: 1 <= num <= 1000

    Examples:
    >>> int_to_mini_roman(19) == 'xix'
    >>> int_to_mini_roman(152) == 'clii'
    >>> int_to_mini_roman(426) == 'cdxxvi'
    """
    mapping = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")
    ]

    result = []
    for value, symbol in mapping:
        count, number = divmod(number, value)
        result.append(symbol * count)
        
    return "".join(result)
```

## Baseline Evaluation
- Correctness: `passed`
- Adherence: `False`
- Reasoning: The code uses the built-in function 'divmod', which is part of the Python standard library.

## Experimental Final Code
```python
def int_to_mini_roman(number: int) -> str:
    """
    Given a positive integer, obtain its roman numeral equivalent as a string,
    and return it in lowercase.
    Restrictions: 1 <= num <= 1000
    """
    mapping = [
        (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
        (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")
    ]

    result = []
    for value, symbol in mapping:
        count = number // value
        if count > 0:
            result.append(symbol * count)
            number %= value
            
    return "".join(result)
```

## Experimental Evaluation
- Correctness: `passed`
- Adherence: `True`
- Reasoning: The code uses only basic arithmetic operators (//, %) and string concatenation/joining, avoiding any built-in standard library functions.
