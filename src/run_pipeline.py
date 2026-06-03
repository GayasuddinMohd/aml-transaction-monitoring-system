"""
AML Transaction Monitoring System
Master Pipeline Runner
=======================
Usage: python src/run_pipeline.py   (from project root)
"""

import os, sys, time

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=" * 60)
print("  AML Transaction Monitoring System — Full Pipeline")
print("=" * 60)

print("\n[1/2] DATA GENERATION")
print("-" * 40)
t = time.time()
from src.data_generator import main as gen_main
gen_main()
print(f"      Done in {time.time()-t:.1f}s")

print("\n[2/2] AML RULES ENGINE")
print("-" * 40)
t = time.time()
from src.rules_engine import main as rules_main
rules_main()
print(f"      Done in {time.time()-t:.1f}s")

print("\n" + "=" * 60)
print("  ✅ Pipeline complete!")
print("  ▶  Launch dashboard:  streamlit run dashboard/app.py")
print("=" * 60)
