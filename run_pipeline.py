"""
AML Transaction Monitoring System
run_pipeline.py — Single entry point to build everything from scratch.

Usage:
    python run_pipeline.py           # full build
    python run_pipeline.py --reset   # drop DB and rebuild
"""

import os
import sys
import argparse

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'aml_system.db')

def main():
    parser = argparse.ArgumentParser(description='AML TMS Pipeline')
    parser.add_argument('--reset', action='store_true', help='Delete DB and rebuild from scratch')
    args = parser.parse_args()

    if args.reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("🗑  Existing database removed.")

    print("\n" + "═"*55)
    print("  AML TRANSACTION MONITORING SYSTEM")
    print("  End-to-End Pipeline Runner")
    print("═"*55)

    # Step 1: Generate data
    print("\n📦 STEP 1: Generating synthetic data...")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
    from data_generator import build_database
    build_database()

    # Step 2: Run rules engine + scoring
    print("\n⚙  STEP 2: Running AML rules engine...")
    from alert_scoring import run_pipeline
    run_pipeline()

    print("\n" + "═"*55)
    print("  ✅ PIPELINE COMPLETE")
    print("═"*55)
    print("\nNext steps:")
    print("  Launch dashboard:  streamlit run dashboard/app.py")
    print("  View outputs:      ls outputs/")
    print("  Explore DB:        sqlite3 data/aml_system.db\n")

if __name__ == '__main__':
    main()
