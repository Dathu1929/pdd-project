import os
import sys
import subprocess

if __name__ == "__main__":
    script_path = os.path.join(os.path.dirname(__file__), "generate_test_reports.py")
    subprocess.check_call([sys.executable, script_path])
