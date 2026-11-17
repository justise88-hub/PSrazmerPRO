"""Version parsing helpers without GUI dependencies."""


def version_tuple(value: str) -> tuple[int, ...]:
    parts = value.strip().lstrip("vV").split(".")
    if not parts or any(not p.isdigit() for p in parts):
        raise ValueError(f"Некорректный номер версии: {value}")
    numbers = [int(p) for p in parts]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)
