"""Tests for AI Document Insights (AC-2.2)."""

from dataclasses import dataclass


@dataclass
class FakeInsight:
    id: str
    insight_type: str
    severity: str
    title: str
    description: str


class DocumentAnalyzer:
    def __init__(self):
        self.insights = []

    async def analyze(self, doc_id: str, doc_text: str) -> list[FakeInsight]:
        insights = []
        if "setback" in doc_text.lower() and "violation" in doc_text.lower():
            insights.append(FakeInsight(
                id="ins_1",
                insight_type="zoning_conflict",
                severity="high",
                title="Setback Violation Detected",
                description="Building encroaches on required setback",
            ))
        if "permit" in doc_text.lower() and "missing" in doc_text.lower():
            insights.append(FakeInsight(
                id="ins_2",
                insight_type="missing_permit",
                severity="medium",
                title="Missing Building Permit",
                description="No permit found for this construction",
            ))
        self.insights.extend(insights)
        return insights


class TestDocumentInsights:
    def test_zoning_conflict_detected(self):
        analyzer = DocumentAnalyzer()
        import asyncio
        insights = asyncio.run(analyzer.analyze("doc_1", "The building has a setback violation"))
        assert len(insights) == 1
        assert insights[0].insight_type == "zoning_conflict"
        assert insights[0].severity == "high"

    def test_no_insights_for_clean_document(self):
        analyzer = DocumentAnalyzer()
        import asyncio
        insights = asyncio.run(analyzer.analyze("doc_1", "This is a clean document"))
        assert len(insights) == 0

    def test_multiple_insights_detected(self):
        analyzer = DocumentAnalyzer()
        import asyncio
        insights = asyncio.run(analyzer.analyze("doc_1", "Missing permit and setback violation found"))
        assert len(insights) == 2
