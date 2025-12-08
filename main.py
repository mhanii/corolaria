"""
Coloraria Ingestion - Main Entry Point.

This is a convenience wrapper for the ingestion service.
For full CLI options, use: python -m src.ingestion.main --help
"""

from src.ingestion.main import run_ingestion, ingestion_lifecycle
from src.ingestion.result import IngestionStatus


def main():
    """Run the ingestion pipeline for the default law."""
    law_id = "BOE-A-1978-31229"  # Spanish Constitution
    
    with ingestion_lifecycle():
        result = run_ingestion(law_id)
        
        if result.status == IngestionStatus.SUCCESS:
            print(f"\n✓ Ingestion successful for {law_id}")
            print(f"  Duration: {result.duration_seconds:.2f}s")
            print(f"  Nodes created: {result.nodes_created}")
        elif result.status == IngestionStatus.ROLLED_BACK:
            print(f"\n⚠ Ingestion failed and was rolled back")
            print(f"  Failed step: {result.failed_step}")
            print(f"  Error: {result.error_message}")
        else:
            print(f"\n✗ Ingestion failed: {result.error_message}")
            return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
