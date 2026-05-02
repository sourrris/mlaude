import argparse
import os
import json
import time
import httpx
import pexpect

# LLM Configuration
LLM_BASE_URL = "http://127.0.0.1:1234/v1"
MODEL = "gemma4:e4b" # Using the local LM model seen previously

SYSTEM_PROMPT = """You are an autonomous Quality Assurance (QA) Agent. 
Your goal is to test an interactive command-line AI tool named 'mlaude'.
You will receive the terminal output from 'mlaude' and must decide what to do next.

Your task is to intentionally try to break the tool, test edge cases, and discover UX flaws.
Try running different slash commands (like /help, /model, /tools), interacting with the assistant, or using tools.

You MUST respond ONLY in valid JSON format with exactly two keys:
1. "flaw_found": A string describing a bug or UX flaw you just noticed in the recent output. If no flaw is found, this should be null.
2. "next_command": The exact text string of the next command/message you want to send to the terminal. (e.g., "/help" or "What is 2+2?").

Example Output:
{
    "flaw_found": null,
    "next_command": "/tools"
}
"""

def query_llm(messages, model=MODEL, base_url=LLM_BASE_URL, temperature=0.3, timeout=60.0):
    """Query the local LLM for the next action."""
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{base_url}/chat/completions", json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            
            # Clean up the response to ensure it's JSON
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
                
            return json.loads(content)
    except Exception as e:
        print(f"Error querying QA LLM: {e}")
        return {"flaw_found": None, "next_command": "/help"} # Fallback

def log_flaw(flaw):
    """Log a discovered flaw to the markdown file."""
    if not flaw:
        return
        
    print(f"\n[QA AGENT] DISCOVERED FLAW: {flaw}\n")
    with open("qa_flaws_log.md", "a") as f:
        f.write(f"- {flaw}\n")

def run_qa_loop(
    max_iterations=100,
    model=MODEL,
    base_url=LLM_BASE_URL,
    temperature=0.3,
    timeout=60.0,
):
    print("Starting Autonomous QA Agent...")
    
    # Ensure log file exists
    if not os.path.exists("qa_flaws_log.md"):
        with open("qa_flaws_log.md", "w") as f:
            f.write("# QA Agent Autonomous Flaws Log\n\n")

    # Start mlaude
    child = pexpect.spawn('uv run mlaude', encoding='utf-8', dimensions=(24, 200))
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    try:
        for i in range(max_iterations):
            print(f"\n--- QA Turn {i+1}/{max_iterations} ---")
            
            # Read output until prompt
            child.expect(r'❯', timeout=60)
            terminal_output = child.before.strip()
            print(f"[Terminal Output]:\n{terminal_output[:500]}...\n")
            
            # Ask LLM for next move
            messages.append({"role": "user", "content": f"Terminal Output:\n{terminal_output}"})
            
            response_json = query_llm(
                messages,
                model=model,
                base_url=base_url,
                temperature=temperature,
                timeout=timeout,
            )
            
            flaw = response_json.get("flaw_found")
            next_cmd = response_json.get("next_command", "/version")
            
            if flaw:
                log_flaw(flaw)
                
            print(f"[QA AGENT] Sending command: {next_cmd}")
            
            # Add assistant response to history
            messages.append({"role": "assistant", "content": json.dumps(response_json)})
            
            # Send command to terminal
            child.sendline(next_cmd)
            time.sleep(1) # Slight pause to let UI breathe
            
    except pexpect.TIMEOUT:
        print("\n[QA AGENT] TIMEOUT waiting for terminal prompt.")
        log_flaw("Terminal hung or timed out waiting for prompt. Possible freeze.")
    except Exception as e:
        print(f"\n[QA AGENT] ERROR: {e}")
    finally:
        child.sendline('/quit')
        child.close()
        print("\nQA Session Completed.")

def parse_args():
    parser = argparse.ArgumentParser(description="Autonomous QA loop for mlaude CLI.")
    parser.add_argument(
        "-n",
        "--iterations",
        type=int,
        default=5,
        help="Number of QA turns to execute (default: 5).",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help=f"Model name for QA LLM (default: {MODEL}).",
    )
    parser.add_argument(
        "--base-url",
        default=LLM_BASE_URL,
        help=f"OpenAI-compatible base URL for QA LLM (default: {LLM_BASE_URL}).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="Sampling temperature for QA LLM (default: 0.3).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="HTTP timeout seconds for QA LLM requests (default: 60.0).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_qa_loop(
        max_iterations=args.iterations,
        model=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
        timeout=args.timeout,
    )
