"""A tiny training loop: data, model, loss, optimiser."""

import random
from dataclasses import dataclass


@dataclass
class Config:
    learning_rate: float = 0.05
    epochs: int = 20
    batch_size: int = 8
    seed: int = 0


def make_data(n: int, seed: int) -> list[tuple[float, float]]:
    """Points on a noisy line y = 3x + 1."""
    rng = random.Random(seed)
    data = []
    for _ in range(n):
        x = rng.uniform(-1.0, 1.0)
        y = 3.0 * x + 1.0 + rng.gauss(0.0, 0.1)
        data.append((x, y))
    return data


def batches(data: list[tuple[float, float]], size: int):
    for start in range(0, len(data), size):
        yield data[start : start + size]


def loss_and_grads(w: float, b: float, batch: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Mean squared error of the batch and its gradients with respect to w and b."""
    loss = gw = gb = 0.0
    for x, y in batch:
        err = w * x + b - y
        loss += err * err
        gw += 2 * err * x
        gb += 2 * err
    n = len(batch)
    return loss / n, gw / n, gb / n


def train(config: Config) -> tuple[float, float]:
    data = make_data(256, config.seed)
    w, b = 0.0, 0.0
    for epoch in range(config.epochs):
        random.Random(epoch).shuffle(data)
        for batch in batches(data, config.batch_size):
            loss, gw, gb = loss_and_grads(w, b, batch)
            w -= config.learning_rate * gw
            b -= config.learning_rate * gb
        print(f"epoch {epoch:2d}  loss {loss:.4f}")
    return w, b


if __name__ == "__main__":
    print(train(Config()))
