"""LGPD cleanup script - runnable as Cloud Run Job daily.

Triggered by Cloud Scheduler daily at 3am BRT.
Cleans up old history (>90 days) and old audit logs (>5 years).
"""
import os
import sys
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lgpd import cleanup_old_history, cleanup_old_audit

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("lgpd_cleanup")


def main():
    """Main entry point."""
    logger.info("LGPD cleanup starting...")

    history_result = cleanup_old_history()
    logger.info(f"History cleanup: {history_result}")

    audit_result = cleanup_old_audit()
    logger.info(f"Audit cleanup: {audit_result}")

    result = {
        "history": history_result,
        "audit": audit_result,
    }
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
