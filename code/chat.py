"""
chat.py — Interactive Playground for the Support Triage Agent.

Use this script to chat with the agent in real-time. 
Perfect for testing and live demonstrations during the judge interview.
"""

import os
from agent import SupportAgent
from dotenv import load_dotenv

load_dotenv()

def main():
    print("\n" + "="*50)
    print("  SUPPORT AGENT INTERACTIVE PLAYGROUND")
    print("="*50)
    print("Type 'exit' or 'quit' to stop.")
    
    agent = SupportAgent()
    
    while True:
        try:
            print("\n" + "-"*30)
            subject = input("Subject (optional): ").strip()
            issue = input("Issue: ").strip()
            
            if not issue or issue.lower() in ['exit', 'quit']:
                break
                
            company = input("Company (HackerRank/Claude/Visa/None): ").strip() or "None"
            
            print("\nProcessing...\n")
            result = agent.process_issue(issue, subject, company)
            
            print("\n" + "="*50)
            print(f"STATUS: {result['status'].upper()}")
            print(f"TYPE:   {result['request_type']}")
            print(f"AREA:   {result['product_area']}")
            print("-" * 50)
            print(f"RESPONSE:\n{result['response']}")
            print("-" * 50)
            print(f"JUSTIFICATION:\n{result['justification']}")
            print("="*50 + "\n")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}")

    print("\nGoodbye!")

if __name__ == "__main__":
    main()
