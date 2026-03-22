from core.aiops_agent.inference_queue import InMemoryInferenceQueue
from core.aiops_agent.inference_schema import InferenceRequest, InferenceResult
from core.aiops_agent.providers import AIOpsProvider


class InferenceWorker:
    def __init__(self, provider: AIOpsProvider) -> None:
        self.provider = provider

    def process(self, request: InferenceRequest) -> InferenceResult:
        return self.provider.infer(request)

    def run_once(self, queue: InMemoryInferenceQueue) -> InferenceResult | None:
        request = queue.dequeue()
        if request is None:
            return None
        return self.process(request)
