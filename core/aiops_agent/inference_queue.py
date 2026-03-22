from collections import deque

from core.aiops_agent.inference_schema import InferenceRequest


class InMemoryInferenceQueue:
    def __init__(self) -> None:
        self._items: deque[InferenceRequest] = deque()

    def enqueue(self, request: InferenceRequest) -> None:
        self._items.append(request)

    def dequeue(self) -> InferenceRequest | None:
        if not self._items:
            return None
        return self._items.popleft()

    def size(self) -> int:
        return len(self._items)
