from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from app.domain.models import Finding, FindingStatus


def posture_score(findings: Iterable[Finding]) -> Decimal | None:
    passed = 0
    failed = 0
    for finding in findings:
        if finding.status is FindingStatus.PASS:
            passed += 1
        elif finding.status is FindingStatus.FAIL:
            failed += 1

    evaluable = passed + failed
    if evaluable == 0:
        return None

    score = Decimal(100 * passed) / Decimal(evaluable)
    return score.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
