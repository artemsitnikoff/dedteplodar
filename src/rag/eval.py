"""Evaluation module for RAG performance."""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import yaml
from pydantic import BaseModel

from .retriever import Retriever, SearchResult

logger = logging.getLogger(__name__)


class ExpectedResult(BaseModel):
    """Expected result for evaluation query."""
    chunk_type: Optional[str] = None  # 'product' | 'pdf' | None for any
    product_id: Optional[int] = None
    document_id: Optional[int] = None
    category_id: Optional[int] = None
    contains: Optional[List[str]] = None  # keywords that should be in chunk text


class EvalQuery(BaseModel):
    """Evaluation query with expected results."""
    id: int
    question: str
    expected: List[ExpectedResult]
    notes: Optional[str] = None


@dataclass
class QueryResult:
    """Result for a single evaluation query."""
    query_id: int
    question: str
    hit_at_1: bool
    hit_at_5: bool
    hit_at_10: bool
    mrr: float
    rank_of_first_hit: Optional[int]
    top_result: Optional[SearchResult]


@dataclass
class EvalReport:
    """Complete evaluation report."""
    mean_hit_at_1: float
    mean_hit_at_5: float
    mean_hit_at_10: float
    mean_mrr: float
    per_query_results: List[QueryResult]
    total_queries: int


class RAGEvaluator:
    """Evaluates RAG retrieval performance."""

    def __init__(self, retriever: Retriever):
        """Initialize evaluator.

        Args:
            retriever: Retriever instance to evaluate
        """
        self.retriever = retriever

    def load_queries_from_yaml(self, yaml_path: str) -> List[EvalQuery]:
        """Load evaluation queries from YAML file.

        Args:
            yaml_path: Path to YAML file with queries

        Returns:
            List of EvalQuery objects
        """
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        queries = []
        for query_data in data.get('queries', []):
            expected = [ExpectedResult(**exp) for exp in query_data.get('expected', [])]
            queries.append(EvalQuery(
                id=query_data['id'],
                question=query_data['question'],
                expected=expected,
                notes=query_data.get('notes')
            ))

        logger.info(f"Loaded {len(queries)} evaluation queries from {yaml_path}")
        return queries

    def _matches_expected(self, result: SearchResult, expected: ExpectedResult) -> bool:
        """Check if search result matches expected criteria.

        Args:
            result: Search result to check
            expected: Expected criteria

        Returns:
            True if result matches any criteria
        """
        # Check chunk type
        if expected.chunk_type and result.chunk_type != expected.chunk_type:
            return False

        # Check exact matches
        if expected.product_id and result.product_id == expected.product_id:
            return True

        if expected.document_id and result.document_id == expected.document_id:
            return True

        if expected.category_id and result.category_id == expected.category_id:
            return True

        # Check contains keywords
        if expected.contains:
            chunk_text_lower = result.chunk_text.lower()
            if all(keyword.lower() in chunk_text_lower for keyword in expected.contains):
                return True

        # If no specific criteria matched but chunk_type was the only filter
        if (expected.chunk_type and not expected.product_id and
            not expected.document_id and not expected.category_id and not expected.contains):
            return True

        return False

    def _evaluate_query(
        self,
        session,
        eval_query: EvalQuery,
        k: int = 10
    ) -> QueryResult:
        """Evaluate a single query.

        Args:
            session: Database session
            eval_query: Query to evaluate
            k: Number of results to retrieve

        Returns:
            QueryResult with metrics
        """
        # Get search results
        results = self.retriever.search(session, eval_query.question, k=k)

        # Find first matching result
        rank_of_first_hit = None
        for rank, result in enumerate(results, 1):
            if any(self._matches_expected(result, expected) for expected in eval_query.expected):
                rank_of_first_hit = rank
                break

        # Calculate metrics
        hit_at_1 = rank_of_first_hit == 1 if rank_of_first_hit else False
        hit_at_5 = rank_of_first_hit <= 5 if rank_of_first_hit else False
        hit_at_10 = rank_of_first_hit <= 10 if rank_of_first_hit else False
        mrr = 1.0 / rank_of_first_hit if rank_of_first_hit else 0.0

        top_result = results[0] if results else None

        return QueryResult(
            query_id=eval_query.id,
            question=eval_query.question,
            hit_at_1=hit_at_1,
            hit_at_5=hit_at_5,
            hit_at_10=hit_at_10,
            mrr=mrr,
            rank_of_first_hit=rank_of_first_hit,
            top_result=top_result
        )

    def run_eval(self, session, queries: List[EvalQuery]) -> EvalReport:
        """Run evaluation on a set of queries.

        Args:
            session: Database session
            queries: List of evaluation queries

        Returns:
            Complete evaluation report
        """
        logger.info(f"Running evaluation on {len(queries)} queries")

        per_query_results = []
        for eval_query in queries:
            result = self._evaluate_query(session, eval_query)
            per_query_results.append(result)
            logger.debug(f"Query {eval_query.id}: MRR={result.mrr:.3f}, Hit@5={result.hit_at_5}")

        # Calculate aggregate metrics
        total_queries = len(queries)
        mean_hit_at_1 = sum(r.hit_at_1 for r in per_query_results) / total_queries
        mean_hit_at_5 = sum(r.hit_at_5 for r in per_query_results) / total_queries
        mean_hit_at_10 = sum(r.hit_at_10 for r in per_query_results) / total_queries
        mean_mrr = sum(r.mrr for r in per_query_results) / total_queries

        report = EvalReport(
            mean_hit_at_1=mean_hit_at_1,
            mean_hit_at_5=mean_hit_at_5,
            mean_hit_at_10=mean_hit_at_10,
            mean_mrr=mean_mrr,
            per_query_results=per_query_results,
            total_queries=total_queries
        )

        logger.info(f"Evaluation completed:")
        logger.info(f"  Hit@1: {mean_hit_at_1:.3f}")
        logger.info(f"  Hit@5: {mean_hit_at_5:.3f}")
        logger.info(f"  Hit@10: {mean_hit_at_10:.3f}")
        logger.info(f"  MRR: {mean_mrr:.3f}")

        return report

    def print_detailed_results(self, report: EvalReport) -> None:
        """Print detailed evaluation results.

        Args:
            report: Evaluation report to print
        """
        print("=" * 80)
        print("RAG Evaluation Results")
        print("=" * 80)
        print(f"Total queries: {report.total_queries}")
        print(f"Hit@1:  {report.mean_hit_at_1:.3f}")
        print(f"Hit@5:  {report.mean_hit_at_5:.3f}")
        print(f"Hit@10: {report.mean_hit_at_10:.3f}")
        print(f"MRR:    {report.mean_mrr:.3f}")
        print()

        print("Per-query results:")
        print("-" * 80)
        print(f"{'ID':<3} {'Hit@5':<6} {'MRR':<6} {'Rank':<5} {'Query':<30} {'Top Result'}")
        print("-" * 80)

        for result in report.per_query_results:
            hit5_str = "✓" if result.hit_at_5 else "✗"
            rank_str = str(result.rank_of_first_hit) if result.rank_of_first_hit else "-"
            query_short = result.question[:30] + "..." if len(result.question) > 30 else result.question

            top_result_info = ""
            if result.top_result:
                if result.top_result.chunk_type == "product":
                    top_result_info = f"Product {result.top_result.product_id}"
                else:
                    top_result_info = f"Doc {result.top_result.document_id}"

            print(f"{result.query_id:<3} {hit5_str:<6} {result.mrr:<6.3f} {rank_str:<5} {query_short:<30} {top_result_info}")

        print("-" * 80)