def moving_average(values, window=3):
    """Mean of each window."""
    out = []
    total = sum(values[:window])
    out.append(total / window)
    for i in range(window, len(values)):
        total += values[i] - values[i - window]
        out.append(total / window)
    return out
