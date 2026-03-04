"""
ci_eval.py - CI/CD Quality Gate Script
=========================================
WHY: This script runs in GitHub Actions on every pull request.
     If RAG quality drops below thresholds, the build FAILS,
     preventing bad prompt changes or chunking regressions from
     reaching production.

USAGE:
  python -m app.evaluation.ci_eval

EXIT CODES:
  0 = All metrics pass thresholds
  1 = One or more metrics below threshold (build should fail)
"""

import json
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    from app.evaluation.evaluate import run_full_evaluation

    logger.info("=" * 60)
    logger.info("RAG Quality Gate - CI/CD Evaluation")
    logger.info("=" * 60)

    results = run_full_evaluation()

    # Print results
    logger.info("\nResults:")
    logger.info(f"  Samples evaluated: {results['num_samples']}")
    logger.info(f"  Scores: {json.dumps(results['scores'], indent=2)}")
    logger.info(f"  Thresholds: {json.dumps(results['thresholds'], indent=2)}")

    if results["passed"]:
        logger.info("\nQUALITY GATE: PASSED")
        sys.exit(0)
    else:
        logger.error("\nQUALITY GATE: FAILED")
        for failure in results["failures"]:
            logger.error(f"  - {failure}")
        sys.exit(1)


if __name__ == "__main__":
    main()
