import sys
import os

# Add the current directory to sys.path so we can import from .agent
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent import run_agent

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 main.py <input_csv_path> <output_csv_path>")
        sys.exit(1)
    
    input_csv = sys.argv[1]
    output_csv = sys.argv[2]
    
    run_agent(input_csv, output_csv)
