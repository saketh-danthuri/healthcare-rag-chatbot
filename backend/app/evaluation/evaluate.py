"""
evaluate.py - RAG Evaluation with RAGAS
==========================================
WHY: "Trust but verify." The RAG pipeline might look good in demos but
     silently degrade when you change prompts, chunking strategy, or add
     new documents. RAGAS provides automated metrics to catch regressions.

METRICS WE TRACK:
  - Faithfulness: Are answers grounded in the retrieved context? (no hallucination)
  - Answer Relevancy: Does the answer actually address the question?
  - Context Precision: Were the retrieved docs relevant to the question?
  - Context Recall: Were ALL necessary docs retrieved?

GOLDEN DATASET:
  A curated set of question-answer pairs from YOUR actual runbooks.
  These are the "known correct" answers that we evaluate against.
  Stored in golden_dataset.json and version-controlled in git.

CI/CD INTEGRATION:
  ci_eval.py (separate script) loads this module and runs the evaluation.
  If any metric drops below the threshold, the GitHub Actions build fails,
  preventing bad changes from reaching production.
"""

import json
import logging
from pathlib import Path

from app.config.settings import get_settings
from app.retrieval.retriever import format_context_for_llm, retrieve

logger = logging.getLogger(__name__)

# Quality thresholds - if any metric drops below these, CI fails
THRESHOLDS = {
    "faithfulness": 0.85,
    "answer_relevancy": 0.80,
    "context_precision": 0.75,
    "context_recall": 0.75,
}


def load_golden_dataset(path: str | None = None) -> list[dict]:
    """Load the golden evaluation dataset.

    Each entry has:
    - question: The ops team's question
    - ground_truth: The correct answer (from the actual runbook)
    - source_docs: Which runbooks contain the answer

    Returns list of evaluation samples.
    """
    if path is None:
        path = str(Path(__file__).parent / "golden_dataset.json")

    with open(path) as f:
        data = json.load(f)

    return data.get("samples", [])


def generate_answers_for_evaluation(samples: list[dict]) -> list[dict]:
    """Run the RAG pipeline on each golden dataset question.

    For each question:
    1. Retrieves context using the full hybrid search + reranker pipeline
    2. Generates an answer using the LLM
    3. Collects the retrieved contexts

    Returns augmented samples with 'answer' and 'contexts' fields
    added, ready for RAGAS evaluation.
    """
    import yaml
    from openai import AzureOpenAI

    settings = get_settings()
    client = AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )

    # Load RAG prompt template
    prompts_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
    with open(prompts_path) as f:
        prompts = yaml.safe_load(f)
    rag_prompt = prompts["prompts"]["rag_answer_prompt"]
    system_prompt = prompts["prompts"]["system_prompt"]

    augmented_samples = []

    for i, sample in enumerate(samples):
        question = sample["question"]
        logger.info(f"Evaluating question {i + 1}/{len(samples)}: {question[:60]}...")

        # Retrieve context
        results = retrieve(question, top_k=5)
        context = format_context_for_llm(results)
        contexts = [r.content for r in results]

        # Generate answer
        prompt = rag_prompt.format(context=context, question=question)
        response = client.chat.completions.create(
            model=settings.azure_openai_chat_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )

        answer = response.choices[0].message.content

        augmented_samples.append(
            {
                "question": question,
                "answer": answer,
                "contexts": contexts,
                "ground_truth": sample.get("ground_truth", ""),
            }
        )

    return augmented_samples


def run_ragas_evaluation(samples: list[dict]) -> dict:
    """Run RAGAS evaluation on the augmented samples.

    Returns a dict of metric_name -> score.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )

        # Convert to HuggingFace Dataset format (required by RAGAS)
        dataset = Dataset.from_list(samples)

        # Run evaluation
        result = evaluate(
            dataset=dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
        )

        scores = {
            "faithfulness": float(result["faithfulness"]),
            "answer_relevancy": float(result["answer_relevancy"]),
            "context_precision": float(result["context_precision"]),
            "context_recall": float(result["context_recall"]),
        }

        logger.info(f"RAGAS evaluation results: {scores}")
        return scores

    except ImportError:
        logger.error("RAGAS not installed. Run: pip install ragas datasets")
        return {}


def check_quality_gates(scores: dict) -> tuple[bool, list[str]]:
    """Check if all metrics meet the quality thresholds.

    Returns (passed, list_of_failures).
    Used by CI/CD to decide if the build should pass or fail.
    """
    failures = []

    for metric, threshold in THRESHOLDS.items():
        score = scores.get(metric, 0.0)
        if score < threshold:
            failures.append(f"{metric}: {score:.3f} < {threshold:.3f} (FAIL)")
        else:
            logger.info(f"{metric}: {score:.3f} >= {threshold:.3f} (PASS)")

    passed = len(failures) == 0
    return passed, failures


def run_full_evaluation(golden_dataset_path: str | None = None) -> dict:
    """Run the complete evaluation pipeline.

    1. Load golden dataset
    2. Generate answers using RAG pipeline
    3. Run RAGAS evaluation
    4. Check quality gates
    5. Return comprehensive results

    This is what ci_eval.py calls during CI/CD.
    """
    # Load golden dataset
    samples = load_golden_dataset(golden_dataset_path)
    logger.info(f"Loaded {len(samples)} golden dataset samples")

    # Generate answers
    augmented = generate_answers_for_evaluation(samples)

    # Run RAGAS
    scores = run_ragas_evaluation(augmented)

    # Check gates
    passed, failures = check_quality_gates(scores)

    return {
        "passed": passed,
        "scores": scores,
        "failures": failures,
        "num_samples": len(samples),
        "thresholds": THRESHOLDS,
    }
