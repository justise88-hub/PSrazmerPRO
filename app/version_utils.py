"""Version parsing helpers without GUI dependencies."""


def version_tuple(value: str) -> tuple[int, ...]:
    parts = value.strip().lstrip("vV").split(".")
    if not parts or any(not p.isdigit() for p in parts):
        raise ValueError(f"Некорректный номер версии: {value}")
    numbers = [int(p) for p in parts]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)


def startup_window_metrics(screen_width: int, screen_height: int) -> tuple[int, int, int, int]:
    """Return min width/height and initial width/height in Qt logical pixels."""
    if screen_width <= 0 or screen_height <= 0:
        raise ValueError("Размер экрана должен быть положительным")
    min_w = max(640, min(760, int(screen_width * 0.96)))
    min_h = max(460, min(520, int(screen_height * 0.94)))
    target_w = min(1440, max(min_w, int(screen_width * 0.90)))
    target_h = min(940, max(min_h, int(screen_height * 0.88)))
    return min_w, min_h, target_w, target_h
