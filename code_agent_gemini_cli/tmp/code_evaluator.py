from typing import Any

from nexevo.evaluator import EvaluationRunResult, Evaluator


# mock evaluator for code agent, always return 0.0
class CodeEvaluator(Evaluator):
    def __init__(self):
        super().__init__()

    def evaluate(self, data: Any, evaluation_target: Any) -> EvaluationRunResult:
        return EvaluationRunResult(reward=0.0, ground_truth="", metrics={}, extra_info={})
